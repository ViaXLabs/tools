# Docker Image EOL Report

Generates an HTML report of your team's Docker images, grouped by how urgent
their upstream lifecycle status is:

- **Out of service** — already past end-of-life
- **Approaching EOL** — EOL within the warning window (default 180 days)
- **Supported** — fine for now
- **Needs review** — couldn't be auto-checked (version not recognized upstream,
  API error, or no data source configured yet)

## Quick start

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python eol_report.py --demo                                # try it with bundled sample data, no network
open report.html                                            # (or just double-click it)
```

Once you're happy with your `config/images.yaml`, drop `--demo` to hit live data:

```bash
python eol_report.py --config config/images.yaml --out report.html
```

## How it decides what "EOL" means, per image

Every image in `config/images.yaml` has a `source` field that says how to check it:

| `source`         | Used for                                                | How it works |
|------------------|----------------------------------------------------------|--------------|
| `endoflife`      | Ubuntu, Alpine, Node, Ruby, Go, Terraform, nginx, Tomcat, Jetty, JDK distros, SonarQube, and ~450 others | Live-queries `endoflife.date`'s API for that product's release cycles and reads the published EOL date |
| `latest_release` | Tools with **no formal EOL policy** — just "latest wins" (Cypress, JMeter) | Compares your pinned version's major number against the latest GitHub release; flags anything more than 1 major behind as unsupported |
| `manual`         | Products with no public API at all (e.g. commercial tools like Harness) | Reads `config/manual_sources.yaml`, a small file a human keeps updated. Flags itself if not re-verified in 120+ days |

**Why endoflife.date instead of scraping each vendor's site directly:** it's a
community-maintained aggregator (460+ products) that already does the work of
tracking each vendor's official release/support pages, and it's what tools
like Renovate and GitHub's own dependency tooling use under the hood. Building
and maintaining ~15 individual site-scrapers would be far more fragile — one
markup change on a vendor's docs page and that checker silently breaks. Every
row in the report links back to the source page it used, so you can always
verify. If your security/compliance process specifically requires primary-source
citations rather than an aggregator, that's a reasonable call — just say so and
the `endoflife` checker can be swapped for direct per-vendor lookups one product
at a time (start with whichever ones matter most for audit purposes).

**Cypress, JMeter, Harness genuinely don't publish EOL dates.** This isn't a
gap in the tool — these projects use a rolling support model (only the last
one or two versions are supported, no fixed retirement date). The
`latest_release` and `manual` checkers approximate "is this stale" as best as
that data allows; treat their output as a flag to investigate, not a hard fact
the way an Ubuntu EOL date is.

## Things to double check / adjust for your real setup

I made a few assumptions building the sample `config/images.yaml` — fix
whichever of these don't match your team:

1. **Java/JVM images**: endoflife.date tracks JDK *distributions* separately
   (`eclipse-temurin`, `amazon-corretto`, `oracle-jdk`, `redhat-build-of-openjdk`,
   `microsoft-build-of-openjdk`, `azul-zulu`, `sapmachine`, `ibm-semeru-runtime`).
   I defaulted to `eclipse-temurin`. Change `product:` to match what your JVM
   base images actually use.
2. **SonarQube**: endoflife.date splits this into `sonarqube-community` and
   `sonarqube-server` (community build vs. commercial). I assumed
   `sonarqube-server` — swap if you run the community edition.
3. **"Harness"**: I treated this as Harness.io CI/CD (delegate images), tracked
   via the `manual` checker since Harness doesn't publish a public EOL API. If
   you meant something else, just rename the `product` field.
4. **Every `current_version`** in the sample config is a placeholder — if
   you're pulling inventory from Nexus, ignore it entirely; see below.

## Pulling inventory from Nexus instead of hand-editing images.yaml

`nexus_inventory.py` queries Nexus for what you actually have and generates
`config/images.yaml` for you. Nexus knows *"my-team/node-service, tag
20-alpine exists"* — it doesn't know that means "Node.js 20", so
`config/product_map.yaml` supplies that mapping (glob pattern on the Nexus
image name -> product family). A starting map covering the stack you
described is already filled in — check the assumptions inside it, especially
the JDK distro and SonarQube community-vs-server line.

```bash
export NEXUS_USERNAME=svc-eol-report      # or export NEXUS_TOKEN=...
export NEXUS_PASSWORD='...'                # never pass credentials as CLI args

python nexus_inventory.py \
  --nexus-url https://nexus.internal.yourcompany.com \
  --repository docker-hosted \
  --out config/images.yaml
