# MODULE: terraform/modules/ecs-service (main.tf)
# One ECS cluster + task definition + service + autoscaling per call site.
# repositoryCredentials on the container definition is what lets ECS pull
# from Nexus (a private, non-IAM-integrated registry) -- see
# var.nexus_pull_secret_arn. task_role_arn and execution_role_arn are set
# to the same role here (the shared foundation workload role) as a
# simplification; see the README for why that's fine for this scaffold.

locals {
  cluster_name = coalesce(var.cluster_name, "${var.name}-${var.environment}")
}

data "aws_region" "current" {}

resource "aws_ecs_cluster" "this" {
  name = local.cluster_name
  tags = var.tags
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name}-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.task_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = var.name
    image     = var.image_uri
    essential = true
    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]
    repositoryCredentials = {
      credentialsParameter = var.nexus_pull_secret_arn
    }
    environment = [for k, v in var.environment_variables : { name = k, value = v }]
    secrets     = [for k, v in var.secrets : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/psa/${var.environment}/${var.name}"
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.name
        "awslogs-create-group"  = "true"
      }
    }
  }])

  tags = var.tags
}

resource "aws_security_group" "service" {
  name_prefix = "${var.name}-${var.environment}-"
  vpc_id      = var.vpc_id
  tags        = var.tags

  ingress {
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tighten to the shared ALB's security group before prod
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_service" "this" {
  name            = "${var.name}-${var.environment}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = var.name
    container_port   = var.container_port
  }

  tags = var.tags
}

resource "aws_appautoscaling_target" "this" {
  max_capacity       = var.desired_count * 3
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-${var.environment}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 60
  }
}
