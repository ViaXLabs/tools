Claude finished the response
i need to use terrafomr to create a module to tag new relic setup for a team

need tags on
destinatiosn
workflows
alert policies
alert contions

lets say teh tag team needs to be used fro all those thing>>>

please research of all those new relci things CAN be tagged.. double check and print the ref'd website

ok.. so think anad create some dummy terrafrom that would do all this

2:34 PM

Searched the web
Searched the web
Now let me check the specific tagging capabilities for each resource — especially newrelic_notification_destination (which doesn't natively support tags) and newrelic_alert_policy.

Searched the web
Searched the web
Great research. Now I have a clear picture. Let me also check if newrelic_alert_policy exposes an entity_guid for tagging.

Searched the web
Searched the web
Now I have a complete picture. Let me build the Terraform module. Here's the key summary of what I found before writing the code:

Tagging support per resource:

Resource Taggable? How
newrelic_nrql_alert_condition ✅ Yes exposes entity_guid → use newrelic_entity_tags
newrelic_notification_destination ⚠️ Partially exposes guid, but there's a known bug (#2886) where entity tags silently fail for destinations — best workaround is naming conventions
newrelic_workflow ✅ Yes the workflow filter predicate uses accumulations.tag.team to route by team tag
newrelic_alert_policy ⚠️ No native entity_guid the newrelic_alert_policy resource does NOT export an entity_guid — you must look up the policy entity via newrelic_entity data source and use NerdGraph/newrelic_entity_tags
Now let me write the module:

Created 6 files, ran a command, read a file
Created 6 files, ran a command, read a file
Here's the full breakdown of what was researched and built:

Research findings — can each resource be tagged?
I verified all four resources against the live Terraform Registry docs and provider GitHub issues.

Alert conditions — ✅ clean. newrelic_nrql_alert_condition (and the legacy newrelic_alert_condition) export an entity_guid attribute directly, which you pass straight into newrelic_entity_tags. No lookup needed.
Terraform Registry

Alert policy — ⚠️ needs a workaround. newrelic_alert_policy does not export an entity_guid. To tag it you have to do a newrelic_entity data source lookup by name after creation (using type = "POLICY" / domain = "AIOPS") to get the GUID, then pass that into newrelic_entity_tags. There's an open GitHub issue about this gap.
Terraform Registry

Notification destination — ⚠️ known bug. The resource does export a guid, but there's a known provider bug where newrelic_entity_tags on a destination throws expected entity tag to have been created but was not found. The tag block is included in the module with a comment explaining this — it'll work on fixed provider versions. In the meantime, the resource name encodes the team name as a safe fallback.
GitHub

Workflow — ✅ handled differently. Workflows use accumulations.tag.team as a filter predicate in issues_filter — meaning the workflow routes issues to the right team by matching the team tag on the conditions that fired them. That's actually the idiomatic way to connect teams to workflows in New Relic.
Terraform Registry

What the module does
Single team variable drives all naming and tagging
extra_tags map lets you add env, cost_center, etc. on top
The root main.tf shows two teams (platform + checkout) using the same module simultaneously
All newrelic_entity_tags use dynamic "tag" blocks so adding/removing tags is one variable change

Readme
Document · MD

Main
TF

Variables
TF

Outputs
TF

Main
TF

Variables
TF
great.... so yes... for policy, let's do that lookup to get it and run a nerd graph script to update... this may have to be outside of teh terraform ? we coudl write a python program top do that...

we may need the outputs fo teh terrafomr for teh creation of teh item to use ??
then run some pythion or something... but coudl that py script run inside pterrafomr ?? i forget

and then for destinatiosn... maybe we coudl do teh same... get the name and guid of the destination... then look it up and get the anme or guid and tehn use nerd grapgh to use with pyon running in terraform?? or maybe in anothe rstep of teh pipeline

maybe harness has an out put if those are created and we save that variable for teh next harness stage with does the update...

it woudl be nice to have it terrafor.. ao think and explain a lot of it

Show more
2:41 PM
Great question — let me think through this properly before writing any code.

The problem
Both newrelic_alert_policy and newrelic_notification_destination need NerdGraph API calls to tag them, because the Terraform provider either doesn't expose the GUID cleanly or has a bug. You need the resource IDs/GUIDs after Terraform creates them to do the tagging.

Your options — thinking it through
Option 1: null_resource + local-exec Python inside Terraform Terraform has a null_resource with a local-exec provisioner that runs a shell/script after a resource is created. You can pass ${newrelic_alert_policy.team_policy.id} directly as an env var into the script. This keeps everything in one terraform apply. The downside: local-exec is considered a Terraform anti-pattern — it doesn't manage state, it won't re-run on drift, and it makes plans harder to reason about. But for "fire and forget" tagging it's totally reasonable.

Option 2: Terraform http provider / REST call The http provider can make GET requests but not POST — so it can't call NerdGraph. Dead end.

Option 3: Terraform outputs → separate Python script → run in pipeline Classic two-stage pipeline approach. Stage 1: terraform apply, capture outputs. Stage 2: Python script reads the outputs (via terraform output -json) and calls NerdGraph. Clean separation of concerns, easy to test the Python independently, works perfectly in Harness as two pipeline stages where Stage 1 exports variables that Stage 2 consumes.

Option 4: external data source Can call scripts but only for reading data into Terraform, not writing to external systems. Wrong direction.

Option 5: Terraform newrelic_entity_tags with depends_on + retry We already tried this — it's the bug that makes destinations fail. The data source lookup for policies works but is fragile (timing-dependent on NR's entity catalog indexing).

