# ROOT: terraform/live/dev/eks (backend.tf)
# Separate state from foundation/ and ecs/. REPLACE_ME: bucket/dynamodb_table
# need your actual values (same ones used in the other two backend.tf files).

terraform {
  backend "s3" {
    bucket         = "psa-tfstate"
    key            = "psa/dev/eks/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "psa-tflock"
    encrypt        = true
  }
}
