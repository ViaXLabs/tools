#!/bin/sh
# bulk-migrate-nexus-to-ecr.sh
#
# Bulk-migrates images from Nexus into AWS ECR, driven by a CSV report/list.
# For each row: docker pull from Nexus -> docker tag -> docker push to ECR.
# Built for backfilling ECR with everything that's already sitting in Nexus.
#
# INPUT_FILE format (CSV; header row, '#' comments, and blank lines are all
# skipped automatically). Only column 1 is required:
#
#   nexus_image,ecr_repo_name,ecr_tag
#   nexus.company.com/docker-hosted/service-a:1.4.2,,
#   nexus.company.com/docker-hosted/service-b:2.0.0,team/service-b,2.0.0
#
# If ecr_repo_name / ecr_tag are blank, they're derived from the Nexus image
# path and tag. A plain one-column list (no commas at all) also works fine.
#
# Required env vars:
#   NEXUS_REGISTRY          - e.g. nexus.company.com or nexus.company.com:8082
#   NEXUS_USERNAME
#   NEXUS_PASSWORD
#   AWS_ACCESS_KEY_ID
#   AWS_SECRET_ACCESS_KEY
#   AWS_REGION
#   AWS_ACCOUNT_ID           - target account, e.g. your non-prod account
#   INPUT_FILE               - path to the CSV report
#
# Optional:
#   CREATE_REPO_IF_MISSING  - true (default) / false
#   SKIP_IF_EXISTS          - true (default) / false - skip tags already in ECR
#   CLEANUP_AFTER_PUSH      - true (default) / false - docker rmi after each push
#   DRY_RUN                 - false (default) / true - print actions, do nothing
#   RESULTS_FILE            - default ./ecr-bulk-migration-results.csv
#   MAX_RETRIES             - default 3 (applies to both pull and push)
#   RETRY_SLEEP_SECONDS     - default 5
#
# Exit code is non-zero if anything failed, so a CI step will show red
# even though most images may have gone through fine - check RESULTS_FILE
# for the per-image breakdown either way.

set -eu

: "${NEXUS_REGISTRY:?must set NEXUS_REGISTRY}"
: "${NEXUS_USERNAME:?must set NEXUS_USERNAME}"
: "${NEXUS_PASSWORD:?must set NEXUS_PASSWORD}"
: "${AWS_REGION:?must set AWS_REGION}"
: "${AWS_ACCOUNT_ID:?must set AWS_ACCOUNT_ID}"
: "${INPUT_FILE:?must set INPUT_FILE}"

CREATE_REPO_IF_MISSING="${CREATE_REPO_IF_MISSING:-true}"
SKIP_IF_EXISTS="${SKIP_IF_EXISTS:-true}"
CLEANUP_AFTER_PUSH="${CLEANUP_AFTER_PUSH:-true}"
DRY_RUN="${DRY_RUN:-false}"
RESULTS_FILE="${RESULTS_FILE:-./ecr-bulk-migration-results.csv}"
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_SLEEP_SECONDS="${RETRY_SLEEP_SECONDS:-5}"

if [ ! -f "$INPUT_FILE" ]; then
  echo "ERROR: input file not found: $INPUT_FILE" >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws-cli not found, installing..."
  if command -v apk >/dev/null 2>&1; then
    apk add --no-cache aws-cli
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq awscli
  else
    echo "ERROR: no apk/apt-get available to install aws-cli. Use a step image that already has it." >&2
    exit 1
  fi
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging in to Nexus (${NEXUS_REGISTRY})..."
echo "${NEXUS_PASSWORD}" | docker login --username "${NEXUS_USERNAME}" --password-stdin "${NEXUS_REGISTRY}"

echo "Logging in to ECR (${ECR_REGISTRY})..."
ECR_PASSWORD=$(aws ecr get-login-password --region "${AWS_REGION}")
echo "${ECR_PASSWORD}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# Splits a full image reference into REGISTRY_HOST / REPO_PATH / REPO_TAG,
# correctly ignoring a registry port (e.g. host:5000) when looking for the tag.
parse_image_ref() {
  ref="$1"
  last_component="${ref##*/}"
  if [ "$last_component" = "$ref" ]; then
    path_prefix=""
  else
    path_prefix="${ref%/*}/"
  fi
  case "$last_component" in
    *:*)
      REPO_TAG="${last_component##*:}"
      repo_last="${last_component%:*}"
      ;;
    *)
      REPO_TAG="latest"
      repo_last="$last_component"
      ;;
  esac
  full_no_tag="${path_prefix}${repo_last}"
  REGISTRY_HOST="${full_no_tag%%/*}"
  case "$full_no_tag" in
    */*) REPO_PATH="${full_no_tag#*/}" ;;
    *)   REPO_PATH="$full_no_tag" ;;
  esac
}

