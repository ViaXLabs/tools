#!/usr/bin/env bash
# Ask IAM directly whether the resolved identity can perform a set of
# actions, instead of inferring it from CLI error text. Feed it the actions
# that showed up as FAIL in 02-command-matrix.sh.
#
# Usage: ./03-permission-simulate.sh [profile] [action1 action2 ...]
# If no actions are given, uses a default list matching 02-command-matrix.sh.

set -uo pipefail

PROFILE="${1:-${AWS_PROFILE:-default}}"
shift || true
ACTIONS=("$@")
if [ ${#ACTIONS[@]} -eq 0 ]; then
  ACTIONS=(sts:GetCallerIdentity sts:GetSessionToken iam:GetUser s3:ListAllMyBuckets \
           ec2:DescribeRegions ec2:DescribeInstances secretsmanager:ListSecrets \
           ssm:DescribeParameters ecr:DescribeRepositories logs:DescribeLogGroups)
fi

ARN=$(aws --profile "$PROFILE" sts get-caller-identity --query Arn --output text 2>&1)
if [[ "$ARN" != arn:aws* ]]; then
  echo "Could not resolve a caller identity ARN — fix credential resolution before"
  echo "running the simulator. sts get-caller-identity returned:"
  echo "$ARN"
  exit 1
fi
echo "Simulating as: $ARN"

# simulate-principal-policy requires the underlying IAM user/role ARN, not an
# assumed-role SESSION arn — convert if needed.
POLICY_ARN="$ARN"
if [[ "$ARN" == *":assumed-role/"* ]]; then
  ACCOUNT=$(echo "$ARN" | cut -d: -f5)
  ROLE=$(echo "$ARN" | sed -E 's#.*assumed-role/([^/]+)/.*#\1#')
  POLICY_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"
  echo "(assumed-role session detected — simulating against underlying role: $POLICY_ARN)"
fi
echo

aws --profile "$PROFILE" iam simulate-principal-policy \
  --policy-source-arn "$POLICY_ARN" \
  --action-names "${ACTIONS[@]}" \
  --resource-arns "*" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision,MatchedStatements:MatchedStatements[].SourcePolicyId}' \
  --output table

echo
echo "For a DENY, cross-check CloudTrail for the same action — errorMessage often"
echo "names the exact denying policy/SCP, which the simulator alone won't show:"
echo '  aws --profile '"$PROFILE"' cloudtrail lookup-events \'
echo '    --lookup-attributes AttributeKey=Username,AttributeValue=<session-name> \'
echo '    --max-results 20 --query "Events[?contains(CloudTrailEvent, '"'"'AccessDenied'"'"')]"'
