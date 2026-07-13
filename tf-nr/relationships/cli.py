# Matching rules for reconciling AWS resources with New Relic entities.
#
# To support a NEW AWS resource kind later:
#   1. Add a fetch function in src/aws_client.py that returns AwsResource objects
#      with that `kind` (see existing ecs_cluster/eks_cluster/rds_instance fetchers).
#   2. Add a block here describing how to build match candidates for it.
# The matching engine itself (src/matcher.py) is generic and doesn't change.
#
# For each kind:
#   nr_entity_types: NR `entityType` values likely to represent this AWS
#     resource. Leave empty ([]) to consider ALL entities in the graph
#     (slower, but useful if you don't know the entity type yet -- run
#     `nr-rel schema` or check a report to find out, then narrow it down).
#   aws_name_fields: dotted paths into the AwsResource used as candidate
#     names ("tags.Name" reads resource.tags["Name"]).
#   nr_tag_keys: NR tag keys to pull as candidate names, in addition to
#     the entity's own `name`.
#   normalize: ordered text transforms applied to every candidate before
#     comparison. Supported ops: lowercase, strip_prefix:<str>,
#     strip_suffix:<str>, replace:<a>:<b>, strip_non_alnum.

ecs_cluster:
  nr_entity_types: ["AWSECSCLUSTERENTITY"]
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["aws.ecsClusterName", "label.Name"]
  normalize:
    - lowercase
    - "strip_prefix:arn:aws:ecs:"
    - "replace:_:-"

ecs_service:
  nr_entity_types: ["AWSECSSERVICEENTITY", "APM_APPLICATION_ENTITY"]
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["aws.ecsServiceName", "label.Name", "tags.service"]
  normalize:
    - lowercase
    - "replace:_:-"

eks_cluster:
  nr_entity_types: ["AWSEKSCLUSTERENTITY", "KUBERNETES_CLUSTER_ENTITY"]
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["aws.eksClusterName", "label.clusterName", "k8s.clusterName"]
  normalize:
    - lowercase
    - "replace:_:-"

rds_instance:
  nr_entity_types: ["AWSRDSDBINSTANCEENTITY"]
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["aws.rdsDbInstanceId", "label.Name"]
  normalize:
    - lowercase
    - "replace:_:-"

rds_cluster:
  nr_entity_types: ["AWSRDSDBCLUSTERENTITY"]
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["aws.rdsClusterId", "label.Name"]
  normalize:
    - lowercase
    - "replace:_:-"

# Fallback used for any kind not listed above.
_default:
  nr_entity_types: []
  aws_name_fields: ["id", "tags.Name"]
  nr_tag_keys: ["label.Name"]
  normalize:
    - lowercase
    - "replace:_:-"