Recommendation
Do null_resource + local-exec for a pure-Terraform experience, OR the two-stage pipeline if you're already in Harness. Both are legitimate. Since you mentioned Harness specifically, the pipeline approach is actually cleaner because:

Stage outputs in Harness are a first-class feature
The Python script is independently testable
You avoid local-exec weirdness in your Terraform state
If tagging fails, you don't have to re-apply the whole Terraform plan
Let me build both — the null_resource approach inside the module, and a standalone Python script designed to be called from a Harness pipeline stage reading Terraform outputs.

Viewed 3 files
Viewed 3 files
Good, I have the full picture. Now let me build everything — the updated Terraform with null_resource/local-exec as the in-Terraform approach, the Python NerdGraph tagger, and the Harness pipeline YAML.

Python NerdGraph tagging script - standalone, reads terraform output JSON or env vars
Python NerdGraph tagging script - standalone, reads terraform output JSON or env vars
Now add the null_resource option to the Terraform module so it can run the script inline:

Edited 3 files
Edited 3 files
Now update the module variables.tf to add the new vars:

Add null_resource control variables to module variables.tf
Add null_resource control variables to module variables.tf
Now update module outputs.tf to remove the data source reference that no longer exists and add alert_policy_name:

Update outputs to remove data source ref and add policy name output
Update outputs to remove data source ref and add policy name output
Now add nr_api_key and enable_nerdgraph_tagging to the root main.tf module calls, and build the Harness pipeline YAML:

Edited 2 files
Edited 2 files
Now write the Harness pipeline YAML:

Harness pipeline YAML - two stage: Terraform apply then NerdGraph tag
Harness pipeline YAML - two stage: Terraform apply then NerdGraph tag
Now update the README to document all three approaches clearly:

Created a file, ran a command, read a file
Created a file, ran a command, read a file
Here's the full reasoning and what was built:

Can Python run inside Terraform? Yes — via null_resource + local-exec
Yes, Terraform can run a Python script using a null_resource with a local-exec provisioner. It fires after the resource it depends_on is created, and you can pass Terraform-known values (like newrelic_alert_policy.team_policy.id) directly as environment variables into the script. That's Approach A in the module.

The catch: local-exec is stateless from Terraform's perspective. It doesn't track whether tagging succeeded on previous runs — it uses triggers (a hash of the tag values) to decide when to re-run. It also means the machine running terraform apply needs python3 + requests installed.

The three approaches — what was built
Approach A (null_resource inline): Two null_resource blocks in modules/newrelic_team_alerting/main.tf — one for the alert policy (does a NerdGraph name lookup with retry for catalog lag), one for the destination. Gated behind var.enable_nerdgraph_tagging. Single terraform apply does everything.

Approach B (standalone script): nr_tag_resources.py reads terraform output -json via --tf-outputs tf_outputs.json, or accepts everything as env vars via --from-env. Has built-in retry logic for the policy entity catalog lag (up to 3 attempts, 5s apart). Works from your local shell or any CI step.

Approach C (Harness pipeline): harness-pipeline.yaml with two stages. Stage 1 runs Terraform with enable_nerdgraph_tagging=false and uses Harness outputVariables to export the policy name and destination GUID. Stage 2 reads those variables natively (Harness passes them between stages without file passing) and calls the Python script per team with secrets injected from Harness Secrets Manager. This is probably the cleanest option if you're already on Harness.

Main
TF

Nr tag resources
PY

Harness pipeline
YAML

Variables
TF

Outputs
TF

Main
TF

Readme
Document · MD

Skip to content newrelic terraform-provider-newrelic Repository navigation Code Issues 100 (100) Pull requests 76 (76) Discussions Actions Projects Security and quality Insights newrelic_entity_tags: expected entity tag to have been created but was not found #2886 Open Open newr

pasted

ok... so found this page taht might be a better help

THINK DEEPER THERE

2:47 PM
Great find. Let me re-read this carefully before touching any code.

The bug reporter figured out two things:

It's eventual consistency — NR's entity catalog takes 60-70 seconds to index a newly created destination before tags can be applied. The API isn't rejecting it; it's just not ready yet.
Two workarounds that actually work inside Terraform, no Python, no null_resource:
A sleep 120 local-exec provisioner on the destination resource itself (forces a wait before newrelic_entity_tags runs)
A timeouts { create = "5m" } block on newrelic_entity_tags — which is better because Terraform retries automatically and stops as soon as the tag lands, rather than always sleeping the full duration
The timeouts approach is the clean solution. It means:

No Python script needed for destinations
No null_resource needed for destinations
No pipeline stage needed for destinations
Just add timeouts { create = "5m" } to newrelic_entity_tags and it self-heals
This changes our destination strategy significantly. The policy situation is still different (no entity_guid exported at all), but for destinations we should revert to the proper Terraform-native approach with the timeout fix.

Let me update the module:

Viewed 2 files
Viewed 2 files
Good. Now I have the complete picture. The key insight from that issue is:

