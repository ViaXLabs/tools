# Nexus Container Image Reporting — Design Notes

**Purpose of this doc:** a self-contained explanation of *how* to build the Nexus
→ two-CSV → Confluence reporting step of your Harness pipeline, written so it
can be handed to another AI/engineer who is picking this up cold. It covers
the Nexus API calls that actually matter, the tag-classification logic, the
data model for the two reports, the CSV "color and links" question (and its
real limits), and the failure modes that usually cause this exact pipeline to
go sideways.

Companion file: `nexus_image_report.py` — a runnable reference
implementation of everything below (Nexus polling → classification → CSV +
optional colored Confluence-table HTML).

---

## 1. What Nexus actually gives you

Nexus Repository 3 exposes this over `GET /service/rest/v1/search` and
`GET /service/rest/v1/search/assets`. Both are **paginated** with a
`continuationToken` — this is the #1 thing that silently breaks reports on
repos with "a ton of images": if the loop stops after page one, the report
looks complete but quietly only covers the newest N components.

### 1.1 Component search (one row per image:tag)

```
GET /service/rest/v1/search?repository=<repo>&format=docker&continuationToken=<token>
```

Returns something like:

```json
{
  "items": [
    {
      "id": "...",
      "repository": "docker-hosted",
      "format": "docker",
      "name": "platform/corretto-java",
      "version": "21.2.3-567GRE7",
      "assets": [
        {
          "downloadUrl": "https://nexus.example.com/repository/docker-hosted/v2/platform/corretto-java/manifests/21.2.3-567GRE7",
          "path": "v2/platform/corretto-java/manifests/21.2.3-567GRE7",
          "id": "...",
          "repository": "docker-hosted",
          "format": "docker",
          "checksum": { "sha1": "...", "sha256": "..." }
        }
      ]
    }
  ],
  "continuationToken": "abc123"
}
```

For Docker components, `name` = image name, `version` = tag — same generic
fields Nexus uses for every format. Keep paging (pass the returned
`continuationToken` back in as a query param) until it comes back `null`.

### 1.2 Asset search (where the *dates* actually live)

The component-level `assets[]` above is deliberately thin. The fields you
actually need for "when was this created / last updated" — `lastModified`,
`blobCreated`, `lastDownloaded`, `fileSize`, `uploader` — come back from the
**asset** endpoint:

```
GET /service/rest/v1/search/assets?repository=<repo>&format=docker&continuationToken=<token>
```

```json
{
  "items": [
    {
      "downloadUrl": "https://nexus.example.com/repository/docker-hosted/v2/platform/corretto-java/manifests/21.2.3-567GRE7",
      "path": "v2/platform/corretto-java/manifests/21.2.3-567GRE7",
      "id": "cGxhdGZvcm0=",
      "repository": "docker-hosted",
      "format": "docker",
      "checksum": { "sha256": "52f827f7...", "sha1": "65608834..." },
      "contentType": "application/vnd.docker.distribution.manifest.v2+json",
      "lastModified": "2026-08-14T15:10:04.582+00:00",
      "lastDownloaded": "2026-09-01T09:11:01.154+00:00",
      "uploader": "ci-pipeline-svc",
      "fileSize": 3992,
      "blobCreated": "2026-08-14T15:10:04.598+00:00",
      "docker": {}
    }
  ],
  "continuationToken": null
}
```

**Practical recommendation:** drive the report off `/search/assets`, filtered
to the manifest path (`.../manifests/<tag>`), rather than off `/search`. It's
one call type instead of two, and it's the one that actually has your dates.
Use `/search` only if you need the `group`/`name`/`version` grouping and are
willing to join it against asset data by `id`.

- `blobCreated` ≈ "when this exact tag was first pushed" (created)
- `lastModified` ≈ "last updated" (re-tag, re-push, metadata touch)
- `lastDownloaded` is a bonus "is anyone still pulling this" signal, useful
  for a staleness/cleanup column later if you want it

### 1.3 Nexus version matters

Nexus 3.88.0 moved search from Elasticsearch to SQL search, which changed
wildcard behavior. If the "Fed side" Nexus instance is on an older or much
newer build than what your working pipeline talks to, that's a real
candidate for why the same logic behaves differently there. Check with:

```
GET /service/rest/v1/status
```

or read `/service/rest/swagger.json` for the live surface on that instance.
Worth a five-minute sanity check before debugging the client logic further.

---

## 2. Classifying "clean" vs. "SHA-suffixed" tags

Given your example — `21.2.3` (clean) vs. `21.2.3-567GRE7` (dev build) — the
naive approach is "match semver." Don't do that. Your tags aren't all semver
(`corretto-21`, `alpine3.18-jre`, OS-family tags, etc.), so a strict semver
regex will misclassify half your clean tags as "weird" and reject them.

The actual distinguishing feature you described is **a trailing hyphenated
token that looks like a build/commit stamp** — short, mixes letters and
digits, not a recognized human-chosen qualifier.

