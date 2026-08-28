# MODULE: terraform/modules/ecs-service
# Reusable, no state of its own -- one instance of this module is one ECS
# service (its own cluster, task def, service, autoscaling). Deliberately
# language-agnostic: it only takes an image_uri string, never anything
# language-specific. Called from terraform/live/<env>/ecs/main.tf, once
# per app (see java_ecs / python_ecs there for the pattern).

variable "name" {
  description = "Service name, e.g. psa-java"
  type        = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "cluster_name" {
  description = "Name for this app's ECS cluster (defaults to <name>-<environment>)"
  type        = string
  default     = null
}

variable "image_uri" {
  description = "Full image URI including tag. This module never needs to know what language built it."
  type        = string
}

variable "container_port" {
  type    = number
  default = 8080
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "task_role_arn" {
  description = "IAM role ARN from the foundation module's workload_role_arn output"
  type        = string
}

variable "nexus_pull_secret_arn" {
  description = "Secrets Manager ARN with Nexus registry credentials, used as ECS repositoryCredentials since Nexus isn't IAM-integrated like ECR"
  type        = string
}

variable "environment_variables" {
  description = "Plain (non-secret) container env vars, e.g. NEW_RELIC_APP_NAME"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Map of container env var name to Secrets Manager ARN"
  type        = map(string)
  default     = {}
}

variable "alb_target_group_arn" {
  description = "Target group ARN from the platform-managed shared ALB"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