Destination: NOT a provider bug per se — it's NR eventual consistency. The entity catalog takes 60-70s to become taggable. The timeouts { create = "5m" } fix on newrelic_entity_tags makes Terraform retry automatically until it succeeds. No Python, no null_resource, no pipeline step needed for destinations.
Alert policy: Still needs the null_resource/NerdGraph approach since it doesn't export entity_guid at all — a different root cause.
This means we can simplify significantly: destinations go back to pure Terraform, only policy needs the escape hatch.

Rewrite module main.tf with corrected tagging strategy
Rewrite module main.tf with corrected tagging strategy
Now simplify variables.tf — we can drop the destination-related script vars since that path is gone, but keep the policy ones:

Rewrite module variables.tf - cleaner now destination is pure TF
Rewrite module variables.tf - cleaner now destination is pure TF
Now update the README to reflect the corrected understanding:

Ran a command, read a file
Ran a command, read a file
Good catch — that issue completely changes the destination picture. Here's what changed and why:

What the issue actually told us
The reporter's own debugging revealed it: at the ~60-70 second mark, tags started appearing in the NR UI on their own. It's not a provider bug — NR's entity catalog has eventual consistency lag after a destination is created. The API isn't broken; it just isn't ready yet.

He found two fixes, and the better one is:

hcl
resource "newrelic_entity_tags" "destination_tags" {
guid = newrelic_notification_destination.team_email.guid
...
timeouts {
create = "5m"
}
}
Terraform's retry loop on create keeps polling until the tag confirms as written, then stops immediately. If NR is fast (say 65s), you don't wait the full 5 minutes. That's exactly the right fix.

How this simplifies things
Before (wrong diagnosis) After (correct)
Destination: thought to be a provider bug → null_resource + Python Destination: eventual consistency → newrelic_entity_tags + timeouts { create = "5m" }
Alert policy: no entity_guid + lag → Python Alert policy: no entity_guid → still needs Python, but now we understand it's a different root cause
The null_resource/Python path is now only needed for the alert policy, and for a much cleaner reason: the GUID simply doesn't exist in the Terraform resource state at all. The module, variables, and README are all updated to reflect this.

Main
TF

Variables
TF

Readme
Document · MD

Skip to content newrelic terraform-provider-newrelic Repository navigation Code Issues 100 (100) Pull requests 76 (76) Discussions Actions Projects Security and quality Insights newrelic_entity_tags: expected entity tag to have been created but was not found #2886 Open Open newr

pasted

The page navigation is complete. You may now navigate the page content as you wish.Skip to main content | Registry Browse Publish Sign In Search providers, modules, run tasks, and policies... / Providers newrelic newrelic v3.88.0 newrelic newrelic Partner newrelic/newrelic Down

pasted

The page navigation is complete. You may now navigate the page content as you wish.Skip to main content | Registry Browse Publish Sign In Search providers, modules, run tasks, and policies... / Providers newrelic newrelic v3.88.0 newrelic newrelic Partner newrelic/newrelic Down

pasted

Skip to content newrelic terraform-provider-newrelic Repository navigation Code Issues 100 (100) Pull requests 76 (76) Discussions Actions Projects Security and quality Insights Error: expected entity tag team to have been updated but was not found #1556 Closed Closed Error: exp

pasted

Skip to content newrelic terraform-provider-newrelic Repository navigation Code Issues 100 (100) Pull requests 76 (76) Discussions Actions Projects Security and quality Insights Error: expected entity tag team to have been updated but was not found #1556 Closed Closed Error: exp

pasted

Skip to content newrelic terraform-provider-newrelic Repository navigation Code Issues 100 (100) Pull requests 76 (76) Discussions Actions Projects Security and quality Insights expected entity tag to have been created but was not found #2633 Closed as not planned @maathor Descr

pasted

ok.. going t paste a lot more info... read and thin kthorugh it... and provide soem high level suggestions... and we will go form there

from:
https://github.com/newrelic/terraform-provider-newrelic/issues/2886

then from: https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/service_level#attributes-reference

and from
https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/service_level#attributes-reference

from:
https://github.com/newrelic/terraform-provider-newrelic/issues/1556#issuecomment-1338011778

from:
https://github.com/newrelic/terraform-provider-newrelic/issues/2633

Show more
2:54 PM
Good call — let me read all of this carefully before suggesting anything.

What these four sources actually tell us
Issue #2886 (destination eventual consistency)
Already covered last round. The key finding: timeouts { create = "5m" } on newrelic_entity_tags fixes destinations because it's a catalog lag issue, not a provider bug.