### 2.1 Default heuristic

```
^(?P<base>.+)-(?P<suffix>[A-Za-z0-9]{5,12})$
```

...with the suffix accepted as a "dev stamp" only if it contains **both** a
digit and a letter (pure-digit suffixes like `-3` or `-18` are almost always
legitimate version parts, e.g. `alpine-3`; pure-letter suffixes are almost
always qualifiers, e.g. `-slim`, `-jre`, `-alpine`).

```python
import re

DEV_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<suffix>[A-Za-z0-9]{5,12})$")
KNOWN_QUALIFIERS = {
    "slim", "alpine", "jre", "jdk", "windows", "nanoserver",
    "bullseye", "bookworm", "focal", "jammy",
}

def classify_tag(tag: str) -> str:
    m = DEV_SUFFIX_RE.match(tag)
    if not m:
        return "clean"
    suffix = m.group("suffix")
    has_digit = any(c.isdigit() for c in suffix)
    has_alpha = any(c.isalpha() for c in suffix)
    if suffix.lower() in KNOWN_QUALIFIERS:
        return "clean"
    if has_digit and has_alpha:
        return "dev_build"
    return "clean"
```

### 2.2 Don't trust this blind — calibrate it first

Before wiring this into anything that publishes a report, run it as a
one-off against a full tag dump and eyeball the output:

```python
# one-time calibration pass — not part of the pipeline
from collections import Counter
tags = [...]  # pull every distinct tag you have
print(Counter(classify_tag(t) for t in tags))
# then spot-check 20-30 from each bucket
```

Different platform teams will have different conventions, and you have "a
ton of images" — a 2% misclassification rate is invisible in a code review
but very visible on a Confluence page someone actually reads. Tune
`KNOWN_QUALIFIERS` and the length bounds against your real data, then treat
the regex as config (env var / small YAML), not a hardcoded constant, so
whoever inherits this next doesn't have to redeploy to adjust it.

### 2.3 If you want it bulletproof instead of heuristic

If your platform team's dev-build tagging is consistent (e.g., always a git
short-SHA, always exactly 7 lowercase hex chars, always appended by the same
CI step), replace the heuristic with an exact match for that one known
pattern instead — it'll be far more precise than any general-purpose
heuristic. Worth five minutes to check with them before assuming the fuzzy
version is necessary.

---

## 3. Report data model

One row per **tag** (not per asset — a tag can have multiple assets; see
§5.3 on de-duplication). Suggested columns for both reports:

| Column | Source | Notes |
|---|---|---|
| Repository | `repository` | which Nexus docker repo |
| Image Name | `name` | e.g. `platform/corretto-java` |
| Tag | `version` | e.g. `21.2.3-567GRE7` |
| Classification | computed | `clean` / `dev_build` |
| Digest | `checksum.sha256` | image content digest |
| Created | `blobCreated` | first push of this tag |
| Last Updated | `lastModified` | most recent push/touch |
| Last Pulled | `lastDownloaded` | may be null — see §5.4 |
| Size (MB) | `fileSize / 1e6` | manifest size, not full image — see note below |
| Age (days) | computed from `lastModified` | for staleness sorting |
| Nexus Link | constructed | direct browse URL, see §4 |
| New Relic Link | constructed | see §4 |

**Note on size:** the manifest asset's `fileSize` is the manifest JSON's
size, not the compressed image size. If "how big is this image" matters for
the report, sum the referenced layer blob sizes instead, or pull it from the
registry's `Content-Length` on a HEAD request — worth deciding whether that
level of detail is in scope before you build it.

### 3.1 The two reports

- **Report A — "Clean Tag Catalog":** rows where `Classification == clean`.
  This is your "safe to reference in a runbook / promote" list.
- **Report B — "Full Image Catalog":** every row, with the `Classification`
  column intact. Don't build this as a separate query — pull once, write
  twice (filtered vs. unfiltered). Two API sweeps of the same data doubles
  your Nexus load for no reason.

---

## 4. The CSV "color and links" question — read this before building it

Worth being direct about this up front: **a CSV file cannot store cell
color.** CSV is comma-separated plain text — there's no such thing as a
"colored cell" in the format, the same way a `.txt` file can't be bold. That
isn't a creativity limit, it's the file format. Whatever produced
"colorful CSVs" you may have seen was actually one of the options below
wearing a `.csv` label loosely. Three real ways to get the effect you want
in Confluence:

### Option A — plain CSV + a status column, colored by Confluence itself
Keep the two files as plain CSV, but make sure the `Classification` column
(and maybe an `Age (days)` bucket) is there. If your Confluence side uses a
macro like **Table Filter and Charts for Confluence** (Stiltsoft) or
similar, that macro's *conditional formatting rules* — configured once, in
Confluence, not regenerated every run — can color whole rows based on that
column's value. This is the lowest-effort option if that macro (or an
equivalent) is already in play, since your Harness template stays a CSV
consumer and nothing about the generation step changes.

