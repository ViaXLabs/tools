# MODULE: terraform/modules/ecs-service (outputs.tf)
# Not currently consumed by anything in this scaffold -- exposed for
# convenience if a future need arises (e.g. wiring a target group or
# security group rule from outside this module).

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_name" {
  value = aws_ecs_service.this.name
}

output "security_group_id" {
  value = aws_security_group.service.id
}