The service_level docs (issues #2633 and the registry page)
This is the really interesting one. Issue #2633 was being diagnosed as an entity tags bug, but the actual root cause was using the wrong GUID attribute. newrelic_service_level has TWO guid-like outputs:

.guid — the GUID of the entity being monitored (the APM app, etc.) — this is an input that gets re-exported
.sli_guid — the GUID of the SLI entity itself
When people used .guid for tagging, they were accidentally tagging the upstream app entity, not the service level. Multiple service levels all pointing at the same app meant multiple newrelic_entity_tags resources fighting over the same entity GUID, which caused the cascade failure. The fix is simply using .sli_guid instead.

Issue #1556 (the long-running "expected entity tag to have been updated" thread)
This one reveals something broader. The same error message surfaces from multiple completely different root causes:

API eventual consistency (catalog lag) — fixed by timeouts/retries
Wrong GUID being passed — guid vs sli_guid on service levels
for_each on newrelic_entity_tags itself — using for_each to create multiple separate newrelic_entity_tags resources (one per tag key) hammers the same entity with parallel writes and they race each other. The fix is one newrelic_entity_tags resource per entity with a dynamic "tag" block inside it — NOT one resource per tag.
Excessive parallelism under load — less relevant for us
The contributor from New Relic confirmed: one newrelic_entity_tags per entity, all tags as dynamic blocks inside, never loop newrelic_entity_tags itself with count or for_each.

High-level implications for our module
Good news: Our current module already does this correctly. We have one newrelic_entity_tags per entity with dynamic "tag" blocks. We're not making the for_each-on-the-tags-resource mistake.

Things worth revisiting:

The dynamic "tag" pattern — we're using for_each = local.common_tags (a map) inside the dynamic block. The sanderblue example from NR uses a toset() approach for entities but still maps tags with for_each. Our pattern is correct but worth double-checking the iteration value access (tag.key / tag.value for a map is right).
Alert conditions — conditions export entity_guid directly and we use a single newrelic_entity_tags per condition with a dynamic block. That's the canonical correct pattern. No issue here.
Destination — already fixed with timeouts { create = "5m" }. Still correct.
Alert policy — still the NerdGraph escape hatch. Nothing in these issues changes that — the problem remains that the resource doesn't export a GUID.
If you ever add newrelic_service_level to this module later — the lesson from #2633 is critical: use .sli_guid not .guid when passing to newrelic_entity_tags.
What I'd suggest doing next
There are a few small defensive improvements worth making to the existing module based on all of this:

A) Add a timeouts { create = "5m" } block to the alert condition newrelic_entity_tags resources too, not just the destination. The catalog lag is a platform-wide issue and conditions could theoretically hit it too, especially if Terraform is applying many resources in parallel.

B) Add a comment to the dynamic "tag" blocks explicitly noting the anti-pattern to avoid (for_each on newrelic_entity_tags itself) — so future maintainers don't "fix" it incorrectly.

C) Pre-wire a newrelic_service_level resource stub (commented out) that correctly uses .sli_guid — since teams will almost certainly want SLOs next, and the guid/sli_guid trap is easy to fall into.

D) Add a timeouts variable to the module so the wait time is configurable rather than hardcoded — in case someone is operating in a region where catalog lag is worse.

Want me to implement those changes, or are there other areas from these issues you want to discuss first?

hmmm... so what do you recommend ?

3:06 PM
Based on everything we've read, here's my honest recommendation:

The core insight from all these issues
The error message expected entity tag X to have been created but was not found is one error message with four different root causes. That's what made it so confusing across all those threads. Let me separate them cleanly:

Root cause Affected resource Fix
NR entity catalog lag (~60-70s) newrelic_notification_destination timeouts { create = "5m" } — already in our module
No entity_guid exported at all newrelic_alert_policy NerdGraph via Python — already in our module
for_each on newrelic_entity_tags itself (parallel writes to same entity) Any entity when tags are looped wrong One newrelic_entity_tags per entity with dynamic "tag" inside — already correct in our module
Wrong GUID attribute newrelic_service_level specifically Use .sli_guid not .guid — not in our module yet but will matter when you add SLOs
Our module is already doing the right thing for the resources we have. The question is whether to add defensive improvements.

My actual recommendation
Don't over-engineer it right now. Here's why:

The module is correct. The patterns are right. Adding more complexity to guard against things that aren't broken yet just creates noise for future maintainers to read through.

What I'd focus on instead is three small, high-value additions:

1. Add timeouts { create = "5m" } to the alert condition tags too
   Not because conditions are known to have catalog lag, but because the lag is a platform-wide NR behavior. If you're ever applying this module for many teams simultaneously (high parallelism), conditions could hit it too. It costs nothing and makes the module more resilient.

2. Add a commented-out newrelic_service_level block with .sli_guid
   Teams almost always want SLOs after they set up alerting. The guid vs sli_guid trap from issue #2633 is completely non-obvious — the resource accepts guid as input and re-exports it as an attribute, so it looks right until it silently tags the wrong entity. A pre-wired stub with the correct attribute and a clear comment saves the next person from a frustrating debugging session.

3. Lock the provider version more tightly
   The issues show this problem has been present and regressing across many provider versions (2.30, 2.34, 2.46, 2.49, 3.0, 3.6, 3.62...). Right now we have version = "~> 3.0" which allows any 3.x. Given how much behavior varies across patch versions, I'd pin to ~> 3.88.0 (the current version from the registry page you shared) so you're not surprised by regressions.

What I'd leave alone
The null_resource + Python approach for alert policy tagging. The issues we read don't offer a better path — the fundamental problem (no exported GUID) hasn't been fixed in the provider. NerdGraph is still the right escape hatch.
The Harness pipeline approach. It's still the cleanest option for teams already on Harness and nothing in these issues changes that calculus.
The dynamic "tag" pattern. It's already correct. Don't touch it.
Bottom line
Make those three targeted changes and call the module done. Want me to implement them?

ok... so give the run down on hpw to appreaoch all of these

