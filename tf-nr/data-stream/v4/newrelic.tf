# ============================================================
# New Relic AWS account link
# ============================================================
# This is a SEPARATE concern from the Firehose role in iam.tf: this role is
# assumed BY New Relic (via their fixed AWS account) to poll/read your
# account for entity metadata and the polling-only integrations (billing,
# cloudtrail, health, trusted advisor, vpc, x-ray). The Firehose role is
# assumed BY the AWS Firehose service to push metric-stream data.
#
# New Relic's AWS account ID (754728514883) is fixed and publicly
# documented for the standard cloud-integrations flow (this is distinct
# from the separate account ID New Relic uses for Workflow Automation --
# don't mix the two up).

data "aws_iam_policy_document" "newrelic_assume_policy" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["754728514883"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.newrelic_account_id]
    }
  }
}

resource "aws_iam_role" "newrelic_aws_role" {
  name        = "NewRelicInfrastructure-Integrations-${var.name_prefix}"
  description = "Role assumed by New Relic to read AWS account data for monitoring/integrations"

  assume_role_policy = data.aws_iam_policy_document.newrelic_assume_policy.json

  tags = var.tags
}

# AWS-managed ReadOnlyAccess -- covers the bulk of what New Relic's
# integrations need.
resource "aws_iam_role_policy_attachment" "newrelic_readonly" {
  role       = aws_iam_role.newrelic_aws_role.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Trusted Advisor is explicitly NOT covered by ReadOnlyAccess per New
# Relic's own docs -- it needs AWSSupportAccess. Without this, every other
# integration below works fine but trusted_advisor silently returns nothing.
resource "aws_iam_role_policy_attachment" "newrelic_support_access" {
  role       = aws_iam_role.newrelic_aws_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSSupportAccess"
}

# Small inline policy for the extras New Relic's console flow calls out
# explicitly (budgets isn't in ReadOnlyAccess at all; the others are
# included here for parity/documentation even where ReadOnlyAccess already
# covers them, in case that policy's scope ever changes).
resource "aws_iam_role_policy" "newrelic_extra_permissions" {
  name = "NewRelicCloudIntegrationsExtras-${var.name_prefix}"
  role = aws_iam_role.newrelic_aws_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "config:BatchGetResourceConfig",
          "config:ListDiscoveredResources",
          "elasticache:DescribeCacheClusters",
          "tag:GetResources",
          "budgets:ViewBudget"
        ]
        Resource = "*"
      }
    ]
  })
}

# ------------------------------------------------------------
# Ingest key for Firehose, managed by Terraform instead of pasted in
# ------------------------------------------------------------
# This IS the credential that goes into the Firehose http_endpoint_
# configuration's access_key in firehose.tf. Keeping it Terraform-managed
# means it can be rotated by tainting/replacing this resource instead of
# hunting down a static key someone pasted in six months ago.
resource "newrelic_api_access_key" "newrelic_aws_access_key" {
  account_id  = var.newrelic_account_id
  key_type    = "INGEST"
  ingest_type = "LICENSE"
  name        = "Metric Stream Key for ${var.name_prefix}"
  notes       = "AWS Cloud Integrations Metric Stream Key (managed by Terraform)"
}

# ------------------------------------------------------------
# The actual account link + integrations enrollment
# ------------------------------------------------------------
resource "newrelic_cloud_aws_link_account" "this" {
  account_id             = var.newrelic_account_id
  arn                    = aws_iam_role.newrelic_aws_role.arn
  metric_collection_mode = var.metric_collection_mode
  name                   = "${var.name_prefix} ${var.metric_collection_mode == "PUSH" ? "metric stream" : "pull"}"

  depends_on = [
    aws_iam_role_policy_attachment.newrelic_readonly,
    aws_iam_role_policy_attachment.newrelic_support_access,
    aws_iam_role_policy.newrelic_extra_permissions,
  ]
}

# Polling-based integrations for services without metric-stream support.
# These run regardless of PUSH/PULL mode for metrics, per New Relic's
# guidance -- metric streams replace the CloudWatch-metrics polling, not
# these.
resource "newrelic_cloud_aws_integrations" "this" {
  account_id        = var.newrelic_account_id
  linked_account_id = newrelic_cloud_aws_link_account.this.id

  billing {}
  cloudtrail {}
  health {}
  trusted_advisor {}
  vpc {}
  x_ray {}
}
