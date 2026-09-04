# Harness Deploy Concurrency — Preventing Terraform Lock Collisions

## The short answer

Harness has **no direct equivalent** to Jenkins' `disableConcurrentBuilds()` — there's no single toggle that says "only one instance of this exact pipeline, ever." The one setting that sounds like it (**Concurrent Active Pipeline Executions**) is an **account-wide cap** across *every* pipeline you own, not a per-pipeline lock. So the checkbox you're picturing genuinely doesn't exist. What Harness gives you instead is two purpose-built mechanisms — one automatic, one manual — that together do the same job, just assembled rather than flipped on.

---

## The three control mechanisms (in order of how "automatic" they are)

### 1. Resource Constraints — already running, no setup needed

Every CD Deploy stage automatically gets a **Resource Constraint** keyed on `service + environment + connector + infrastructure`. If two executions target that exact same combination, Harness silently queues the second one until the first finishes.

- **This is already protecting you today**, without you doing anything.
- **Why it's not enough for your case**: it only fires if two runs share the *same* service+infra key. Two different branches deploying to *different* dynamic environments (or a plan-only run that doesn't fully match the key) can sail right past each other and still collide on the same Terraform state file, which Resource Constraints knows nothing about — it has no concept of state files or locks.
- Toggle location if you ever need to *disable* it for a stage: stage's **Infrastructure** settings → **Allow simultaneous deployments on the same infrastructure**.

### 2. Queue step — the actual fix for your Terraform-lock problem

This is the mechanism built for exactly your scenario: **you** define the key, so it can map to your Terraform state/lock rather than to service+infra.

**Setup:**
1. In the Deploy stage's **Execution**, add a step at the very top — before any `terraform init/plan/apply` step.
2. Category: **Flow Control** → **Queue**.
3. Give it a name and a timeout (how long an execution waits in queue before giving up).
4. **Resource Key** — this is the part that matters. Supports Fixed Values, Runtime Inputs, and Expressions. Use one tied to your actual state file, not just the branch:
   ```
   tf-lock-<+env.name>-<+infra.name>
   ```
   or, if you specifically want branch-level exclusivity regardless of environment:
   ```
   tf-lock-<+codebase.branch>
   ```
5. **Run next queued execution after completion of** → choose **Pipeline** (not just Stage) if the lock could still be held by a later step in the same pipeline run.

**Scope note:** Queue steps are **account-wide**. If pipelines in two different Harness projects both have a Queue step using the identical Resource Key, they'll queue against each other too — which is actually useful here, since it means your API Test pipeline (or any other chained pipeline touching the same state) just needs the same key in its own Queue step to be covered.

### 3. Barriers — not your use case, but worth knowing it exists

Barriers synchronize *parallel stages/step groups within a single pipeline execution* — e.g., making sure Stage B doesn't start until Stage A hits a checkpoint. Barriers are scoped to one pipeline and can't coordinate across separate pipeline runs or across pipelines, so this doesn't help with your cross-branch/cross-pipeline collision problem. Mentioned here only for completeness, since it's the third leg of Harness's official "control resource usage" trio.

---

## Mapping this onto what you actually described

You named two distinct collision risks:

| Risk | What causes it | Fix |
|---|---|---|
| Same branch deployed twice at once | A retrigger, a flaky webhook firing twice, someone manually re-running while a run is still in flight | Queue step keyed on `<+codebase.branch>` |
| Two *different* branches (e.g. main + a feature branch) hitting the same Terraform state | Both ultimately writing to the same `.tfstate`/lock regardless of branch identity | Queue step keyed on the actual state path (env/infra combo) |

These are two different keys protecting two different things. If your actual state file is scoped per-environment (most common setup), the **second** key is really the one doing the heavy lifting — a branch-scoped key alone wouldn't stop main and a feature branch from both targeting the same prod state simultaneously, since they'd have different branch names but the same underlying lock.

**Practical recommendation:** use one Queue step keyed directly on whatever uniquely identifies your Terraform state (environment + infra, or the literal state file path if you can express it), rather than branch name. That's the one that actually maps 1:1 to "what does Terraform's own lock protect" — which is the thing you're trying to avoid corrupting in the first place. Add the branch-level key too only if you've specifically seen the *same branch* double-trigger as its own separate problem.

---

## Example YAML for the Queue step

```yaml
- step:
    type: Queue
    name: TF State Lock Queue
    identifier: tf_state_lock_queue
    timeout: 30m
    spec:
      key: tf-lock-<+env.name>-<+infra.name>
      scope: Pipeline
```

Place this as the very first step in the stage's `execution.steps`, ahead of your `terraform init/plan/apply` steps.

---

## TL;DR — Jenkins vs. Harness

| Jenkins | Harness equivalent | Effort |
|---|---|---|
| `disableConcurrentBuilds()` checkbox | *(no direct equivalent)* | — |
| Same job, don't overlap | Queue step, keyed on something meaningful to you | One step, one-time |
| Same resource, don't overlap | Resource Constraints (automatic default) | Already on |
| Global concurrency cap | Concurrent Active Pipeline Executions (Account Settings) | Account-wide, not per-pipeline |

It's genuinely more setup than Jenkins' one-liner — but it's a single Queue step added once, not an ongoing maintenance burden. Once it's in the stage template, every pipeline built off that template inherits the protection automatically.
