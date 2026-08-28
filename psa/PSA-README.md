# PSA (Platform Sample App) — structure

This is a starting scaffold for restructuring the PSA repo so it scales
across languages (`psa-python` and `psa-java` today, more later), across
compute targets (ECS and EKS via Helm), and across environments
(dev/test/stage/prod) without the Terraform and Harness pipelines turning
into one big pile. Both apps deploy to **both** targets in this scaffold,
so it doubles as a working reference for "how we'd stand up ECS and EKS
for a new PSA language variant."

**If you're merging this into the real PSA repo, read `INTEGRATION.md`
first** — it's written as an explicit, ordered checklist (including where
the real repo almost certainly already has conflicting files, like an
existing Python app and existing Terraform) rather than prose to
interpret. This README explains *why* things are structured this way;
`INTEGRATION.md` explains *what to do* with it.

## Scripts

Three scripts live in `scripts/`, each with a longer explanation in its
own header comment:

- **`scripts/check-placeholders.sh`** — greps the whole repo for every
  `REPLACE_ME` and prints file:line for each. Run this after filling in
  real values, or as a mechanical "is this actually done" check.
- **`scripts/new-environment.sh <name>`** — scaffolds `test`/`stage`/`prod`
  by copying `terraform/live/dev/` and rewriting every dev-specific string
  that has to change (state keys, the hardcoded `environment = "dev"`,
  and the paths/wording inside header comments so they don't lie about
  which environment they're describing).
- **`scripts/validate.sh`** — bundles the offline structural checks used
  while building this scaffold (HCL balance, YAML parsing, Helm template
  syntax, module argument wiring, app source compiling) into one script,
  so whoever integrates this can re-run the same checks after merging —
  see "How this was tested" below for exactly what that does and doesn't
  cover.

## The core idea

Terraform is split by **what it manages**, not by which app happens to be
using it:

- **`terraform/modules/`** — reusable code, no state. `common` (VPC-adjacent
  resources, IAM baseline, KMS, RDS Postgres), `ecs-service`, and
  `eks-workload` are each written to be language-agnostic: they take an
  image URI as a variable and don't care whether that image was built from
  Gradle or pip, or that it lives in Nexus rather than ECR.
- **`terraform/live/<env>/`** — actual applied state, one root per concern:
  `foundation` (always applied, rarely changes), `ecs`, and `eks`. Each has
  its own S3 state key and its own minimal `versions.tf`. This is what fixes
  the "providers are jumbled" problem — only `eks/` carries the
  `kubernetes`/`helm` providers, for example, instead of every root
  carrying every provider.
- `ecs/` and `eks/` read `foundation`'s outputs via `terraform_remote_state`
  instead of redeclaring the VPC, RDS instance, or Nexus credentials secret.
- **`charts/psa-service/`** — one shared Helm chart, used by every app's
  EKS deployment. This is the Kubernetes-side equivalent of
  `modules/ecs-service`: the chart doesn't know or care which language it's
  running, it just takes an image and some values.

Both `psa-java` and `psa-python` are wired all the way through in `dev/ecs`
and `dev/eks` as two side-by-side `module` blocks each, calling the same
shared modules and the same shared chart with different inputs — that's
the pattern to copy for the next language.

Only `dev` is fully filled in here. To add `test`, `stage`, or `prod`, copy
`terraform/live/dev/` to `terraform/live/<env>/`, update the three
`backend.tf` files' `key` to `psa/<env>/...`, and update the `.tfvars`
files with that environment's real values.

## Images live in Nexus (with a backup copy in ECR)

Nexus is the registry both ECS and EKS actually pull from. The practical
difference from ECR: **Nexus isn't IAM-integrated**, so both compute
targets need explicit pull credentials, not just an image path:

- `modules/common` takes an existing `nexus_pull_secret_arn` (a Secrets
  Manager secret holding Nexus username/password, created and rotated
  outside this repo) and grants the shared workload role read access to it.
- **ECS:** `modules/ecs-service` sets `repositoryCredentials` on the
  container definition, pointing at that same secret ARN. This is what
  lets the ECS agent actually authenticate to Nexus when pulling.
- **EKS:** the shared chart (`charts/psa-service`) takes an
  `imagePullSecret` value — the name of a `kubernetes.io/dockerconfigjson`
  Secret holding the same Nexus credentials, synced into the `psa-<env>`
  namespace by something like External Secrets Operator. `dev/eks/main.tf`
  passes `psa-nexus-pull` as that name for both apps, since they land in
  the same namespace and can share one synced secret.
- Image URIs in the `.tfvars` files point at Nexus
  (`nexus.<host>:<port>/repository/<repo-name>/psa-<env>-<lang>:<tag>`) —
  the exact path format depends on how your Nexus Docker repos are set up
  (hosted vs. group repo, port-per-repo vs. path-based routing), so treat
  the `REPLACE_ME` values as illustrative, not literal.
- One parsing detail worth knowing: `terraform/live/dev/eks/main.tf` splits
  the image URI into repository + tag using a regex that only matches the
  *last* colon, specifically because Nexus hosts commonly include a port
  (`nexus.company.com:8082/...`) — a naive `split(":", uri)` would wrongly
  split on that too.

**ECR still exists, but purely as a backup.** `modules/common` provisions
one ECR repo per app (`aws_ecr_repository.backup`), and every CI pipeline
pushes the same build there in addition to Nexus. Nothing ever pulls from
it for deployment — no CD pipeline, no Terraform variable, references it.
If Nexus were ever unavailable, a copy of every image still exists in ECR;
that's the entire reason it's there.

## Adding a new language later (Node, Nginx, ...)

`psa-python` and `psa-java` are both wired through end to end, so this is
the exact recipe either one followed — copy it:

1. Add the app under `apps/psa-<name>/` with its own `Dockerfile`.
2. In `terraform/live/<env>/ecs/main.tf`, add a `module` block calling
   `modules/ecs-service` — copy the `python_ecs` or `java_ecs` block and
   change the name/image/target-group variable.
3. In `terraform/live/<env>/eks/main.tf`, add a `module` block calling
   `modules/eks-workload` with the same `chart_path` local — copy the
   `python_eks` or `java_eks` block. It automatically deploys through the
   shared `charts/psa-service` chart; you don't touch the chart itself.
4. Copy `.harness/pipelines/psa-{java,python}-ci.yaml` and the matching
   `-ecs.yaml`/`-eks.yaml` CD pipelines, swapping the repo path, Dockerfile
   path, and build context in the CI pipeline's Build stage.
5. Make sure the image gets pushed to Nexus under the naming convention
   the pipelines expect (`psa-<env>-<name>`) — nothing here creates the
   Nexus repo itself, same as it doesn't create an ECR repo.

Nothing in `modules/ecs-service`, `modules/eks-workload`, or
`charts/psa-service` needs to change — that's the point of keeping them
language-agnostic.

## Harness pipelines: CI and CD are separate

Building an image and deploying one are different concerns with different
triggers, so they're two pipelines per app, not one:

- **`psa-{java,python}-ci.yaml`** — build stage only. Pushes to Nexus
  (primary) and ECR (backup), tagged with `<+pipeline.sequenceId>`. Doesn't
  touch Terraform or deploy anything.
- **`psa-{java,python}-{ecs,eks}.yaml`** — the CD pipelines. No build stage
  at all — they take `image_tag` as a pipeline variable (the tag CI just
  pushed) and run foundation → apply target → verify, deploying exactly
  that tag from Nexus.

The handoff: a CD pipeline's `image_tag` is meant to come from a Harness
**Pipeline trigger** on the matching CI pipeline's success (passing
`<+pipeline.sequenceId>` from the CI run through), or be supplied manually
when kicking off a deploy. Nothing here wires up that trigger — it's a
Harness UI/API step outside what YAML alone can express, so treat the
`image_tag` input as the seam where you'd connect one.

