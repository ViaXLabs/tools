# ROOT: terraform/live/dev/ecs (variables.tf)
# One pair of vars per app (java_*/python_*) -- adding a language means
# adding another pair here plus another module block in main.tf.
# java_image_uri/python_image_uri get their default from terraform.tfvars
# but are meant to be overridden per-deploy by the CD pipeline's varFiles
# input (see .harness/pipelines/psa-java-ecs.yaml) -- the tfvars value is
# really just "what to use for a manual terraform apply".

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "new_relic_license_key_secret_arn" {
  description = "Secrets Manager ARN holding the New Relic license key"
  type        = string
}

variable "java_image_uri" {
  description = "Set by the Harness pipeline at deploy time (image tag from the build stage)"
  type        = string
}

variable "java_alb_target_group_arn" {
  description = "Target group ARN from the platform-managed shared ALB, for the java service"
  type        = string
}

variable "python_image_uri" {
  description = "Set by the Harness pipeline at deploy time (image tag from the build stage)"
  type        = string
}

variable "python_alb_target_group_arn" {
  description = "Target group ARN from the platform-managed shared ALB, for the python service"
  type        = string
}