ow I have a complete picture. Let me build the Terraform module. Here's the key summary of what I found before writing the code:
Tagging support per resource:
ResourceTaggable?Hownewrelic_nrql_alert_condition✅ Yesexposes entity_guid → use newrelic_entity_tagsnewrelic_notification_destination⚠️ Partiallyexposes guid, but there's a known bug (#2886) where entity tags silently fail for destinations — best workaround is naming conventionsnewrelic_workflow✅ Yesthe workflow filter predicate uses accumulations.tag.team to route by team tagnewrelic_alert_policy⚠️ No native entity_guidthe newrelic_alert_policy resource does NOT export an entity_guid — you must look up the policy entity via newrelic_entity data source and use NerdGraph/newrelic_entity_tags

oh... add on tagging new relic muting rules

Show more
3:30 PM
Great — let me give you the complete, definitive rundown on every resource, incorporating everything we've learned, including muting rules.

Complete Tagging Rundown
newrelic_nrql_alert_condition
Status: ✅ Clean — pure Terraform

Exports entity_guid directly. One newrelic_entity_tags resource per condition, all tags as dynamic "tag" blocks inside. Add timeouts { create = "5m" } defensively for catalog lag under parallelism.

hcl
resource "newrelic_entity_tags" "condition_tags" {
guid = newrelic_nrql_alert_condition.this.entity_guid

dynamic "tag" {
for_each = local.common_tags
content {
key = tag.key
values = [tag.value]
}
}

timeouts { create = "5m" }
}
newrelic_notification_destination
Status: ✅ Fixed — pure Terraform with timeout

Was misdiagnosed as a provider bug. Actually NR entity catalog eventual consistency (~60-70s lag). timeouts { create = "5m" } makes Terraform retry until the catalog is ready, then stops immediately. No Python, no sleep hacks.

hcl
resource "newrelic_entity_tags" "destination_tags" {
guid = newrelic_notification_destination.this.guid

dynamic "tag" {
for_each = local.common_tags
content {
key = tag.key
values = [tag.value]
}
}

timeouts { create = "5m" }
}
newrelic_alert_policy
Status: ⚠️ Escape hatch required — NerdGraph via Python

The resource does not export entity_guid at all. A newrelic_entity data source lookup (type = "POLICY", domain = "AIOPS") exists but suffers from the same catalog lag, and unlike newrelic_entity_tags there is no timeout retry on a data source — it just fails. Two options:

Option A — inline null_resource (single terraform apply, needs python3 + requests on runner):

hcl
resource "null_resource" "tag_policy" {
triggers = {
policy_id = newrelic_alert_policy.this.id
tags_hash = jsonencode(local.common_tags)
}

provisioner "local-exec" {
command = "python3 nr_tag_resources.py --from-env --policy-name \"${newrelic_alert_policy.this.name}\""
environment = {
NR_API_KEY = var.nr_api_key
NR_ACCOUNT_ID = var.account_id
NR_TEAM = var.team
}
}
}
Option B — pipeline stage (set enable_nerdgraph_tagging = false, run nr_tag_resources.py in a separate Harness stage reading terraform output -json). Cleaner separation, nothing special needed on the Terraform runner.

newrelic_workflow
Status: ✅ Handled differently — not directly taggable

Workflows do not expose an entity GUID. But they don't need to be tagged in the traditional sense — the issues_filter predicate using accumulations.tag.team IS the team association. The workflow routes issues to the right team by matching tags on the conditions that fired. This is the idiomatic NR pattern.

hcl
issues_filter {
name = "${var.team}-filter"
type = "FILTER"

predicate {
attribute = "accumulations.tag.team"
operator = "EXACTLY_MATCHES"
values = [var.team]
}
}
newrelic_alert_muting_rule ← new
Status: ⚠️ Needs research — let me check now

Searched the web
Searched the web
Now I have the full picture on muting rules. Here's the complete definitive rundown:

Complete Resource Tagging Rundown
newrelic_nrql_alert_condition
✅ Pure Terraform — straightforward

Exports entity_guid directly. Use newrelic_entity_tags with a dynamic "tag" block. Add timeouts { create = "5m" } defensively since catalog lag is a platform-wide NR behavior that can bite under parallelism.

hcl
resource "newrelic_entity_tags" "condition_tags" {
guid = newrelic_nrql_alert_condition.this.entity_guid

dynamic "tag" {
for_each = local.common_tags
content {
key = tag.key
values = [tag.value]
}
}

timeouts { create = "5m" }
}
Anti-pattern to never do: for_each on the newrelic_entity_tags resource itself (one resource per tag key). That causes parallel writes to the same entity and races. Always one newrelic_entity_tags per entity, all tags inside a single dynamic block.

newrelic_notification_destination
✅ Pure Terraform — needs timeout

Root cause was misdiagnosed as a provider bug for years. It's NR entity catalog eventual consistency — the entity isn't taggable until ~60-70s after creation. timeouts { create = "5m" } makes Terraform retry automatically and stop as soon as it lands.

hcl
resource "newrelic_entity_tags" "destination_tags" {
guid = newrelic_notification_destination.this.guid

dynamic "tag" {
for_each = local.common_tags
content {
key = tag.key
values = [tag.value]
}
}

timeouts { create = "5m" }
}
newrelic_alert_policy
⚠️ NerdGraph escape hatch required

The resource simply does not export entity_guid. A newrelic_entity data source lookup (type = "POLICY", domain = "AIOPS") technically works but has no timeout retry mechanism unlike newrelic_entity_tags — the data source fails immediately on catalog lag rather than retrying. Two clean options:

