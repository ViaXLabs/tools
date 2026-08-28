# MODULE: terraform/modules/eks-workload (main.tf)
# Creates the namespace (if not already there) and a helm_release of
# charts/psa-service. All chart-specific values (image, replicas, env
# vars, the IRSA role ARN as a service-account annotation, ingress host,
# and optionally an imagePullSecret name) are assembled into one
# yamlencode()'d values block below -- see charts/psa-service/values.yaml
# for the full list of keys the chart understands.

locals {
  namespace = coalesce(var.namespace, "psa-${var.environment}")
}

resource "kubernetes_namespace" "this" {
  metadata {
    name = local.namespace
  }
}

# One helm_release per app. Every PSA language variant points at the same
# chart_path (charts/psa-service) -- only the values below change per app.
# This is intentionally the same pattern as modules/ecs-service: one
# reusable definition, parameterized per caller.
resource "helm_release" "this" {
  name       = var.name
  namespace  = kubernetes_namespace.this.metadata[0].name
  chart      = var.chart_path

  values = [
    yamlencode(merge(
      {
        image = {
          repository = var.image_repository
          tag        = var.image_tag
        }
        replicaCount  = var.replicas
        containerPort = var.container_port
        resources = {
          requests = {
            cpu    = var.cpu_request
            memory = var.memory_request
          }
        }
        env = [for k, v in var.environment_variables : { name = k, value = v }]
        envFrom = var.secret_env_from == null ? [] : [
          { secretRef = { name = var.secret_env_from } }
        ]
        serviceAccount = {
          create = true
          annotations = {
            "eks.amazonaws.com/role-arn" = var.irsa_role_arn
          }
        }
        ingress = {
          enabled = true
          host    = var.ingress_host
        }
        service = {
          port = 80
        }
      },
      var.image_pull_secret == null ? {} : { imagePullSecret = var.image_pull_secret }
    ))
  ]
}
