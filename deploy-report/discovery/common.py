"""Small helpers shared by the ECS and EKS discovery modules."""

import re


def get_tag_ci(tags: dict, key: str):
    """Case-insensitive lookup in a plain {key: value} tag dict."""
    if not tags or not key:
        return None
    key_lower = key.lower()
    for k, v in tags.items():
        if k.lower() == key_lower:
            return v
    return None


# Heuristics for pulling a commit SHA out of a Docker image tag, tried in order.
_FULL_TAG_SHA = re.compile(r'^[0-9a-f]{7,40}$', re.IGNORECASE)
_SUFFIX_SHA = re.compile(r'[-_.]g?([0-9a-f]{7,40})$', re.IGNORECASE)
_ANY_SHA = re.compile(r'([0-9a-f]{7,40})', re.IGNORECASE)


def extract_sha(tag: str, pattern: str = None):
    """Best-effort extraction of a git commit SHA from an image tag.

    Tries, in order:
      1. the whole tag is a hex SHA                    e.g. "a1b2c3d"
      2. the tag ends in a hex SHA after a separator    e.g. "v1.4.2-g1a2b3c4"
      3. a custom regex supplied via config             e.g. "build-142-a1b2c3d"
      4. any hex-looking substring, as a last resort (highest false-positive risk)

    Returns None if nothing plausible is found -- callers should treat that
    as "couldn't determine the commit", not as an error.
    """
    if not tag:
        return None
    if _FULL_TAG_SHA.match(tag):
        return tag.lower()
    m = _SUFFIX_SHA.search(tag)
    if m:
        return m.group(1).lower()
    if pattern:
        m = re.search(pattern, tag, re.IGNORECASE)
        if m:
            return (m.group(1) if m.groups() else m.group(0)).lower()
    m = _ANY_SHA.search(tag)
    if m:
        return m.group(1).lower()
    return None


def containers_from_task_def(task_def: dict):
    """Extract [{name, image, tag}, ...] from an ECS describe_task_definition
    response's 'taskDefinition' object. Shared by live discovery and history
    reconstruction so both treat image/tag parsing identically."""
    out = []
    for c in task_def.get('containerDefinitions', []):
        image = c.get('image', '')
        last_segment = image.rsplit('/', 1)[-1]
        tag = last_segment.split(':', 1)[1] if ':' in last_segment else 'latest'
        out.append({'name': c.get('name'), 'image': image, 'tag': tag})
    return out


def split_image_reference(image_uri: str):
    """Split 'registry.host:port/path/to/image:tag' into
    (registry_host, image_path, tag). A leading segment counts as a
    registry host only if it looks like one (has a '.', a ':', or is
    'localhost') -- the same heuristic Docker itself uses, since
    'library/nginx:latest' has no registry host but 'nexus.co:8083/x:latest'
    does."""
    if not image_uri:
        return None, None, None
    without_digest = image_uri.split('@')[0]
    first_segment, sep, rest = without_digest.partition('/')
    if not sep:
        registry_host, image_path = None, first_segment
    elif '.' in first_segment or ':' in first_segment or first_segment == 'localhost':
        registry_host, image_path = first_segment, rest
    else:
        registry_host, image_path = None, without_digest
    if ':' in image_path.rsplit('/', 1)[-1]:
        image_path, tag = image_path.rsplit(':', 1)
    else:
        tag = 'latest'
    return registry_host, image_path, tag


def guess_repo_name(image_uri: str):
    """Derive a likely repo name from an image URI, e.g.

    123456789012.dkr.ecr.us-east-1.amazonaws.com/payments-api:abc123 -> payments-api
    """
    if not image_uri:
        return None
    path = image_uri.split('@')[0]  # strip a digest suffix if present
    last_segment = path.rsplit('/', 1)[-1]
    if ':' in last_segment:
        last_segment = last_segment.split(':', 1)[0]
    return last_segment or None