Getting that tag into Terraform: each CD pipeline's target-apply step
(`Apply ECS` / `Apply EKS`) passes an inline Terraform var file through
`terraform-apply`'s `varFiles` input, e.g.:

```
java_image_uri = "<+pipeline.variables.nexus_registry>/psa-<+pipeline.variables.environment>-java:<+pipeline.variables.image_tag>"
```

This overrides whatever's sitting in the checked-in `.tfvars` for that one
run, so what deploys is always the tag CI just built — the static
`.tfvars` value becomes more of a "what to use if nobody overrides it"
default, useful for a manual `terraform apply` from a laptop.

The `terraform-apply` template's `varFiles` input is required by the
template, so the `Foundation` stage (which has no image to override) just
passes an empty string — Terraform accepts an empty var file without
complaint.

- `.harness/templates/` holds four reusable step templates:
  `build-and-push-image` (Nexus push), `build-and-push-ecr-backup` (ECR
  push, backup only), `terraform-apply` (parameterized by workspace, root
  folder path, and an optional var-file override — the same template
  applies foundation, ecs, or eks), and `deploy-and-verify` (health check
  + a reminder to confirm the app is reporting to New Relic).
- `.harness/input-sets/` carries the static per-environment values
  (`environment`, `nexus_registry`) that both CI and CD pipelines share.
  `image_tag` is deliberately not in there — see above. Before promoting
  to `stage` or `prod`, add a `HarnessApproval` step ahead of the
  terraform-apply steps so a plan gets a human sign-off first.

