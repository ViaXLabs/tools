# INTEGRATION.md

This document is written to be followed literally and in order, by
whoever or whatever (human or automated agent) is merging this scaffold
into the real PSA repository. It does not assume you can see this
scaffold's author's reasoning beyond what's written here and in
README.md -- if something isn't covered below, stop and ask a human
rather than guessing.

## 0. What this is, and what it is not

This is a **scaffold**, not a finished, tested deliverable. It was built
and checked in an environment with no network access and no `terraform`
or `helm` binaries available, so:

- It IS: structurally consistent (every module call has the right
  arguments, every file references real files, both apps genuinely run),
  heavily commented, and validated as far as offline checks can go (see
  `scripts/validate.sh`).
- It is NOT: something that has been run through `terraform validate`,
  `terraform plan`, or `helm template` against a real backend. It is
  also NOT exported from a live Harness account -- the `.harness/*.yaml`
  files are a best-effort structural approximation of Harness's step
  schema, not a guaranteed-correct export.

Do not treat successful completion of the steps below as proof this
works end-to-end in your real environment. Step 6 below is where that
gets found out.

## 1. Before touching anything: inventory what already exists

The real PSA repo almost certainly already has *some* of these paths
(at minimum, an existing Python app, per prior conversation). For each
top-level directory this scaffold provides --
`apps/`, `terraform/`, `charts/`, `.harness/`, `scripts/` -- check
whether it already exists in the target repo:

- **If a top-level directory does NOT exist in the target repo:** copy
  it in wholesale from this scaffold. No merge needed.
- **If a top-level directory DOES exist in the target repo:** do not
  overwrite it wholesale. Go file-by-file per the sections below.

## 2. `apps/` -- likely a real conflict, handle carefully

The real repo probably already has an existing Python app (and possibly
files at `apps/python-hello/` or similar, from before this scaffold's
naming convention existed).

- If the real repo's existing Python app lives somewhere other than
  `apps/psa-python/`: **do not delete or move it automatically.** Flag
  it for a human to decide whether to rename/relocate it to match this
  scaffold's `psa-<language>` convention, or whether this scaffold's
  `apps/psa-python/` should be discarded in favor of the real one.
- `apps/psa-java/` is new (Java didn't exist before this scaffold) --
  safe to add as-is if the path doesn't already exist.
- Never silently merge two different `app.py`/`Application.java` files.
  If both exist, stop and ask a human which one is authoritative.

## 3. `terraform/` -- almost certainly a real conflict

Per prior conversation, the real repo already has Terraform for both
ECS and EKS, described as "messy" and "all thrown under the EKS part."
This scaffold's `terraform/modules/` and `terraform/live/dev/` structure
is a **replacement proposal**, not something to merge line-by-line with
whatever already exists.

1. Do not run `terraform apply` with anything in this section until a
   human has reviewed it. Existing state files in the real repo's
   current structure represent real, already-provisioned AWS resources
   -- applying this scaffold's structure naively risks Terraform trying
   to destroy/recreate real infrastructure.
2. Concretely: add `terraform/modules/` and `terraform/live/dev/` from
   this scaffold as **new, additional paths** alongside whatever
   Terraform already exists in the real repo (e.g. under a path like
   `terraform-new/` temporarily, if that avoids collision) rather than
   replacing the existing directory in place.
3. Flag for a human: the existing Terraform's state needs to be
   reconciled with this new structure (likely via `terraform state mv`
   or a fresh `import`) before the old structure can be deleted. This is
   NOT something to automate without a human approving the plan first --
   state migration mistakes are destructive and hard to undo.
4. Once a human has approved the new structure, use
   `scripts/new-environment.sh` to generate `test`/`stage`/`prod` from
   the `dev` template (see its own header comment for usage).

## 4. `charts/` and `.harness/` -- lower risk, but still check

- `charts/psa-service/` is new (this scaffold introduces Helm-based EKS
  deployment where raw `kubectl`/manual manifests may have existed
  before). Safe to add if the path doesn't already exist. If the real
  repo already has Helm charts for these apps, flag for a human --
  don't have two charts serving the same purpose.
- `.harness/` pipelines, templates, and input sets are new structure.
  If the real repo already has Harness pipeline YAML (even informally,
  e.g. pasted directly into the Harness UI rather than version
  controlled), a human needs to decide whether to migrate those into
  this file-based structure or keep them as-is.

## 5. Fill in every placeholder

Run this from the repo root once everything from sections 2-4 is in
place:

```
./scripts/check-placeholders.sh
```

This lists every `REPLACE_ME` across the repo with file:line. Each one
needs a real value -- see README.md's "What you need to fill in"
section for what kind of value each category expects (VPC IDs, Nexus
secret ARNs, Harness connector names, etc.). These values are specific
to your AWS account, Nexus instance, and Harness org/project -- nothing
in this scaffold can supply them, and guessing at them is worse than
leaving them as REPLACE_ME for a human to fill in.

## 6. Validate

```
./scripts/validate.sh
```

This re-runs the same offline structural checks used while building
this scaffold (HCL balance, YAML parsing, module argument wiring, app
source compiling). A clean run here does NOT mean this is
production-ready -- it means the structural work didn't introduce
copy-paste damage. Follow this with the real tools once available:

```
terraform -chdir=terraform/live/dev/foundation init -backend=false
terraform -chdir=terraform/live/dev/foundation validate
# repeat for terraform/live/dev/ecs and terraform/live/dev/eks

helm template psa-java charts/psa-service -f /dev/stdin <<< 'image: {repository: test, tag: test}
ingress: {host: test.local}'
```

## 7. Things that cannot be automated -- flag these for a human explicitly

- Creating the Nexus pull-credentials secret in Secrets Manager (README's
  "Assumptions made" section)
- Standing up External Secrets Operator (or equivalent) in the EKS
  cluster to sync that secret into each namespace as a
  `dockerconfigjson` Secret
- Configuring the actual Harness connectors (`account.psa_nexus_connector`,
  `account.psa_ecr_connector`) with real credentials
- Wiring a Harness Pipeline trigger from each `*-ci.yaml` pipeline to its
  matching CD pipeline(s), passing the build tag through as `image_tag`
- Reconciling existing Terraform state with the new structure (section 3)
- Any decision where this document says "flag for a human" above

## If something in this scaffold looks wrong

Don't silently "fix" it by guessing at the intended behavior -- most of
this scaffold's non-obvious decisions are explained in a comment at the
top of the relevant file, or in README.md. If a discrepancy isn't
explained in either place, that's a real gap: note it and surface it to
a human rather than resolving it unilaterally.
