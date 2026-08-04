#!/usr/bin/env bash
# Run this on a machine WITH internet access - your laptop, a build box, a
# CI runner - NOT on the bastion. It vendors boto3/click and every
# dependency directly into ./vendor as plain importable packages (not
# wheels), so the bastion needs zero pip installs and zero internet access.
#
# Many bastions/jumpboxes already have python3 and either boto3 or the AWS
# CLI preinstalled. This script is only needed if yours doesn't, or if you
# want awsx fully self-contained regardless of what's already there.
#
# Usage:
#   ./scripts/build_offline_bundle.sh [python-version] [platform-tag]
#
# Examples:
#   ./scripts/build_offline_bundle.sh 3.11 manylinux2014_x86_64   # typical Amazon Linux 2023 bastion
#   ./scripts/build_offline_bundle.sh 3.9  manylinux2014_aarch64  # Graviton bastion
#
# Output: awsx-offline-bundle.tar.gz in the repo root. Copy that one file to
# the bastion (scp, S3, whatever your bastion access pattern is) and run
# scripts/install_offline.sh there.

set -euo pipefail

PYVER="${1:-3.11}"
PLATFORM="${2:-manylinux2014_x86_64}"

cd "$(dirname "$0")/.."
rm -rf vendor
mkdir -p vendor

echo "Vendoring boto3 + click for Python ${PYVER} / ${PLATFORM} ..."
pip install \
  --target vendor \
  --platform "${PLATFORM}" \
  --python-version "${PYVER}" \
  --only-binary=:all: \
  --no-deps \
  boto3 botocore s3transfer jmespath python-dateutil urllib3 six click

# --no-deps above means we listed every dependency explicitly (boto3's own
# transitive deps as of writing). If a future boto3 release adds a new
# dependency, drop --no-deps once to pull the full tree, confirm what
# landed in vendor/, then pin the explicit list again.

echo "Bundling project + vendored deps ..."
tar -czf awsx-offline-bundle.tar.gz \
  awsx pyproject.toml README.md scripts vendor

echo
echo "Done: awsx-offline-bundle.tar.gz"
echo "Copy this file to the bastion, then run scripts/install_offline.sh there."
