"""Nexus Repository client -- two independent pieces:

1. Looking up a deployed image's component record via Nexus's documented
   Search API, to get a real link to it:
     GET {base_url}/service/rest/v1/search?repository=...&name=...&version=...&format=docker
   https://help.sonatype.com/en/search-api.html
   This is a stable, versioned REST API -- not the Angular web UI's
   hash-routed URLs, which aren't documented and change between Nexus
   versions, so we don't try to construct those.

2. Optionally detecting an image's base image (off by default), by reading
   the OCI Distribution Spec registry API directly
   (GET /v2/<name>/manifests/<tag>), following the standard Bearer-token
   challenge/response flow that OCI-conformant registries use when Basic
   auth alone is rejected, and checking for the two official OCI
   base-image annotations:
     org.opencontainers.image.base.name / .base.digest
   https://github.com/opencontainers/image-spec/blob/main/annotations.md
   If your images are classic Docker v2 schema2 (not OCI format) or your
   build tooling doesn't set these, there's nothing to find -- this
   reports "not recorded" rather than guessing from layer history, which
   isn't reliable enough to present as fact.
"""

import requests

_SEARCH_PATH = '/service/rest/v1/search'
_BASE_NAME_ANNOTATION = 'org.opencontainers.image.base.name'
_BASE_DIGEST_ANNOTATION = 'org.opencontainers.image.base.digest'


def search_component(base_url, username, password, repository, image_name, tag, timeout=20):
    """Returns the raw component dict (with an 'assets' list) for one
    image:tag, or None if the search came back empty."""
    resp = requests.get(
        f'{base_url}{_SEARCH_PATH}',
        params={'repository': repository, 'name': image_name, 'version': tag, 'format': 'docker'},
        auth=(username, password) if username else None,
        timeout=timeout,
    )
    resp.raise_for_status()
    items = resp.json().get('items', [])
    return items[0] if items else None


def links_for_image(base_url, username, password, repository, image_name, tag):
    """Best-effort link set for one deployed image. Never raises -- a
    lookup failure just means fewer links on that row, not a broken
    report."""
    browse_url = f"{base_url.rstrip('/')}/#browse/browse:{repository}"
    asset_url = None
    try:
        component = search_component(base_url, username, password, repository, image_name, tag)
        if component and component.get('assets'):
            asset_url = component['assets'][0].get('downloadUrl')
    except Exception:
        pass
    return {'asset_url': asset_url, 'browse_url': browse_url}


def _get_registry_token(username, password, challenge_header, timeout=20):
    parts = {}
    for piece in challenge_header.replace('Bearer ', '', 1).split(','):
        if '=' in piece:
            k, v = piece.split('=', 1)
            parts[k.strip()] = v.strip().strip('"')
    realm = parts.get('realm')
    if not realm:
        return None
    resp = requests.get(
        realm, params={'service': parts.get('service'), 'scope': parts.get('scope')},
        auth=(username, password) if username else None, timeout=timeout,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get('token') or data.get('access_token')


def _registry_get(url, username, password, accept, timeout=20):
    headers = {'Accept': accept}
    resp = requests.get(url, headers=headers, auth=(username, password) if username else None, timeout=timeout)
    if resp.status_code == 401 and resp.headers.get('WWW-Authenticate', '').lower().startswith('bearer'):
        token = _get_registry_token(username, password, resp.headers['WWW-Authenticate'], timeout=timeout)
        if token:
            headers['Authorization'] = f'Bearer {token}'
            resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp


def detect_base_image(registry_host, username, password, image_name, tag, timeout=20):
    """Returns {'name': ..., 'digest': ...} if the image's manifest (or,
    as a fallback, its config's Labels) carries an OCI base-image
    annotation, else None. Never raises."""
    try:
        manifest_url = f'https://{registry_host}/v2/{image_name}/manifests/{tag}'
        accept = ('application/vnd.oci.image.manifest.v1+json, '
                  'application/vnd.docker.distribution.manifest.v2+json')
        manifest = _registry_get(manifest_url, username, password, accept, timeout=timeout).json()

        annotations = manifest.get('annotations') or {}
        name = annotations.get(_BASE_NAME_ANNOTATION)
        digest = annotations.get(_BASE_DIGEST_ANNOTATION)
        if name or digest:
            return {'name': name, 'digest': digest}

        # Fallback: some teams set this as a plain Docker LABEL instead of
        # a proper manifest annotation.
        config_digest = (manifest.get('config') or {}).get('digest')
        if not config_digest:
            return None
        config_url = f'https://{registry_host}/v2/{image_name}/blobs/{config_digest}'
        config_accept = 'application/vnd.oci.image.config.v1+json, application/vnd.docker.container.image.v1+json'
        config = _registry_get(config_url, username, password, config_accept, timeout=timeout).json()
        labels = ((config.get('config') or {}).get('Labels')) or {}
        name = labels.get(_BASE_NAME_ANNOTATION)
        digest = labels.get(_BASE_DIGEST_ANNOTATION)
        return {'name': name, 'digest': digest} if (name or digest) else None
    except Exception:
        return None
