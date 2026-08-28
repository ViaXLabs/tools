# MODULE: terraform/modules/common
# Reusable, no state of its own -- called by terraform/live/<env>/foundation.
# Inputs required by callers: environment, vpc_id, private_subnet_ids,
# nexus_pull_secret_arn (see below for what each is for).
# See main.tf in this directory for what it actually creates.

variable "environment" {
  description = "Environment name (dev, test, stage, prod)"
  type        = string
}

variable "vpc_id" {
  description = "Existing VPC ID owned by the platform team"
  type        = string
}

variable "private_subnet_ids" {
  description = "Existing private subnet IDs for RDS and workloads"
  type        = list(string)
}

variable "app_names" {
  description = "Language variants that get a backup ECR repo (CI pushes a backup copy here in addition to Nexus)"
  type        = list(string)
  default     = ["python", "java"]
}

variable "nexus_pull_secret_arn" {
  description = "Existing Secrets Manager secret holding Nexus registry pull credentials (username/password). Managed outside this repo -- foundation just wires up read access for the workload role."
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class for the demo Postgres database"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_name" {
  type    = string
  default = "psa"
}

variable "db_username" {
  type    = string
  default = "psa_admin"
}

variable "tags" {
  type    = map(string)
  default = {}
}
