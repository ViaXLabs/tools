#!/usr/bin/env bash
# scripts/new-environment.sh
#
# Scaffolds a new environment (test/stage/prod) by copying
# terraform/live/dev/ and rewriting every "dev"-specific string that has
# to change: backend.tf state keys, remote_state.tf lookups, and the
# hardcoded environment = "dev" in each main.tf.
#
# This does NOT fill in real values (VPC ids, EKS cluster name, ALB
# target groups, image URIs, Nexus secret ARN) -- those are still
# REPLACE_ME in the new environment's .tfvars files, same as they
# started out in dev/. Run scripts/check-placeholders.sh afterward to
# find all of them in one pass.
#
# Usage:
#   ./scripts/new-environment.sh test
#   ./scripts/new-environment.sh stage
#   ./scripts/new-environment.sh prod

set -euo pipefail

ENV_NAME="${1:-}"

if [ -z "$ENV_NAME" ]; then
  echo "Usage: $0 <environment-name>"
  echo "Example: $0 test"
  exit 1
fi

if [[ ! "$ENV_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "Environment name must be lowercase letters, numbers, and hyphens only (got: $ENV_NAME)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/terraform/live/dev"
DEST_DIR="$REPO_ROOT/terraform/live/$ENV_NAME"

if [ ! -d "$SRC_DIR" ]; then
  echo "Expected to find $SRC_DIR -- run this from a checkout that still has terraform/live/dev/"
  exit 1
fi

if [ -d "$DEST_DIR" ]; then
  echo "$DEST_DIR already exists -- refusing to overwrite. Remove it first if you want to regenerate it."
  exit 1
fi

echo "Copying $SRC_DIR -> $DEST_DIR ..."
cp -r "$SRC_DIR" "$DEST_DIR"

echo "Rewriting dev-specific strings for '$ENV_NAME' ..."

# backend.tf and remote_state.tf: state key paths (psa/dev/... -> psa/<env>/...)
find "$DEST_DIR" -name "*.tf" -exec sed -i.bak "s#psa/dev/#psa/$ENV_NAME/#g" {} \;

# main.tf files: the hardcoded environment = "dev" module argument
find "$DEST_DIR" -name "main.tf" -exec sed -i.bak "s/environment[[:space:]]*=[[:space:]]*\"dev\"/environment           = \"$ENV_NAME\"/g" {} \;

# Header comments: path references (terraform/live/dev/...) and prose
# ("the dev environment") copied verbatim from dev/ would otherwise now
# be wrong -- e.g. a comment inside terraform/live/test/foundation/main.tf
# that still says "terraform/live/dev/foundation" is actively misleading,
# not just stale. Fix both forms.
find "$DEST_DIR" -name "*.tf" -exec sed -i.bak "s#terraform/live/dev/#terraform/live/$ENV_NAME/#g" {} \;
find "$DEST_DIR" -name "*.tf" -exec sed -i.bak "s/\bdev environment\b/$ENV_NAME environment/g" {} \;
find "$DEST_DIR" -name "*.tf" -exec sed -i.bak "s/represents the dev\b/represents the $ENV_NAME/g" {} \;

# Clean up sed's .bak backup files
find "$DEST_DIR" -name "*.bak" -delete

echo
echo "Done. Created terraform/live/$ENV_NAME/ with:"
find "$DEST_DIR" -type f | sed "s#$REPO_ROOT/#  #"
echo
echo "Still needed before this applies cleanly:"
echo "  1. Fill in every REPLACE_ME in terraform/live/$ENV_NAME/*/terraform.tfvars"
echo "     (real VPC/subnet IDs, EKS cluster name, ALB target group ARNs,"
echo "      Nexus pull-credentials secret ARN, New Relic license key ARN)"
echo "  2. Add a matching input set: copy .harness/input-sets/dev.yaml to"
echo "     .harness/input-sets/$ENV_NAME.yaml and update its 'value: dev' lines"
echo "  3. Run ./scripts/check-placeholders.sh terraform/live/$ENV_NAME to confirm"
echo "  4. If this is stage or prod: add a HarnessApproval step to the CD"
echo "     pipelines before the terraform-apply steps run for this environment"
echo "     (see the note in .harness/input-sets/stage.yaml)"
