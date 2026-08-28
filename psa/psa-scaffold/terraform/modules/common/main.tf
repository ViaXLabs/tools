# MODULE: terraform/modules/common (main.tf)
# Creates the infra shared by every compute target in one environment:
# KMS key, RDS Postgres + its credentials secret, the baseline IAM role
# used by both ECS tasks and EKS pods (via IRSA), and a backup-only ECR
# repo per app. Called once per environment by terraform/live/<env>/foundation.
# Everything downstream (ecs/, eks/) reads this module's outputs via
# terraform_remote_state instead of duplicating any of this.

locals {
  name_prefix = "psa-${var.environment}"
  common_tags = merge(var.tags, {
    Project     = "psa"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# Nexus is the registry that ECS/EKS actually pull from -- see
# nexus_pull_secret_arn below for that side. These ECR repos exist purely
# as a backup copy: the CI pipeline pushes here in addition to Nexus, but
# nothing ever pulls from these for deployment. If ECR access ever went
# away entirely, nothing here would break.
resource "aws_ecr_repository" "backup" {
  for_each             = toset(var.app_names)
  name                 = "${local.name_prefix}-${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, {
    Purpose = "backup-only, not used for deployment"
  })
}

resource "aws_kms_key" "psa" {
  description         = "${local.name_prefix} KMS key for secrets and RDS storage"
  enable_key_rotation = true
  tags                = local.common_tags
}

resource "aws_security_group" "db" {
  name_prefix = "${local.name_prefix}-db-"
  vpc_id      = var.vpc_id
  tags        = local.common_tags

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ecs-service and eks-workload each add their own ingress rule into this
# security group (see those modules) so this module doesn't need to know
# about compute-layer security groups in advance.

resource "aws_db_subnet_group" "psa" {
  name       = "${local.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
  tags       = local.common_tags
}

resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_secretsmanager_secret" "db" {
  name       = "${local.name_prefix}-db-credentials"
  kms_key_id = aws_kms_key.psa.arn
  tags       = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
  })
}

resource "aws_db_instance" "psa" {
  identifier              = "${local.name_prefix}-postgres"
  engine                  = "postgres"
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  db_name                 = var.db_name
  username                = var.db_username
  password                = random_password.db.result
  db_subnet_group_name    = aws_db_subnet_group.psa.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  kms_key_id              = aws_kms_key.psa.arn
  storage_encrypted       = true
  skip_final_snapshot     = true
  tags                    = local.common_tags
}

# Baseline role assumed by ECS tasks directly, and by EKS pods via IRSA
# (the eks-workload module attaches this arn as an IRSA annotation).
resource "aws_iam_role" "psa_workload" {
  name = "${local.name_prefix}-workload"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "read_secrets" {
  name = "${local.name_prefix}-read-secrets"
  role = aws_iam_role.psa_workload.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.db.arn,
        var.nexus_pull_secret_arn,
      ]
    }]
  })
}
