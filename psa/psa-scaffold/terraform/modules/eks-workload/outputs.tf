# MODULE: terraform/modules/eks-workload (outputs.tf)
# Not currently consumed by anything in this scaffold -- exposed for
# convenience (e.g. a future module that needs to know the namespace a
# release landed in).

output "namespace" {
  value = kubernetes_namespace.this.metadata[0].name
}

output "release_name" {
  value = helm_release.this.name
}
