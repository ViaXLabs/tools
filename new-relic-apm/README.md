# New Relic Java APM Agent — Docker Demo

A minimal, working example of attaching the New Relic Java APM agent to a
containerized Java app, including custom app tags (labels) so it's easy to
find and filter in New Relic.

## What's in here
- `HelloWorld.java` — a tiny long-running app. It has to stay alive for a
  bit, or the agent never gets a chance to connect and report anything.
- `Dockerfile` — multi-stage build: compile the app, download the agent,
  assemble a slim runtime image.
- `docker-compose.yml` — convenience wrapper for local runs.

## The three moving pieces

These are independent of each other — worth understanding separately so you
can debug each one on its own if something isn't showing up.

1. **The agent itself.** `newrelic.jar` gets copied into the image and
   loaded as a JVM instrumentation agent via
   `-javaagent:/app/newrelic/newrelic.jar` on the `java` command line. This
   is the thing that actually instruments the JVM at startup — without it,
   none of the config below matters.

2. **Required config.** The agent needs a license key and an app name.
   Set these as environment variables at *runtime*, not baked into the
   image:
   - `NEW_RELIC_LICENSE_KEY` — from your New Relic account (API keys page)
   - `NEW_RELIC_APP_NAME` — the name the app shows up under in APM & Services

3. **Tags** (what you called "agent tagging"). New Relic calls these
   labels/tags — `key:value` pairs attached to the entity so you can filter
   and group apps in the UI by team, environment, service, etc.:
   ```
   NEW_RELIC_LABELS="Environment:dev;Team:platform;Service:hello-java-sample"
   ```
   Multiple tags are semicolon-separated; each pair is `Key:Value`. These
   are New Relic entity tags, not to be confused with Docker image tags
   (`docker build -t name:tag`) — different concept, same word.

## Running it

```bash
docker build -t hello-java-newrelic .

docker run --rm \
  -e NEW_RELIC_LICENSE_KEY="YOUR_LICENSE_KEY_HERE" \
  -e NEW_RELIC_APP_NAME="hello-java-sample" \
  -e NEW_RELIC_LABELS="Environment:dev;Team:platform;Service:hello-java-sample" \
  hello-java-newrelic
```

Or with compose:

```bash
NEW_RELIC_LICENSE_KEY=YOUR_LICENSE_KEY_HERE docker compose up --build
```

## Verifying it worked

- Give it a minute or two — the agent's default harvest cycle is ~60s.
- In New Relic, go to **APM & Services** — you should see `hello-java-sample`.
- Open the entity and click the **Tags** tab — you should see
  `Environment: dev`, `Team: platform`, `Service: hello-java-sample`.
- If nothing shows up: check the container logs for `NEW_RELIC` startup
  lines (the agent logs to stdout because of `NEW_RELIC_LOG_FILE_NAME=STDOUT`),
  and double-check the license key isn't a placeholder.

## Applying this to your actual app

Don't copy this whole demo — pull just these pieces into your existing
Dockerfile:

- The "fetch the agent" `RUN curl ... unzip ...` block
- Copying the resulting `./newrelic` folder into your final image stage
- Adding `-javaagent:/path/to/newrelic.jar` to your `java` command line
  (it needs to come before `-jar yourapp.jar` / your main class)
- The three `NEW_RELIC_*` environment variables above

If your app runs on Tomcat, Spring Boot, or another supported framework,
none of your app code needs to change — the agent auto-instruments it and
you'll get full transaction traces immediately.

## Getting real transaction traces (optional next step)

This demo app has no web framework or job queue, so New Relic will show
host/JVM metrics but no transaction traces — there's nothing
"transaction-shaped" happening for the agent to name. If your real app is a
background/batch process like this one, you can manually mark units of work
using the New Relic Java API:

```java
import com.newrelic.api.agent.Trace;

public class Worker {
    @Trace(dispatcher = true)
    public void doWork() {
        // this method now reports as a transaction in APM
    }
}
```

That requires adding `newrelic-api.jar` (already sitting in the same zip
you downloaded) to your compile classpath. Ask if you want a walkthrough —
it's a small addition to the Dockerfile's build stage.
