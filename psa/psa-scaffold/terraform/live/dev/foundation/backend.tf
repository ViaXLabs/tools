# ROOT: terraform/live/dev/foundation (backend.tf)
# This root's own state, separate from ecs/ and eks/. The "key" value
# here MUST match exactly what ecs/remote_state.tf and eks/remote_state.tf
# read from -- if you change it here, change it in both of those too.
# REPLACE_ME: bucket and dynamodb_table need your actual values.

terraform {
  backend "s3" {
    bucket         = "psa-tfstate"    # replace with your actual state bucket
    key            = "psa/dev/foundation/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "psa-tflock"     # replace with your actual lock table
    encrypt        = true
  }
}
