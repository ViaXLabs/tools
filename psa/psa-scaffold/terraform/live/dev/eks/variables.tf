# ROOT: terraform/live/dev/eks (variables.tf)
# Mirrors ecs/variables.tf's pattern: one pair per app. java_image_uri and
# python_image_uri have the same "default for manual apply, overridden by
# the CD pipeline" relationship explained in ecs/variables.tf.

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "eks_cluster_name" {
  description = "Existing EKS cluster name (owned by the platform team)"
  type        = string
}

variable "java_image_uri" {
  description = "Set by the Harness pipeline at deploy time (image tag from the build stage)"
  type        = string
}

variable "java_ingress_host" {
  type    = string
  default = "psa-java.dev.internal"
}

variable "python_image_uri" {
  description = "Set by the Harness pipeline at deploy time (image tag from the build stage)"
  type        = string
}

variable "python_ingress_host" {
  type    = string
  default = "psa-python.dev.internal"
}
