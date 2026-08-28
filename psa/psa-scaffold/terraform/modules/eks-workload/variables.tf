# MODULE: terraform/modules/eks-workload
# Reusable, no state of its own -- one instance of this module is one
# helm_release of the shared chart at charts/psa-service. Language-agnostic
# like modules/ecs-service: only takes image_repository/image_tag, never
# anything language-specific. Called from terraform/live/<env>/eks/main.tf,
# once per app (see java_eks / python_eks there for the pattern).
# The chart itself lives at charts/psa-service/ -- this module's job is
# just translating Terraform variables into that chart's Helm values.

variable "name" {
  description = "Release name, e.g. psa-java -- this becomes the k8s resource name via the chart"
  type        = string
}

variable "environment" {
  type = string
}

variable "namespace" {
  type    = string
  default = null
}

variable "chart_path" {
  description = "Path to the shared Helm chart (charts/psa-service), passed in by the live root"
  type        = string
}

variable "image_repository" {
  description = "Full repository path in Nexus, without the tag"
  type        = string
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "container_port" {
  type    = number
  default = 8080
}

variable "replicas" {
  type    = number
  default = 1
}

variable "cpu_request" {
  type    = string
  default = "250m"
}

variable "memory_request" {
  type    = string
  default = "512Mi"
}

variable "irsa_role_arn" {
  description = "IAM role ARN from the foundation module's workload_role_arn output"
  type        = string
}

variable "environment_variables" {
  type    = map(string)
  default = {}
}

variable "secret_env_from" {
  description = "Name of a Kubernetes secret (e.g. synced by External Secrets) to load as env vars"
  type        = string
  default     = null
}

variable "image_pull_secret" {
  description = "Name of a k8s dockerconfigjson Secret with Nexus pull credentials, synced into the namespace outside Terraform"
  type        = string
  default     = null
}

variable "ingress_host" {
  description = "Hostname to route to this workload, e.g. psa-java.dev.internal"
  type        = string
}
