"""
Fixture data for `python image_introspect.py --demo`.

Mimics real Docker Registry HTTP API v2 responses: manifests (including one
multi-arch manifest list, to exercise that code path), image config blobs
(Env/Labels), and one gzip'd tar layer blob containing /etc/os-release (to
exercise --scan-os-release without hitting a real registry).

Deliberately includes two cases where the "real" version disagrees with the
Nexus tag, to prove out the mismatch-detection path:
  - my-team/node-service    tagged 20-alpine, but NODE_VERSION inside is 18.x
  - my-team/golang-builder  tagged 1.21.13,   but GOLANG_VERSION inside is 1.22.x
"""

import gzip
import io
import tarfile


def _make_layer_blob(files):
    """Build an in-memory gzip'd tar containing the given {path: text} files."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


UBUNTU_OS_RELEASE = """NAME="Ubuntu"
VERSION="22.04.4 LTS (Jammy Jellyfish)"
ID=ubuntu
ID_LIKE=debian
VERSION_ID="22.04"
"""

ALPINE_OS_RELEASE = """NAME="Alpine Linux"
ID=alpine
VERSION_ID="3.19.1"
"""

# --------------------------------------------------------------------------
# Manifests, keyed by (nexus component name, reference) where reference is
# whatever tag or digest was requested.
# --------------------------------------------------------------------------

MANIFESTS = {
    # --- ubuntu-base: multi-arch manifest list -> amd64 sub-manifest ---
    ("my-team/ubuntu-base", "22.04"): {
        "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
        "manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}, "digest": "sha256:ubuntu-amd64-manifest"},
            {"platform": {"os": "linux", "architecture": "arm64"}, "digest": "sha256:ubuntu-arm64-manifest"},
        ],
    },
    ("my-team/ubuntu-base", "sha256:ubuntu-amd64-manifest"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-ubuntu"},
        "layers": [{"digest": "sha256:layer-ubuntu-rootfs"}],
    },

    # --- alpine-base: plain single manifest ---
    ("my-team/alpine-base", "3.19"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-alpine"},
        "layers": [{"digest": "sha256:layer-alpine-rootfs"}],
    },

    # --- node-service: MISMATCH — tag says 20-alpine, image actually has 18.x ---
    ("my-team/node-service", "20-alpine"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-node-mismatch"},
        "layers": [{"digest": "sha256:layer-node"}],
    },

    # --- node-service-alpine: matches ---
    ("my-team/node-service-alpine", "22"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-node22"},
        "layers": [{"digest": "sha256:layer-node22"}],
    },

    # --- ruby-service ---
    ("my-team/ruby-service", "3.1.6"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-ruby"},
        "layers": [{"digest": "sha256:layer-ruby"}],
    },

    # --- jvm-base: version only in a Label, no env var ---
    ("my-team/jvm-base", "17"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-jvm"},
        "layers": [{"digest": "sha256:layer-jvm"}],
    },

    # --- golang-builder: MISMATCH — tag says 1.21.13, image actually has 1.22.x ---
    ("my-team/golang-builder", "1.21.13"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-golang-mismatch"},
        "layers": [{"digest": "sha256:layer-golang"}],
    },

    # --- terraform-runner ---
    ("my-team/terraform-runner", "1.6.6"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-terraform"},
        "layers": [{"digest": "sha256:layer-terraform"}],
    },

    # --- jetty-app ---
    ("my-team/jetty-app", "11"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-jetty"},
        "layers": [{"digest": "sha256:layer-jetty"}],
    },

    # --- tomcat-app ---
    ("my-team/tomcat-app", "9"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-tomcat"},
        "layers": [{"digest": "sha256:layer-tomcat"}],
    },

    # --- nginx-proxy ---
    ("my-team/nginx-proxy", "1.26.2"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-nginx"},
        "layers": [{"digest": "sha256:layer-nginx"}],
    },

    # --- sonarqube-server: version only in a Label ---
    ("my-team/sonarqube-server", "2025.1.2"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-sonarqube"},
        "layers": [{"digest": "sha256:layer-sonarqube"}],
    },

    # --- cypress-e2e ---
    ("my-team/cypress-e2e", "13.6.1"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-cypress"},
        "layers": [{"digest": "sha256:layer-cypress"}],
    },

    # --- jmeter-perf ---
    ("my-team/jmeter-perf", "5.6.2"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-jmeter"},
        "layers": [{"digest": "sha256:layer-jmeter"}],
    },

    # --- harness-delegate: genuinely no version signal anywhere ---
    ("my-team/harness-delegate", "24.09.83428"): {
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:cfg-harness"},
        "layers": [{"digest": "sha256:layer-harness"}],
    },
}


# --------------------------------------------------------------------------
# Blobs, keyed by digest. dict = config JSON, bytes = layer tar.gz.
# --------------------------------------------------------------------------

BLOBS = {
    "sha256:cfg-ubuntu": {"config": {"Env": [], "Labels": {}}},
    "sha256:layer-ubuntu-rootfs": _make_layer_blob({"etc/os-release": UBUNTU_OS_RELEASE}),

    "sha256:cfg-alpine": {"config": {"Env": [], "Labels": {}}},
    "sha256:layer-alpine-rootfs": _make_layer_blob({"etc/os-release": ALPINE_OS_RELEASE}),

    "sha256:cfg-node-mismatch": {"config": {"Env": ["NODE_VERSION=18.20.4", "PATH=/usr/local/bin"], "Labels": {}}},
    "sha256:cfg-node22": {"config": {"Env": ["NODE_VERSION=22.9.0"], "Labels": {}}},

    "sha256:cfg-ruby": {"config": {"Env": ["RUBY_VERSION=3.1.6"], "Labels": {}}},

    "sha256:cfg-jvm": {"config": {"Env": [], "Labels": {"org.opencontainers.image.version": "17.0.12"}}},

    "sha256:cfg-golang-mismatch": {"config": {"Env": ["GOLANG_VERSION=1.22.5"], "Labels": {}}},

    "sha256:cfg-terraform": {"config": {"Env": ["TERRAFORM_VERSION=1.6.6"], "Labels": {}}},

    "sha256:cfg-jetty": {"config": {"Env": ["JETTY_VERSION=11.0.22"], "Labels": {}}},

    "sha256:cfg-tomcat": {"config": {"Env": ["TOMCAT_VERSION=9.0.91", "TOMCAT_MAJOR=9"], "Labels": {}}},

    "sha256:cfg-nginx": {"config": {"Env": ["NGINX_VERSION=1.26.2"], "Labels": {}}},

    "sha256:cfg-sonarqube": {"config": {"Env": [], "Labels": {"org.opencontainers.image.version": "2025.1.2"}}},

    "sha256:cfg-cypress": {"config": {"Env": ["CYPRESS_VERSION=13.6.1"], "Labels": {}}},

    "sha256:cfg-jmeter": {"config": {"Env": ["JMETER_VERSION=5.6.2"], "Labels": {}}},

    "sha256:cfg-harness": {"config": {"Env": [], "Labels": {}}},  # no signal at all — genuinely unverifiable
}
