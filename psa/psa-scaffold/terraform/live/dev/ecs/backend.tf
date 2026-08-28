# ROOT: terraform/live/dev/ecs (backend.tf)
# Separate state from foundation/ and eks/ -- this root can be applied
# independently without touching either of the others' state.
# REPLACE_ME: bucket/dynamodb_table need your actual values (same ones
# used in foundation/backend.tf and eks/backend.tf).

terraform {
  backend "s3" {
    bucket         = "psa-tfstate"
    key            = "psa/dev/ecs/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "psa-tflock"
    encrypt        = true
  }
}
