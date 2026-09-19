Now let me also add the metadata-footer suggestion explicitly into the usage comments, and regenerate/validate:Let me do a final visual check of both files before shipping:This looks correct and clean. Let's ship the two plugin-based files:Since you have K8s, here's the "don't reinvent the wheel" version — replaces the custom curl/MIME script with Harness's own maintained plugin:

- **`send-email-template-ci-plugin.yaml`** — Step Template for CI Build stages, wrapping `plugins/email` (Harness Support's documented answer to "email + attachments in CI")
- **`send-email-stepgroup-cd-custom-plugin.yaml`** — same plugin for Custom/CD stages, but as a **Step Group Template**, not a plain step. That's a real platform constraint, not a choice: a `Plugin` step outside CI Build must run inside a containerized step group, and the Kubernetes infra binding lives on the group, not the step — so bundling it is what makes this a true drop-in-anywhere unit.

Trade-offs worth knowing:

- Recipients and attachments go in as comma-separated strings (the plugin's flags accept lists; comma-separated is the standard way to feed a list through one setting). No distinct Cc — everyone in `recipients` is treated the same.
- The automatic "pipeline metadata" footer isn't baked in server-side anymore (there's no script to inject it) — it's a copy-paste snippet in each file's usage comment that you include in your own `body` when calling the template. I deliberately didn't try to fake an always-on default for this, since I couldn't verify Harness resolves a nested `<+pipeline...>` expression inside a template's `.default(...)` value.

The earlier two files (`send-email-template-cd-custom.yaml`, `send-email-template-ci-build.yaml`) are the fallback if you ever need real Cc semantics, multiple guaranteed attachments, or no K8s dependency — otherwise these two plugin-based ones are the better default.Both files are above.