### Option B — skip CSV for the *rendered* page, publish Confluence storage format directly
If your Harness→Confluence step can accept a raw page body instead of (or
alongside) a CSV attachment, generate the table as **Confluence storage
format** (their XHTML-ish dialect) with inline `style="background-color:..."`
and real `<a href="...">` tags. This is the only option that gives you
guaranteed color and guaranteed clickable links with zero dependency on
which Confluence macros happen to be installed. Trade-off: it's now HTML
generation instead of CSV generation, and if your existing "black box"
Confluence template is specifically built to ingest a CSV attachment, this
may not fit without changing that template too.

### Option C — Excel-flavored CSV with `HYPERLINK()` formulas
`=HYPERLINK("https://nexus.example.com/...", "view")` in a cell — opens as a
clickable link *if a human downloads the CSV and opens it in Excel or
Sheets*. No color (formulas don't carry formatting either), and Confluence
will render the literal formula text, not a link, if it just displays the
raw CSV. Only useful for the downloadable-artifact use case, not the
in-Confluence view.

**Recommendation:** the reference script below produces Option A by default
(clean CSVs with a `Classification` column, plus plain URL columns for Nexus
and New Relic that auto-link in most viewers) and also includes a function
that emits Option B's HTML as an alternative, in case your Confluence
template turns out to accept a body/storage-format input. Pick based on what
your existing "black box" template actually does with its input — that's the
one part of this I can't see from here.

---

## 5. Things that commonly break this exact pipeline

1. **Pagination stops after page one.** Silent — the report just looks
   complete with fewer rows than reality. Always loop until
   `continuationToken` is `null`.
2. **Assuming all tags are semver.** A generic semver parser will throw or
   silently drop tags like `corretto-21` or `ubuntu-22.04`. Classify by
   string pattern (§2), don't parse as a version number unless you also
   handle the parse failure as "clean, just not numeric."
3. **One row per asset instead of per tag.** A single pushed tag can have a
   manifest asset plus config/layer blob assets. If you don't filter to the
   manifest path (`.../manifests/<tag>`) or de-duplicate by
   `(repository, name, version)`, the report double- or triple-counts images
   and the dates get muddled (blob `blobCreated` dates reflect layer reuse
   across images, not the tag's own push date).
4. **Multi-arch images.** A single tag can point to a manifest *list*
   referencing multiple platform-specific manifests (amd64/arm64/etc). If
   your registry uses these, decide up front whether you want one report row
   per tag (recommended — dedupe by tag, ignore the per-arch children) or one
   per underlying manifest, and be consistent, or the "all images" count will
   drift depending on which images happen to be multi-arch.
5. **Group repositories.** If Nexus is queried against a `group`-type docker
   repo rather than the underlying `hosted` repo, results may reflect
   whatever's aggregated through the group (including proxied upstream
   content) rather than just what your platform team pushed. Point the
   search at the `hosted` repository name directly unless you specifically
   want the group's merged view.
6. **`lastDownloaded` is often null.** Not every asset has been pulled since
   last stats reset, or download tracking may be off for that repo. Treat it
   as optional/nullable in the data model, not a required field.
7. **Nexus version drift between environments** (§1.3) — the same query
   logic can behave differently pre/post the 3.88.0 search engine change.

---

## 6. New Relic links

This part is templated because the actual link depends on how your New
Relic account is set up — account ID, whether container image tag is
tracked as an attribute (commonly `containerImage` or a custom tag on
`K8sContainerSample` / `ProcessSample` if you're using the Kubernetes or
infrastructure integration), and which dashboard or Query Builder view you
want to land on. A generic pattern:

```
https://one.newrelic.com/nrql-console?accountId=<ACCOUNT_ID>&query=<url-encoded NRQL>
```

with an NRQL query like:

```sql
SELECT * FROM K8sContainerSample WHERE containerImage LIKE '%<image>:<tag>%' SINCE 1 day ago
```

Two things to confirm on your end before wiring this in: (1) the actual
attribute name your NR agent populates with the image reference — it varies
by integration — and (2) your NR account ID. Once you have those two, the
link construction is a one-line f-string; see `build_new_relic_link()` in
the reference script, which currently uses obvious placeholders you'll want
to swap in.

---

## 7. Where this fits in the Harness pipeline

Since the Nexus connectivity and the Confluence-publish template are both
already solved on your end, the piece this doc is about is the step in
between: a script step (Python, per the reference implementation) that:

1. Reads repo names / Nexus base URL / credentials from pipeline
   variables (already working on your side)
2. Runs the paginate → classify → build-rows logic in §1–§3
3. Writes `report_clean_tags.csv` and `report_all_images.csv` to a workspace
   path
4. Hands those two file paths to your existing Confluence-publish template
   as its input artifacts

Nothing about your Confluence template needs to change under Option A. It
only needs to change if you go with Option B (§4) and want it to accept a
storage-format body instead of/in addition to CSV attachments.