```

Try it first with `python nexus_inventory.py --demo` (no network, no
credentials needed) to see the shape of the output before pointing it at your
real instance.

**Two query modes**, since Nexus Docker repos are set up differently
everywhere — pick whichever matches your setup, or try `rest` first:

- `--mode rest` (default): Nexus's own REST API (`/service/rest/v1/search`),
  same host/port/auth as the Nexus web UI. "Current version" = the most
  recently *uploaded* tag matching that product's `tag_pattern` in
  `product_map.yaml`.
- `--mode docker_v2`: the standard Docker Registry API (`/v2/_catalog`,
  `/v2/<name>/tags/list`) — use this if your Docker repos are only reachable
  on a separate registry host/port. This API doesn't expose upload
  timestamps, so "current version" falls back to the highest semver tag
  instead of most-recently-pushed.

**Nothing is silently dropped.** Any Nexus image that doesn't match a
pattern in `product_map.yaml` is listed at the end of the run instead of
being skipped quietly — add a mapping for it if it should be tracked. Same
for images that matched a mapping but had no tag matching its `tag_pattern`
(e.g. only `latest`/`canary`/branch-name tags pushed so far).

**On "current version" = most-recently-pushed:** that's a heuristic, not a
guarantee — it assumes your team pushes the version that's actually in
service and doesn't leave newer unreleased tags sitting in Nexus longer than
older deployed ones. The next step below removes that assumption entirely by
checking the image itself rather than trusting the tag.

## Verifying against what's actually inside the image (recommended)

A tag is a claim, not a fact. `node-service:20-alpine` in Nexus doesn't
guarantee the image was actually built with Node 20 — it could have been
re-tagged, rebuilt from a stale layer cache, or mislabeled by hand. Nothing
about a registry search catches that.

`image_introspect.py` closes that gap: it pulls the real image manifest and
config directly from the registry (the same data `docker inspect` would show
— no docker daemon needed) and checks what's *actually* embedded, before any
EOL check happens.

```bash
python image_introspect.py \
  --in config/images.yaml \
  --registry-url https://docker.nexus.internal.yourcompany.com \
  --out config/images.verified.yaml \
  --report verification_report.html

python eol_report.py --config config/images.verified.yaml --out report.html
```

How it confirms the real version, per product (`config/introspection_rules.yaml`):

1. **ENV vars baked into the image** — most official upstream base images set
   one (`NODE_VERSION`, `RUBY_VERSION`, `TOMCAT_VERSION`, `JETTY_VERSION`...),
   and it survives into your image as long as your Dockerfile builds `FROM`
   it without stripping `ENV`.
2. **OCI labels** (`org.opencontainers.image.version`), if your CI sets one at
   build time. This is the single highest-leverage change you could make to
   your Dockerfiles — add that label and every future check on that image
   becomes exact instead of best-effort.
3. **`/etc/os-release`** — for Ubuntu/Alpine base images, neither of the above
   usually exists, so the only ground truth is reading this file out of the
   image's filesystem layers. That requires downloading layer data, so it's
   opt-in: pass `--scan-os-release` to enable it. Without the flag, these are
   reported as "unverifiable" rather than silently assumed correct.

**Where the tag and the image disagree, the verified value wins** for the
downstream EOL check, and the disagreement is flagged loudly — both in
`verification_report.html` and in the exit code (`2` if anything mismatched).
A wrong tag is usually optimistic, not conservative — the whole point is to
catch a `node-service` that's quietly running an EOL'd Node 18 while its tag
still claims a perfectly fine Node 20.

Try `python image_introspect.py --demo` to see this in action — the bundled
sample data includes exactly that scenario (a Node image whose tag says 20
but whose actual `NODE_VERSION` is 18.20.4), so you can see the mismatch flow
end to end before pointing it at your real registry.

**Full pipeline, chained:**

```bash
python nexus_inventory.py --nexus-url ... --repository docker-hosted --out config/images.raw.yaml
python image_introspect.py --in config/images.raw.yaml --registry-url ... --scan-os-release \
  --out config/images.verified.yaml --report verification_report.html
python eol_report.py --config config/images.verified.yaml --out report.html
```

## Running it monthly

This is a plain script, not a hosted service — it needs *something* to invoke
it on a schedule. Two common options:

**GitHub Actions** (if your images/config live in a repo) — see
`.github/workflows/eol-report.yml` for a ready-to-use monthly workflow that
runs the report and uploads `report.html` as a build artifact. Extend the
last step to post to Slack, email, or commit the report into a `reports/`
folder if you want it somewhere more permanent than the Actions UI.

**Cron**, on any machine/container that already runs scheduled jobs for your
team:

```cron
# Run at 8am on the 1st of every month
0 8 1 * * cd /path/to/docker-eol-report && python eol_report.py --out /var/www/reports/eol-$(date +\%Y-\%m).html
```

The script's exit code reflects severity (`0` = all clear, `1` = something
approaching EOL, `2` = something out of service), so you can also use it as a
gate in CI if you want a build to fail loudly when an image goes out of service.

## Extending the inventory

Add a new entry to `config/images.yaml` for any image line you want tracked.
If it's a product endoflife.date already tracks, check the slug at
`https://endoflife.date/api/all.json` and use `source: endoflife`. Otherwise
use `latest_release` (if it's on GitHub and has no EOL policy) or `manual`
(anything else) and add a corresponding entry to `config/manual_sources.yaml`.

## Files

```
eol_report.py                     Main script — checkers + HTML rendering + CLI
demo_fixtures.py                   Sample data for eol_report.py --demo
nexus_inventory.py                 Pulls current tags from Nexus -> images.yaml
nexus_demo_fixtures.py             Sample data for nexus_inventory.py --demo
image_introspect.py                 Verifies real image content against the tag
registry_demo_fixtures.py           Sample data for image_introspect.py --demo
config/images.yaml                 Hand-maintained inventory (skip if using Nexus)
config/product_map.yaml            Nexus image name -> product family mapping
config/introspection_rules.yaml    Where each product's real version lives in-image
config/manual_sources.yaml         Manually-tracked EOL data for non-API products
config/images.generated-example.yaml  Example of what nexus_inventory.py produces
requirements.txt                   pip dependencies
.github/workflows/                 Sample monthly GitHub Actions workflow
sample_report.html                 Example output from the hand-maintained config
sample_report_from_nexus.html       Example output from the Nexus-generated config
sample_report_verified.html         Example output after image verification
verification_report.html            Example tag-vs-actual-content verification report
```
