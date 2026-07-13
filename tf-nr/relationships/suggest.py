"""
NerdGraph query/mutation strings.

IMPORTANT: New Relic's entity/relationship schema does shift between API
versions and account configurations. Before relying on this in production,
paste these into https://api.newrelic.com/graphiql (or your EU equivalent)
with your own API key and confirm the fields resolve for your account.
The `introspect_type` query below is provided so `nr-rel schema <TypeName>`
can check this for you at runtime.
"""

ENTITY_SEARCH_BY_TAG = """
query EntitySearchByTag($query: String!, $cursor: String) {
  actor {
    entitySearch(query: $query) {
      count
      results(cursor: $cursor) {
        nextCursor
        entities {
          guid
          name
          type
          entityType
          domain
          accountId
          tags {
            key
            values
          }
        }
      }
    }
  }
}
"""

ENTITY_WITH_RELATIONSHIPS = """
query EntityWithRelationships($guid: EntityGuid!) {
  actor {
    entity(guid: $guid) {
      guid
      name
      type
      entityType
      tags {
        key
        values
      }
      relationships {
        type
        source {
          entity {
            guid
            name
            type
          }
        }
        target {
          entity {
            guid
            name
            type
          }
        }
      }
    }
  }
}
"""

ENTITIES_WITH_RELATIONSHIPS_BATCH = """
query EntitiesWithRelationshipsBatch($guids: [EntityGuid]!) {
  actor {
    entities(guids: $guids) {
      guid
      name
      type
      entityType
      tags {
        key
        values
      }
      relationships {
        type
        source {
          entity {
            guid
            name
            type
          }
        }
        target {
          entity {
            guid
            name
            type
          }
        }
      }
    }
  }
}
"""

# User-defined ("custom") entity relationships: these are the two mutations
# NerdGraph exposes for manually curating relationships between entities.
# See: https://docs.newrelic.com/docs/apis/nerdgraph/examples/nerdgraph-relationships-api-tutorial/
CREATE_OR_REPLACE_RELATIONSHIP = """
mutation CreateOrReplaceRelationship($sourceEntityGuid: EntityGuid!, $targetEntityGuid: EntityGuid!, $type: EntityRelationshipUserDefinedType!) {
  entityRelationshipUserDefinedCreateOrReplace(
    sourceEntityGuid: $sourceEntityGuid
    targetEntityGuid: $targetEntityGuid
    type: $type
  ) {
    errors {
      message
      type
    }
  }
}
"""

DELETE_RELATIONSHIP = """
mutation DeleteRelationship($sourceEntityGuid: EntityGuid!, $targetEntityGuid: EntityGuid!, $type: EntityRelationshipUserDefinedType!) {
  entityRelationshipUserDefinedDelete(
    sourceEntityGuid: $sourceEntityGuid
    targetEntityGuid: $targetEntityGuid
    type: $type
  ) {
    errors {
      message
      type
    }
  }
}
"""

INTROSPECT_TYPE = """
query IntrospectType($name: String!) {
  __type(name: $name) {
    name
    kind
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""
