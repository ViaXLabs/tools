# ROOT: terraform/live/dev/ecs (versions.tf)
# Only the aws provider -- no kubernetes/helm here. That's deliberate:
# this root only ever touches ECS/AWS resources, so it only ever needs
# this one provider. Compare to eks/versions.tf, which needs three.

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
