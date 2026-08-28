# ROOT: terraform/live/dev/ecs (main.tf)
# Two apps, two module blocks, same modules/ecs-service source. This is
# the pattern to copy when adding a language: another module block here,
# a matching pair of variables above, and matching entries in
# terraform.tfvars.

module "java_ecs" {
  source = "../../../modules/ecs-service"

  name                  = "psa-java"
  environment           = "dev"
  vpc_id                = var.vpc_id
  subnet_ids            = var.subnet_ids
  image_uri             = var.java_image_uri
  task_role_arn         = data.terraform_remote_state.foundation.outputs.workload_role_arn
  nexus_pull_secret_arn = data.terraform_remote_state.foundation.outputs.nexus_pull_secret_arn
  alb_target_group_arn  = var.java_alb_target_group_arn

  environment_variables = {
    NEW_RELIC_APP_NAME      = "psa-java-dev"
    NEW_RELIC_LOG_FILE_PATH = "STDOUT"
    JAVA_OPTS               = "-javaagent:/app/newrelic/newrelic.jar"
  }

  secrets = {
    DB_CREDENTIALS        = data.terraform_remote_state.foundation.outputs.db_secret_arn
    NEW_RELIC_LICENSE_KEY = var.new_relic_license_key_secret_arn
  }
}

module "python_ecs" {
  source = "../../../modules/ecs-service"

  name                  = "psa-python"
  environment           = "dev"
  vpc_id                = var.vpc_id
  subnet_ids            = var.subnet_ids
  image_uri             = var.python_image_uri
  task_role_arn         = data.terraform_remote_state.foundation.outputs.workload_role_arn
  nexus_pull_secret_arn = data.terraform_remote_state.foundation.outputs.nexus_pull_secret_arn
  alb_target_group_arn  = var.python_alb_target_group_arn

  environment_variables = {}

  secrets = {
    DB_CREDENTIALS = data.terraform_remote_state.foundation.outputs.db_secret_arn
  }
}

# The next language variant needing an ECS deployment is another module
# block like these two -- modules/ecs-service itself doesn't change.