Option A — null_resource + Python (inline, single apply):

hcl
resource "null_resource" "tag_policy" {
triggers = {
policy_id = newrelic_alert_policy.this.id
tags_hash = jsonencode(local.common_tags)
}
provisioner "local-exec" {
command = "python3 nr_tag_resources.py --from-env --policy-name \"${newrelic_alert_policy.this.name}\""
environment = {
NR_API_KEY = var.nr_api_key
NR_ACCOUNT_ID = var.account_id
NR_TEAM = var.team
}
}
}
Option B — pipeline stage reading terraform output -json. Cleaner for Harness users — Stage 1 outputs policy name, Stage 2 calls nr_tag_resources.py.

newrelic_workflow
✅ Not directly taggable — but doesn't need to be

No entity GUID exposed. But this is intentional — the issues_filter predicate using accumulations.tag.team is the team association. The workflow routes issues by matching tags on the conditions that fired. That IS the tagging.

hcl
issues_filter {
predicate {
attribute = "accumulations.tag.team"
operator = "EXACTLY_MATCHES"
values = [var.team]
}
}
newrelic_alert_muting_rule ← new
✅ Handled via condition attributes — not newrelic_entity_tags

This one is fundamentally different from all the others. Muting rules don't use newrelic_entity_tags at all — they filter which incidents to mute via a condition block whose attribute field supports tags.<NAME> directly. So to scope a muting rule to a team, you use attribute = "tags.team" inside the muting rule's own condition. No separate tagging resource needed.
Terraform Registry

hcl
resource "newrelic_alert_muting_rule" "team_maintenance" {
account_id = var.account_id
name = "${var.team}-maintenance-window"
enabled = true
description = "Mute ${var.team} alerts during deployments"

condition { # Match incidents where the team tag equals this team
conditions {
attribute = "tags.team"
operator = "EQUALS"
values = [var.team]
} # Optionally AND with a policy scope
conditions {
attribute = "policyName"
operator = "EQUALS"
values = ["${var.team}-alert-policy"]
}
operator = "AND"
}

# Optional scheduled window (e.g. deployment window)

schedule {
start_time = "2024-01-01T02:00:00"
end_time = "2024-01-01T04:00:00"
time_zone = "America/New_York"
repeat = "WEEKLY"
weekly_repeat_days = ["TUESDAY"]
}
}
The muting rule itself exports only id — no entity GUID, no tagging surface. But it doesn't need one because it is already scoped to the team via the tags.team filter condition. The rule is inherently team-aware.

Summary table — definitive
Resource Tagging approach Key detail
newrelic_nrql_alert_condition newrelic_entity_tags + timeouts { create = "5m" } Exports entity_guid directly. One resource, dynamic block inside.
newrelic_notification_destination newrelic_entity_tags + timeouts { create = "5m" } Catalog lag, not a provider bug. Timeout fixes it.
newrelic_alert_policy null_resource + Python NerdGraph or pipeline stage No entity_guid exported at all. Fundamentally different problem.
newrelic_workflow issues_filter predicate (accumulations.tag.team) No GUID exposed. Filter IS the team association.
newrelic_alert_muting_rule condition { attribute = "tags.team" } inline Uses its own condition syntax. No newrelic_entity_tags needed or possible.
Want me to update the module to add the muting rule resource with all of this wired in?

so can i put in a timer for all the tagging except workflows ?

i woudl prefer a more standard fix... even though not great... it is ok

3:36 PM
Yes — and it's actually the cleanest approach. The timeouts { create = "5m" } block is already supported on newrelic_entity_tags and is the officially acknowledged workaround for the catalog lag issue. Applying it universally to every newrelic_entity_tags resource in the module is completely reasonable.

Here's the thinking before touching anything:

Where it helps vs where it's a no-op:

Resource Does timeout help? Why
newrelic_nrql_alert_condition ✅ Defensive Conditions are usually fast but catalog lag can hit under parallelism
newrelic_notification_destination ✅ Confirmed fix This is exactly what issue #2886 validated
newrelic_alert_policy ❌ Can't use it No entity_guid exported — can't even reach newrelic_entity_tags
newrelic_workflow ❌ N/A Not tagged via newrelic_entity_tags at all
newrelic_alert_muting_rule ❌ N/A Uses its own condition syntax, not newrelic_entity_tags
So the answer is: yes, add timeouts { create = "5m" } to every newrelic_entity_tags block in the module — conditions and destination. Alert policy still needs the NerdGraph path because the timeout can't help when there's no GUID to pass in the first place.

Let me update the module now:

Read current module main.tf
Read current module main.tf
Good. Three newrelic_entity_tags blocks need the timeout added: destination_tags already has it, high_error_rate_tags and high_latency_tags don't. Also need to add the muting rule. Let me also extract a tag_timeout variable so it's configurable in one place.

Rewrite module main.tf with universal timeouts and muting rule
Rewrite module main.tf with universal timeouts and muting rule
Now update variables.tf to add tag_timeout, create_muting_rule, muting_rule_enabled, and muting_schedule:

Ran 2 commands, read a file
Ran 2 commands, read a file
Here's the summary of exactly what was done and why:

