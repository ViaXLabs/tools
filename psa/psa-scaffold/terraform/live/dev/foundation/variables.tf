# ROOT: terraform/live/dev/foundation (variables.tf)
# Values for these come from terraform.tfvars in this same directory.
# vpc_id, private_subnet_ids, nexus_pull_secret_arn are all REPLACE_ME
# in that file -- see terraform.tfvars for exactly what's a placeholder.

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_id" {
  description = "Existing VPC ID (owned by the platform team)"
  type        = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "nexus_pull_secret_arn" {
  description = "Existing Secrets Manager secret holding Nexus registry pull credentials"
  type        = string
}