**Note:** the Harness YAML here is a structural starting point based on
Harness's documented step types (`TerraformApply`, `BuildAndPushDockerRegistry`,
`BuildAndPushECR`, step templates with `templateInputs`) — validate field
names against your actual Harness project/module version and connector
setup before running it, since none of this was exported from a live
account.

## EKS deployment via Helm

`modules/eks-workload` no longer creates raw `kubernetes_deployment` /
`kubernetes_service` / `kubernetes_ingress_v1` resources directly — it
calls a `helm_release` resource pointed at `charts/psa-service`, the one
shared chart both apps use:

- The chart itself (`charts/psa-service/`) is a normal, standalone Helm
  chart — `helm template`/`helm install` works on it without Terraform if
  you want to test it locally.
- `modules/eks-workload` passes everything chart-specific in as Helm
  `values` (image repo/tag, replicas, resource requests, env vars, the
  IRSA role ARN as a service account annotation, and the ingress host) —
  the module is the only place that knows this is Terraform-managed.
- Each live root's `eks/main.tf` defines `chart_path` once as a local and
  reuses it for every app's `module` block, so adding an app never means
  touching the chart or copy-pasting a chart folder per language.
- `helm` and `kubernetes` provider config in `eks/versions.tf` both point
  at the same existing EKS cluster (`var.eks_cluster_name`) — this scaffold
  assumes that cluster already exists and is owned by the platform team,
  same as the VPC.

This is the piece meant to double as your "here's how we'd deploy to EKS"
reference for other teams — the chart and the module are both short enough
to read end to end.

## Java + New Relic APM

- `apps/psa-java/Dockerfile` builds with Gradle, runs on a JRE image, and
  bakes in the New Relic Java agent as a `-javaagent`. No code changes are
  needed to get APM data flowing.
- Configuration happens at deploy time via environment variables, not
  baked into the image, so the same image works across dev/test/stage/prod:
  - `NEW_RELIC_LICENSE_KEY` — from Secrets Manager (ECS) or a synced
    Kubernetes secret (EKS), never baked into the image
  - `NEW_RELIC_APP_NAME` — set per environment, e.g. `psa-java-dev`, so
    each environment shows up as its own entity in New Relic
  - `NEW_RELIC_LOG_FILE_PATH=STDOUT` — keeps agent logs in container logs
    instead of a file nobody reads
  - `JAVA_OPTS=-javaagent:/app/newrelic/newrelic.jar` — this is what
    actually attaches the agent; Gradle's `application` plugin start
    script picks up `$JAVA_OPTS` from the environment automatically
- `newrelic.yml` is intentionally minimal — most settings come from the
  env vars above.

## What you need to fill in

Everything marked `REPLACE_ME` needs a real value before this applies
cleanly:

- `terraform/live/dev/*/backend.tf` — your actual state bucket + lock table
- `terraform/live/dev/foundation/terraform.tfvars` — real VPC + subnet IDs,
  the ARN of your existing Nexus pull-credentials secret
- `terraform/live/dev/ecs/terraform.tfvars` — real ALB target group ARNs
  (one per app), New Relic license key secret ARN, real Nexus image URIs
  (these get overridden per-deploy by the CD pipeline anyway, but need a
  sane default for manual applies)
- `terraform/live/dev/eks/terraform.tfvars` — real EKS cluster name, real
  Nexus image URIs (same caveat)
- `.harness/pipelines/*-ci.yaml` — a Docker connector for Nexus
  (`account.psa_nexus_connector`) and an AWS connector for the ECR backup
  push (`account.psa_ecr_connector`)
