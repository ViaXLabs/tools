# Vault-Everywhere Starter Kit

This kit has two jobs:

1. A **repo security checklist** — the stuff that stops secrets from getting hardcoded in the first place.
2. A **working set of patterns for using Vault at runtime, outside of Harness pipelines** — because pipeline-time Vault fetches only solve "how do I deploy," not "how does the running process get its secret."

Files in this kit:

| File | What it's for |
|---|---|
| `.gitleaks.toml` | Secret-scanning rules (default ruleset + a custom New Relic license key rule) |
| `.pre-commit-config.yaml` | Blocks secrets on a dev's machine, before a commit even happens |
| `vault-policy-newrelic.hcl` | Least-privilege Vault policy scoped to exactly one secret path |
| `vault-agent.hcl` | Vault Agent config for VMs / non-Kubernetes runtime injection |
| `newrelic.ini.ctmpl` | Template the agent renders into a real config file at runtime |
| `k8s-vault-agent-injector.yaml` | Kubernetes: sidecar-injector pattern |
| `k8s-vault-secrets-operator.yaml` | Kubernetes: VSO pattern (syncs into native k8s Secrets) |
| `ecs-task-definition-vault-sidecar.json` | ECS: one-shot Vault Agent sidecar + app container, wired together |
| `vault-agent-ecs.hcl` | ECS: Vault Agent config using AWS IAM auth (task role) instead of AppRole/k8s auth |

---

## Part 1 — Repo security checklist

This is the "make all our repos secure" list. Most of it isn't Vault-specific — it's the baseline every repo should have regardless of what secrets manager you use.

**Stop new secrets from landing**
- [ ] Gitleaks pre-commit hook installed org-wide (`.pre-commit-config.yaml`) — catches it before it's even committed
- [ ] Harness Code push protection enabled (if you're on Harness Code) — catches it at push time
- [ ] Harness STO "Secret Detection" step added to every pipeline — catches it at build time, and gives you a dashboard across all repos
- [ ] `.gitignore` covers `.env`, `*.pem`, `*.p12`, `credentials.json`, `*_rsa`, `.terraform/`, and anything with `secret`/`key` in the name

**Clean up what's already there**
- [ ] Full-history Gitleaks scan on every repo (not just new commits) to inventory existing exposure
- [ ] For anything found: rotate the secret first, *then* worry about scrubbing history — a secret that's been pushed is compromised even if you delete it later, since it's already in every clone, fork, and CI cache
- [ ] Rewrite history (`git filter-repo`, not the deprecated BFG-then-hope approach) only after rotation is confirmed, and only with a heads-up to the team since it forces a re-clone

**Structural controls**
- [ ] Branch protection: no direct pushes to main/release branches, required PR review
- [ ] CODEOWNERS on anything touching Vault policies, CI config, or deployment manifests, so secret-adjacent changes get a second set of eyes
- [ ] Harness STO SCA step (dependency scanning) alongside secret detection — a huge share of real incidents are secrets in a *dependency's* code, not yours

**Ongoing hygiene**
- [ ] Quarterly rotation for long-lived static secrets (New Relic license key included) even with no known incident — static credentials that never rotate are a standing liability
- [ ] A secret ownership map: which Vault, which path, which app, who's the human owner. If "who owns this key" takes more than 30 seconds to answer, that's the gap that turned a routine rotation into a 12-vault scramble

---

## Part 2 — Vault outside of pipelines: the full picture

Here's the thing pipeline-based Vault use hides from you: a pipeline fetches a secret *once*, at deploy time, and hands it to whatever it's building or deploying. That's fine for things like build-time credentials. It does nothing for a **long-running process** that needs a secret the whole time it's alive — which is exactly your New Relic agent case. That secret has to get into the *running process*, not just the deploy artifact.

There are three questions that determine which pattern you use:

### Question 1: How does the workload authenticate to Vault in the first place?

This is the "secret zero" problem — to get a secret from Vault, the app needs *some* credential to prove who it is to Vault. If that credential is itself hardcoded, you haven't solved anything, you've just moved the problem one level up.

- **On Kubernetes: use the Kubernetes auth method.** Every pod already gets a signed, short-lived service account token from the cluster itself — that's a credential your app never had to be handed, because Kubernetes handed it one automatically. Vault verifies that token against the K8s API and hands back a Vault token scoped to a policy. No bootstrap secret to distribute, ever.
- **Off Kubernetes (VMs, bare metal): use AppRole.** There's no automatic platform identity to lean on, so you provision a `role-id` (not sensitive, can live in config management) and a `secret-id` (sensitive, single-use, delivered once via a wrapped token or your config management's own secrets channel — e.g. Ansible Vault, cloud-init with instance metadata, or a TPM-backed secret store). The `secret-id` gets consumed once and deleted; the running agent then holds a renewable Vault token, not the original credential.

### Question 2: Does the secret need to be a *file* or a *native platform secret*?

| Need | Pattern |
|---|---|
| App reads a config file (`.ini`, `.yml`, `.env`) | **Vault Agent** — templates the file to disk at startup, refreshes on an interval |
| App expects a Kubernetes `Secret` object / env var | **Vault Secrets Operator (VSO)** or **External Secrets Operator (ESO)** — syncs into native k8s Secrets |
| You don't want the value in etcd at all, even encrypted | **Vault CSI Provider** — mounts secrets as an ephemeral volume, no k8s Secret object created |
| Non-container process (systemd service, cron job) | **envconsul** — wraps the start command, injects env vars, never writes to disk |