# retry <max_attempts> <cmd...>
retry() {
  max_attempts="$1"; shift
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if "$@"; then
      return 0
    fi
    echo "  attempt ${attempt}/${max_attempts} failed, retrying in ${RETRY_SLEEP_SECONDS}s..."
    attempt=$((attempt + 1))
    sleep "$RETRY_SLEEP_SECONDS"
  done
  return 1
}

echo "nexus_image,ecr_repo,ecr_tag,status,message" > "$RESULTS_FILE"

total=0
succeeded=0
skipped=0
failed=0
failed_list=""

while IFS=',' read -r nexus_image ecr_repo_override ecr_tag_override _rest; do
  case "$nexus_image" in
    ""|"#"*|"nexus_image") continue ;;
  esac

  total=$((total + 1))
  nexus_image=$(echo "$nexus_image" | sed 's/^ *//;s/ *$//')
  ecr_repo_override=$(echo "${ecr_repo_override:-}" | sed 's/^ *//;s/ *$//')
  ecr_tag_override=$(echo "${ecr_tag_override:-}" | sed 's/^ *//;s/ *$//')

  parse_image_ref "$nexus_image"
  ecr_repo="${ecr_repo_override:-$REPO_PATH}"
  ecr_tag="${ecr_tag_override:-$REPO_TAG}"
  ecr_image="${ECR_REGISTRY}/${ecr_repo}:${ecr_tag}"

  echo ""
  echo "[$total] ${nexus_image} -> ${ecr_image}"

  if [ "$DRY_RUN" = "true" ]; then
    echo "  DRY RUN: would pull, tag, and push"
    echo "${nexus_image},${ecr_repo},${ecr_tag},dry-run,none" >> "$RESULTS_FILE"
    continue
  fi

  if [ "$SKIP_IF_EXISTS" = "true" ]; then
    if aws ecr describe-images --repository-name "$ecr_repo" --image-ids imageTag="$ecr_tag" \
        --region "$AWS_REGION" >/dev/null 2>&1; then
      echo "  already in ECR, skipping"
      skipped=$((skipped + 1))
      echo "${nexus_image},${ecr_repo},${ecr_tag},skipped,already exists in ECR" >> "$RESULTS_FILE"
      continue
    fi
  fi

  if ! retry "$MAX_RETRIES" docker pull "$nexus_image"; then
    echo "  FAILED to pull from Nexus after ${MAX_RETRIES} attempts"
    failed=$((failed + 1))
    failed_list="${failed_list}${nexus_image} (pull failed)
"
    echo "${nexus_image},${ecr_repo},${ecr_tag},failed,pull from Nexus failed" >> "$RESULTS_FILE"
    continue
  fi

  if [ "$CREATE_REPO_IF_MISSING" = "true" ]; then
    if ! aws ecr describe-repositories --repository-names "$ecr_repo" --region "$AWS_REGION" >/dev/null 2>&1; then
      echo "  creating ECR repository: $ecr_repo"
      aws ecr create-repository \
        --repository-name "$ecr_repo" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true \
        --image-tag-mutability IMMUTABLE >/dev/null
    fi
  fi

  docker tag "$nexus_image" "$ecr_image"

  if ! retry "$MAX_RETRIES" docker push "$ecr_image"; then
    echo "  FAILED to push to ECR after ${MAX_RETRIES} attempts"
    failed=$((failed + 1))
    failed_list="${failed_list}${nexus_image} (push failed)
"
    echo "${nexus_image},${ecr_repo},${ecr_tag},failed,push to ECR failed" >> "$RESULTS_FILE"
    continue
  fi

  echo "  pushed OK"
  succeeded=$((succeeded + 1))
  echo "${nexus_image},${ecr_repo},${ecr_tag},success,none" >> "$RESULTS_FILE"

  if [ "$CLEANUP_AFTER_PUSH" = "true" ]; then
    docker rmi "$nexus_image" "$ecr_image" >/dev/null 2>&1 || true
  fi

done < "$INPUT_FILE"

echo ""
echo "================ Summary ================"
echo "Total:     $total"
echo "Succeeded: $succeeded"
echo "Skipped:   $skipped"
echo "Failed:    $failed"
echo "Results written to: $RESULTS_FILE"

if [ "$failed" -gt 0 ]; then
  echo ""
  echo "Failed images:"
  printf '%s' "$failed_list"
  exit 1
fi
