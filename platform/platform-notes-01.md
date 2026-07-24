# Platform Engineering Pods — Discussion Notes

## 1. Naming the actual problem

Before jumping to structure, it's worth saying this out loud in the meeting:

> "We have a **federated model with no federation mechanism.** Embedded PEs are locally optimized — they make their product team happy, which is good — but there's no shared forcing function that pulls their work back toward a common standard. Eight PEs means eight roadmaps."

This reframes the fix from "add headcount" to "add coordination structure," which is the real gap.

---

## 2. Sizing the pods

- Current: ~8–10 on core platform team, growing by 10–12 → landing around **18–22 total**.
- One scrum team of 20 doesn't work (too big for one backlog, one standup, one sprint review).
- Rule of thumb: keep pods at **4–6 engineers** (two-pizza-team size). At ~20 people, that's **3–4 pods**.
- Don't just split people evenly — split by **domain**, not by which product team they used to sit under. Otherwise you've just re-created the eight-silos problem inside one team.

**Possible pod domains** (adjust to your actual stack):
- CI/CD & developer tooling
- Cloud infra / Kubernetes / networking
- Observability & reliability (SRE-leaning)
- Security & compliance / access management

Each pod owns a "paved road" for its domain — the default, supported way of doing things — rather than each PE reinventing it for whichever product team they're attached to.

---

## 3. Standards without killing responsiveness

The embedded PEs were doing something right (responsiveness to their product teams) — don't lose that.

- **Standards Council / Architecture Guild**: one rep per pod, rotating role, meets biweekly. Owns an RFC process and a decision log (even a simple shared doc/wiki works). This is the thing that didn't exist before.
- **Paved road, not mandate**: standards win adoption when they're the path of least resistance (templates, golden CI pipelines, Terraform modules) — not just a doc nobody reads.
- **Enforce in the pipeline, not in a wiki**: linting, CI gates, scorecards — bake standards into tooling so they don't depend on individual discipline.
- Consider a **"standards champion"** role inside each pod — same person who sits on the council — responsible for bringing decisions back to their pod and making sure their pod's work stays aligned.

---

## 4. Cross-pollination (the thing you said is missing)

- **Weekly cross-pod demo/sync** (15–30 min, lightweight) — what shipped, what's blocked, what other pods should know about.
- **Guilds/chapters by discipline**, orthogonal to pods — e.g., everyone touching Kubernetes meets monthly regardless of which pod they're in. This is how you avoid "four people independently learn the same lesson."
- **Rotational secondments**: engineers spend a sprint or a quarter embedded in a different pod periodically. Spreads knowledge, prevents pod ossification, and gives people growth paths without leaving the team.
- **Shared internal knowledge base / RFC repo** — one place, not four Confluence spaces.

---

## 5. Sprints, support rotation, and pager duty

- **Synchronize sprint calendars across pods** even if backlogs are separate — same start/end dates, same ceremony days. This makes on-call handoffs and cross-pod dependencies much easier to reason about.
- **Round-robin on-call across pods**, not per-product-team: one pod "on point" for a given week/sprint while the others stay heads-down on roadmap work. Reduces context-switching tax.
- Centralize the **on-call tool** (PagerDuty/Opsgenie/etc.) with routing rules by domain, so tickets land with the pod that owns that area rather than whoever happens to still be tied to that product team.
- Decide explicitly: does "support" mean **triage-and-route** (pod on call just routes to the right owning pod) or **full ownership** (on-call pod handles everything that week)? This changes how much cross-training you need.

---

## 6. Open questions to raise in the meeting

- Do pods align to **technical domain** or stay loosely aligned to **product team clusters** (hybrid)? Trade-off: domain alignment fixes standards drift; product alignment keeps responsiveness high.
- Who is the **tie-breaker** when the Standards Council can't reach consensus — a platform lead/architect role?
- How do you handle **legacy debt** from the "eight different directions" — do you retrofit old work to new standards, or grandfather it in and only enforce going forward?
- What's the **onboarding path** for the 10–12 new/absorbed engineers — do they join existing pods, or do you stand up new pods and backfill leadership?
