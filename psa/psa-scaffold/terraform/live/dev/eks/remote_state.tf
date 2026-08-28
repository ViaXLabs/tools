# ROOT: terraform/live/dev/eks (remote_state.tf)
# Same foundation state that ecs/remote_state.tf reads -- the "key" below
# MUST match foundation/backend.tf's key exactly.

data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket = "psa-tfstate"
    key    = "psa/dev/foundation/terraform.tfstate"
    region = "us-east-1"
  }
}