What changed
Universal timeouts { create = var.tag_timeout } on all newrelic_entity_tags
Every newrelic_entity_tags block now has the timeout — destination, error rate condition, and latency condition. The timeout value comes from a single var.tag_timeout variable (default "5m") so you can tune it in one place rather than hunting through three resources.

The logic: the timeout costs absolutely nothing when not needed — Terraform stops retrying the moment the tag confirms. But it saves you when catalog lag hits. Conditions are usually fast but under a large parallel apply (many teams at once) they can hit the same lag the destination does.

Alert policy cannot get this treatment — and this is the key distinction to remember. The timeout only helps when you can get a GUID into newrelic_entity_tags. The policy doesn't export one at all, so the timeout is irrelevant. That's why it stays on the NerdGraph path.

Muting rule added
Uses attribute = "tags.team" inside its own condition block — that's the native way muting rules scope by team. No newrelic_entity_tags involved at all. Controlled by two variables: create_muting_rule (whether to create it) and muting_rule_enabled (whether it's actively muting). The separation lets you pre-create the rule with enabled = false and flip it on during deployments without a full terraform apply.

Main
TF

Variables
TF

Outputs
TF
updat eteh readme and rpint it here

3:57 PM

Ran 2 commands, viewed a file, read a file
Ran 2 commands, viewed a file, read a file
Here it is rendered:

New Relic Team Alerting Module
A Terraform module that creates and tags all alerting infrastructure for a team in New Relic: alert policy, alert conditions, notification destination, channel, workflow, and an optional muting rule.

Tagging — the honest breakdown
Every resource type has a different tagging story. This is the result of researching the provider source, registry docs, and several GitHub issues.

Per-resource matrix
Resource Tagging method Why
newrelic_nrql_alert_condition newrelic_entity_tags + timeouts { create } Exports entity_guid directly. Timeout added defensively — catalog lag is platform-wide and can bite conditions under high parallelism.
newrelic_notification_destination newrelic_entity_tags + timeouts { create } Was misdiagnosed as a provider bug for years. Actually NR entity catalog eventual consistency (~60-70s lag). Timeout makes Terraform retry until the tag lands, then stops immediately. issue #2886
newrelic_alert_policy null_resource + Python NerdGraph or pipeline stage Fundamentally different problem — the resource does not export entity_guid at all. A newrelic_entity data source lookup also fails (no retry on the lookup itself). NerdGraph called from Python is the only reliable path. issue #2492
newrelic_workflow issues_filter predicate (accumulations.tag.team) No entity GUID exposed. The filter predicate IS the team association — the workflow routes issues by matching the team tag on the conditions that fired.
newrelic_alert_muting_rule condition { attribute = "tags.team" } inline Uses its own condition syntax natively. No newrelic_entity_tags needed or possible — the resource only exports id. The muting rule is already team-scoped via its condition.
newrelic_notification_channel Not taggable No entity GUID exposed by provider.
The key distinction everyone gets confused by
newrelic_notification_destination and newrelic_alert_policy both fail with newrelic_entity_tags, but for completely different reasons:

Destination — catalog lag. The GUID exists and is exported. timeouts { create = "5m" } fixes it entirely. No Python needed.
Alert policy — missing GUID. The resource simply doesn't export one. No amount of waiting helps. NerdGraph is required.
Why timeouts on every newrelic_entity_tags
The timeout is applied universally (controlled by var.tag_timeout, default "5m") rather than only on destinations. Reasoning:

NR's entity catalog lag is a platform-wide behavior, not specific to destinations.
Under parallelism (multiple teams applied simultaneously) any entity type can hit it.
The timeout costs nothing when not needed — Terraform stops retrying the moment the tag confirms.
A single variable controls all of them, so tuning for EU region or large applies is one line.
Anti-pattern to never do
Never use for_each or count on newrelic_entity_tags itself (one resource per tag key). That creates parallel writes to the same entity GUID and they race each other, causing intermittent failures. Always: one newrelic_entity_tags per entity, all tags inside a single dynamic "tag" block. issue #1556

Alert policy tagging — two approaches
Approach A: Inline null_resource (default)
Set enable_nerdgraph_tagging = true (default). Terraform runs nr_tag_resources.py via local-exec after the policy is created. Single terraform apply does everything.

Requires: python3 + pip install requests on the Terraform runner.

Approach B: Separate pipeline stage
Set enable_nerdgraph_tagging = false. Terraform creates resources only. A post-apply step runs nr_tag_resources.py reading terraform output -json. See harness-pipeline.yaml for the full two-stage Harness setup.

Requires: Nothing special on the Terraform runner. Python runs in its own pipeline container.