### Question 3: Static secret or something Vault can generate dynamically?

New Relic's license key is account-wide and static — Vault isn't generating it, it's just storing and distributing it. That means your leverage is in **rotation cadence + tight read policies**, not lease TTLs. (Contrast with something like a database credential, where Vault *can* mint a short-lived, auto-expiring credential per app — that's a different and even stronger pattern, worth using anywhere you have a secrets backend that supports it, like the database secrets engine.)

### Putting it together for your New Relic case

1. Vault side: `vault-policy-newrelic.hcl` — a policy that can read exactly `kv/data/prod/newrelic` and nothing else.
2. Auth side:
   - Kubernetes: `vault write auth/kubernetes/role/my-service bound_service_account_names=my-service bound_service_account_namespaces=prod policies=newrelic-read ttl=1h`
   - VM/AppRole: `vault write auth/approle/role/my-service policies=newrelic-read token_ttl=1h token_max_ttl=4h`
3. Runtime side — pick one:
   - K8s + file-based config → `k8s-vault-agent-injector.yaml`
   - K8s + native Secret/env var → `k8s-vault-secrets-operator.yaml`
   - VM → `vault-agent.hcl` + `newrelic.ini.ctmpl`
4. **Delete `license_key` from every `newrelic.ini` / `newrelic.yml` / `newrelic-infra.yml` in the repo.** Don't leave a blank or placeholder value — for several New Relic agents, a value present in the config file wins over an environment variable, so a stale line can silently override what Vault just injected.

### One more principle worth internalizing

Every pattern above shares the same shape: **the secret is materialized only in memory or on an ephemeral volume, only on the machine actually running the workload, only after that workload has proven its own identity.** It never exists as a byte in git, in a Docker image layer, or in a CI log. If you're ever looking at a new tool or a new team's setup and can't point to *where* that materialization happens, that's the gap — not a detail to fill in later.

---

## Part 3 — ECS today, EKS later

None of the Kubernetes-specific patterns above (Agent Injector, VSO) apply on ECS — there's no
admission webhook to hook into. The shape of the fix is the same, though: a Vault Agent
sidecar in the task, authenticating off the task's *own* IAM role, rendering the secret to a
volume the app container reads from. That's what `ecs-task-definition-vault-sidecar.json` and
`vault-agent-ecs.hcl` set up.

**How it fits together:**

1. `vault-agent` runs as a second container in the same task (`essential: false`), authenticates
   to Vault using the **AWS IAM auth method** — Vault validates the task's IAM role the same way
   it'd validate a Kubernetes service account token, so there's no bootstrap secret to hand out.
2. It's run with `-exit-after-auth`: authenticate once, render the template once, exit. No
   long-running sidecar process to babysit.
3. The `app` container has `"dependsOn": [{"containerName": "vault-agent", "condition": "SUCCESS"}]`
   — it only starts if `vault-agent` exited with code 0. If Vault auth fails, the app doesn't
   start at all with a missing/stale key. Fail closed, not open.
4. Both containers mount the same `vault-secrets` volume; on Fargate platform version 1.4.0+
   (and always on the EC2 launch type) that's ephemeral storage scoped to the task, wiped when
   the task stops — no EFS filesystem to provision. If you're pinned to an older Fargate
   platform version, swap in an `efsVolumeConfiguration` instead (see HashiCorp's own ECS +
   Vault Agent tutorial, which uses EFS for exactly that reason).

**Rotation, the ECS way:** because ECS deploys already work by replacing tasks rather than
mutating them in place, you don't need a continuously-refreshing sidecar for a slow-moving
static secret like the New Relic key. When it rotates in Vault, `aws ecs update-service
--force-new-deployment` spins fresh tasks that each run `vault-agent` fresh and pick up the
current value — no task-definition edit, no image rebuild. (If you ever have a secret that
needs to rotate *underneath* a long-lived task without a redeploy, drop `-exit-after-auth`, make
`vault-agent` a persistent sidecar instead, and switch the dependency condition to `HEALTHY`
with a container healthcheck — but that's solving a different problem than the one you have
today.)

**Wiring the Vault side** (see the bottom of `vault-agent-ecs.hcl` for the exact commands):
enable the AWS auth method once, then write a Vault role that binds `my-service-task-role`'s ARN
to the same `newrelic-read` policy from `vault-policy-newrelic.hcl` — the policy and the secret
path don't change from the Kubernetes patterns above, only the auth method does.

**Looking ahead to EKS:** this is the part that makes centralizing on Vault *now* pay off during
the migration later — `vault-policy-newrelic.hcl` and the `kv/data/prod/newrelic` path stay
exactly as they are. The only thing that changes when a service moves from ECS to EKS is which
auth method it uses to prove its identity (AWS IAM → Kubernetes), which is a Vault role
config change, not a secret migration. Nothing about where the New Relic key lives has to move.

---

## Rollout order

1. Get the Vault policy + auth role live for one pilot app (the New Relic case is a good pilot — you already know exactly what's wrong with it).
2. Wire up whichever runtime pattern matches that app's platform.
3. Confirm the old hardcoded value is gone from the repo, not just superseded.
4. Turn on `.pre-commit-config.yaml` and the Harness STO scan org-wide before repeating steps 1-3 for the next app — you want the safety net in place before you go touch 12 more repos.
