# ROOT: terraform/live/dev/foundation (main.tf)
# "dev" is hardcoded below -- this whole directory only ever represents
# the dev environment (that's what makes it a "live" root instead of a
# reusable module). Adding another environment means copying this whole
# terraform/live/dev/ directory, not parameterizing this file.
# app_names must list every language variant that needs a backup ECR
# repo -- add to this list when a new language is added (see README).

module "foundation" {
  source = "../../../modules/common"

  environment           = "dev"
  vpc_id                = var.vpc_id
  private_subnet_ids    = var.private_subnet_ids
  nexus_pull_secret_arn = var.nexus_pull_secret_arn
  app_names             = ["python", "java"]
}