File structure
newrelic-team-module/
├── README.md
├── main.tf # root — calls the module for each team
├── variables.tf # root variables
├── nr_tag_resources.py # NerdGraph policy tagger (Approaches A + B)
├── harness-pipeline.yaml # two-stage Harness pipeline (Approach B)
└── modules/
└── newrelic_team_alerting/
├── main.tf # all NR resources + tagging logic
├── variables.tf # all module inputs
└── outputs.tf # IDs/GUIDs for pipeline consumption
Usage
hcl
module "platform_team" {
source = "./modules/newrelic_team_alerting"

# Core

account_id = var.newrelic_account_id
team = "platform"
alert_email = "platform-oncall@example.com"
app_name = "platform-api"

# Extra tags applied to everything alongside the team tag

extra_tags = {
env = "production"
cost_center = "eng-platform"
}

# Tagging timeout — applied to all newrelic_entity_tags resources

# Increase if you see intermittent failures on large parallel applies

tag_timeout = "5m"

# Alert policy NerdGraph tagging (Approach A — inline)

enable_nerdgraph_tagging = true
nr_api_key = var.newrelic_api_key
nr_region = "US"

# Muting rule — create it disabled; flip muting_rule_enabled=true per deploy

create_muting_rule = true
muting_rule_enabled = false

# Optional scheduled muting window

muting_schedule = {
start_time = "2024-01-01T02:00:00"
end_time = "2024-01-01T04:00:00"
time_zone = "America/New_York"
repeat = "WEEKLY"
weekly_repeat_days = ["TUESDAY"]
repeat_count = null
}
}
What gets created per team
Resource Name Tagging approach
newrelic_notification_destination {team}-email-destination newrelic_entity_tags + timeouts { create = var.tag_timeout }
newrelic_notification_channel {team}-email-channel Not taggable
newrelic_alert_policy {team}-alert-policy NerdGraph via Python (null_resource or pipeline stage)
newrelic_nrql_alert_condition {team}-high-error-rate newrelic_entity_tags + timeouts { create = var.tag_timeout }
newrelic_nrql_alert_condition {team}-high-latency newrelic_entity_tags + timeouts { create = var.tag_timeout }
newrelic_workflow {team}-workflow issues_filter predicate (accumulations.tag.team)
newrelic_alert_muting_rule {team}-maintenance-window condition { attribute = "tags.team" } — no separate tagging resource needed
Key variables
Variable Default Description
team required Team name — used as tag value and resource name prefix
alert_email required Email for alert notifications
app_name "my-app" App name in New Relic (used in NRQL queries)
extra_tags {} Additional tags merged with team tag
tag_timeout "5m" Timeout for all newrelic_entity_tags create operations
enable_nerdgraph_tagging true true = inline Python tagging of policy; false = skip (use pipeline)
nr_api_key "" NR User API key for NerdGraph (needed when enable_nerdgraph_tagging = true)
nr_region "US" NR region for NerdGraph endpoint (US or EU)
create_muting_rule false Whether to create the muting rule resource
muting_rule_enabled false Whether the muting rule is actively muting
muting_schedule null Optional schedule object for the muting window
Source references
Topic Link
newrelic_entity_tags resource docs https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/entity_tags
newrelic_alert_condition entity_guid https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/alert_condition
Destination catalog lag (issue #2886) https://github.com/newrelic/terraform-provider-newrelic/issues/2886
Alert policy missing entity_guid (issue #2492) https://github.com/newrelic/terraform-provider-newrelic/issues/2492
for_each anti-pattern (issue #1556) https://github.com/newrelic/terraform-provider-newrelic/issues/1556
newrelic_workflow filter docs https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/workflow
newrelic_alert_muting_rule docs https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/alert_muting_rule
newrelic_service_level sli_guid trap (issue #2633) https://github.com/newrelic/terraform-provider-newrelic/issues/2633

Readme
Document · MD

## Claude is AI and can make mistakes. Please double-check responses.

Good question — let me be precise about this because it matters.

## The timeout is NOT what does the tagging

The `timeouts { create = "5m" }` block doesn't tag anything. It just tells Terraform **how long to keep retrying** after `newrelic_entity_tags` has already written the tag and is waiting for NR's API to confirm it landed.

The flow is:

1. Resource gets created (destination, condition, etc.)
2. `newrelic_entity_tags` writes the tag via NR API
3. NR's entity catalog takes time to index it
4. Terraform polls: "is the tag there yet?"
5. Without timeout → fails after ~20s
6. With timeout → keeps polling for up to 5 minutes, succeeds at ~70s

So the timeout is just a **patience setting** on top of `newrelic_entity_tags`.

---

## Can they ALL be done the same way?

**Almost — but alert policy breaks the pattern entirely**, and for a completely unrelated reason.

| Resource                            | Can use `newrelic_entity_tags` + timeout? | Why                                                                                                                                                                |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `newrelic_nrql_alert_condition`     | ✅ Yes                                    | Exports `entity_guid` → pass it to `newrelic_entity_tags`                                                                                                          |
| `newrelic_notification_destination` | ✅ Yes                                    | Exports `.guid` → pass it to `newrelic_entity_tags`, add timeout for catalog lag                                                                                   |
| `newrelic_alert_policy`             | ❌ No                                     | **Does not export any GUID at all** — `newrelic_entity_tags` requires a GUID to even start. The timeout can't help when there's nothing to pass in the first place |

The policy problem has nothing to do with catalog lag or timing. The Terraform resource simply never gives you the GUID. Even if you waited 10 minutes, you'd still have no GUID to hand to `newrelic_entity_tags`. That's why it needs the NerdGraph escape hatch — it's a completely different class of problem.

---

## The simple mental model

```
Does the resource export a GUID?
        │
       YES → newrelic_entity_tags + timeouts { create = "5m" }  ✅
        │
        NO → NerdGraph via Python (look up the GUID yourself)   ⚠️
        │
  (alert policy is the only one in this module that falls here)
```

So: same pattern for conditions and destinations — yes. Alert policy — fundamentally different, no shortcut available.
