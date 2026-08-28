# ROOT: terraform/live/dev/foundation (versions.tf)
# Applied FIRST, before ecs/ or eks/ -- they both read this root's state
# via terraform_remote_state. Only needs the aws + random providers.

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
}
