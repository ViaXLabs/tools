Done — tested the mail-building logic end to end (recipients, HTML body, attachments, missing-attachment handling) before packaging it up. Three files:

- **`send-email-template-cd-custom.yaml`** — Step Template for CD/Custom/Approval stages (runs as a Shell Script step on the Delegate)
- **`send-email-template-ci-build.yaml`** — same template, rebuilt as a CI `Run` step, since Harness's stage-type split means one step type can't cover both worlds — this pair is the "works everywhere" answer
- **`example-pipeline-using-send-email-templates.yaml`** — a skeleton pipeline calling both, so you can see the exact `templateInputs:` shape to paste into your own pipelines

Both templates take the same inputs (`MAIL_TO`, `CC`, `SUBJECT`, `BODY_HTML`, `ATTACHMENTS`, SMTP settings) and auto-append a footer to every email with the pipeline name, build number, who triggered it, the send timestamp, and a link straight to that execution (`<+pipeline.executionUrl>`) — so calling pipelines get that for free without passing anything extra.

One thing I couldn't see: your existing working step's actual credential wiring. I used plain SMTP host/user/password (password as a Harness secret) since that's the documented, portable pattern — swap the `SMTP_*` lines for however your real connector/secret is referenced if it differs. Full usage YAML is also in the comment header of each file.The three files are above.