- `.harness/pipelines/*.yaml` (all of them) — your Harness org/project
  identifiers
- `.harness/input-sets/*.yaml` — your actual Nexus host/repo path for
  `nexus_registry`
- A Harness Pipeline trigger from each `*-ci.yaml` to its matching CD
  pipeline(s), passing the build's tag through as `image_tag` — not
  expressed in this YAML, has to be wired up in Harness directly
- Outside Terraform entirely: the `psa-nexus-pull` dockerconfigjson secret
  in each EKS namespace needs to actually get synced from somewhere
  (External Secrets Operator pointed at the same Secrets Manager secret
  foundation reads, or your team's equivalent)

## Assumptions made

- **The Nexus pull-credentials secret already exists.** `foundation` takes
  its ARN as an input rather than creating it, on the assumption your
  security/platform team already manages a Nexus service-account
  credential in Secrets Manager. If that secret doesn't exist yet, someone
  needs to create it (username/password JSON, same shape as the DB secret
  in `modules/common`) before `terraform apply` will succeed.
- **The EKS image-pull secret sync is external.** Terraform passes
  `psa-nexus-pull` as a *name* to the chart, but nothing here creates that
  Kubernetes Secret — something like External Secrets Operator needs to be
  running in the cluster and configured to sync it from Secrets Manager.
  Without it, pods will get `ImagePullBackOff`.
- One Postgres RDS instance per environment, owned by `foundation`, shared
  by whichever compute target (ECS or EKS) is running in that environment.
  If ECS and EKS should eventually have separate databases, that's a
  one-line move — pull the `aws_db_instance` block out of `modules/common`
  and into `modules/ecs-service` / `modules/eks-workload` instead.
- The VPC, subnets, and the EKS cluster itself are treated as existing
  platform-team-owned resources passed in as variables, not created by
  this repo.

## How this was tested

Built and checked with no network access and neither `terraform` nor
`helm` installed, so "tested" means something narrower than usual here.
What was actually verified:

- **Both apps genuinely run.** Not just syntax-checked — actually
  started (`python3 app.py`, and the Java file via `java`'s single-file
  source launcher since no `javac`/Gradle was available) and hit with
  `curl` on both `/` and `/health`, with real responses back.
- **Every Terraform module call is correctly wired.** A small script
  (the same logic now in `scripts/validate.sh`) parses every `module`
  block in `terraform/live/dev/*` and confirms each one passes exactly
  its target module's required arguments — no typos, no missing
  arguments, no unknown ones. Also confirmed every `terraform_remote_state`
  output reference matches a real output name, and that `foundation`'s
  backend state key matches exactly what `ecs/` and `eks/` read.
- **The Helm chart's templates are internally consistent.** Balanced
  `{{ }}` tags, every `include "psa.X"` call resolves to a helper that
  actually exists in `_helpers.tpl`, and the values Terraform's
  `helm_release` generates match the chart's expected keys one-for-one.
- **All YAML parses** (Harness pipelines/templates/input-sets, plus
  `Chart.yaml`/`values.yaml` — the chart's *templates* aren't plain YAML,
  since Go-template syntax isn't valid YAML on its own, so those got the
  brace/helper check above instead).
- **`scripts/new-environment.sh` was actually run**, not just written —
  generated a `test` environment from `dev`, confirmed the state keys,
  the `environment = "test"` substitutions, and the header comments all
  came out correct, then deleted the test run.

What this does **not** cover, and why it matters:

- No real `terraform validate`/`terraform plan` ever ran. The HCL could
  still contain a mistake this repo's structural checks can't catch —
  e.g. a resource argument that's spelled right but doesn't exist for
  that resource type, or a genuine provider-version incompatibility.
- No real `helm template`/`helm install` ever ran against a cluster.
- The Java app was never taken through an actual `gradle build` or
  Docker build — only run directly via source, which doesn't exercise
  `build.gradle`, the multi-stage Dockerfile, or the New Relic agent
  download/unzip step at all.
- The Harness YAML's field names are a best-effort structural
  approximation, not a validated export — see the note in the Harness
  section above.

`scripts/validate.sh` re-runs everything in the first list. Section 6 of
`INTEGRATION.md` covers what to run for the second list once you're
somewhere with the real tools available.
