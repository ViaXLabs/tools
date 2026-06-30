# New Relic APM + Docker Integration Guide

**Scope:** Java, Python, Node.js, and Ruby services running in Docker, deployed to AWS ECS and EKS.
**Audience:** Engineers integrating or troubleshooting New Relic APM on existing Dockerized services.
**Last reviewed:** _add date when you publish_

---

## 1. The Two-Layer Mental Model

New Relic splits container monitoring into two independent systems. Most integration confusion comes from mixing these up.

| | Infrastructure Agent | APM Agent |
|---|---|---|
| What it watches | The host/node — CPU, memory, Docker socket, container lifecycle | Your actual app process — transactions, traces, errors |
| Runs as | Sidecar container (ECS) or DaemonSet (EKS) | Embedded in your app's own container |
| Config method | Environment variables (`NRIA_*`) or `newrelic-infra.yml` | Differs per language — see Section 3 |
| Knows about your code? | No — sees containers as black boxes | Yes — this is what populates the APM Summary page |

> ⚠️ **Most common root cause of "no data showing up":** confusing `NRIA_*` (infra agent) environment variables with `NEW_RELIC_*` (APM agent) environment variables. They are not interchangeable and not read by the same agent.

---

## 2. Prerequisites — Check the Base Image First

Before touching any New Relic config, validate the base image itself. A base image problem looks identical to a "New Relic isn't reporting" problem, so rule this out first.

### Run this on every image before debugging anything else

```bash
docker run --rm <your-image> sh -c "cat /etc/os-release; ldd --version 2>&1 | head -1"
```

This single command tells you the Linux distro and whether you're on **glibc** or **musl** — the most common silent failure point.

### Universal checklist (all languages)

- [ ] Base image is Linux (not `scratch`, not Windows containers unless using the .NET Windows agent path)
- [ ] Architecture matches your build/deploy target — `amd64` vs `arm64` (Graviton ECS/EKS nodes are arm64; Apple Silicon dev machines build arm64 by default — mismatches cause `exec format error` or silently broken binaries)
- [ ] Outbound HTTPS (443) reachable from the container to `collector.newrelic.com` (or your region's host) — check security groups, NACLs, and service mesh/sidecar proxies
- [ ] Container user has write permission to the agent's log directory

### glibc vs musl — why it matters

| Base image type | Examples | Notes |
|---|---|---|
| glibc | `debian`, `ubuntu`, most `*-slim` variants | Safer default for Java and any native extensions |
| musl | `alpine`, `*-alpine` variants | Smaller images, but not all agent binaries are musl-compatible |

### Per-language prerequisite checks

| Language | Check | Command | glibc OK? | musl/Alpine OK? |
|---|---|---|---|---|
| Java | JDK/JRE version supports your pinned agent version | `java -version` | ✅ Preferred | ⚠️ Avoid if possible — JVM has known issues on musl |
| Python | Python version supports your pinned `newrelic` pip version | `python --version` | ✅ | ✅ Generally fine |
| Node.js | Node version supports your pinned `newrelic` npm version | `node --version` | ✅ | ✅ Generally fine |
| Ruby | Ruby + Bundler version supports `newrelic_rpm` gem range | `ruby --version && bundler --version` | ✅ | ✅ but check native gem build deps (`build-base` on Alpine) |

---

## 3. Per-Language Setup — Concrete Files

### 3.1 Java

**Dockerfile**
```dockerfile
FROM tomcat:9-jdk17

# Copy app
COPY my-app.war /usr/local/tomcat/webapps/

# Copy New Relic agent jar + config into the image
ADD newrelic/newrelic.jar /usr/local/tomcat/newrelic/newrelic.jar
ADD newrelic/newrelic.yml /usr/local/tomcat/newrelic/newrelic.yml

# Attach the agent at JVM startup
ENV JAVA_OPTS="-javaagent:/usr/local/tomcat/newrelic/newrelic.jar"

EXPOSE 8080
CMD ["catalina.sh", "run"]
```

**`newrelic/newrelic.yml`** (lives next to the Dockerfile)
```yaml
common: &default_settings
  license_key: <%= ENV["NEW_RELIC_LICENSE_KEY"] %>
  agent_enabled: true
  log_level: info

production:
  <<: *default_settings
  app_name: my-java-service-prod

staging:
  <<: *default_settings
  app_name: my-java-service-staging
```

**How it works:** The agent is a `.jar` injected into the JVM via the `-javaagent` flag — it is not a separate running process. One `newrelic.yml` can serve every environment using named sections; switch sections with `NEW_RELIC_ENVIRONMENT=production` or `-Dnewrelic.environment=production`.

**Known failure mode:** Some base-image entrypoint scripts (especially custom ones) ignore `JAVA_OPTS`. If the agent never attaches, confirm your actual startup script reads that variable.

---

### 3.2 Python

**Dockerfile**
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt newrelic

COPY . .

ENV NEW_RELIC_LICENSE_KEY=""
ENV NEW_RELIC_APP_NAME="my-python-service"
ENV NEW_RELIC_LOG=stdout

CMD ["newrelic-admin", "run-program", "gunicorn", "-b", "0.0.0.0:8000", "app:app"]
```

**How it works:** `newrelic-admin run-program` wraps your start command and reads configuration entirely from `NEW_RELIC_*` environment variables — no config file required.

**Optional file-based config instead:** add `ENV NEW_RELIC_CONFIG_FILE=/app/newrelic.ini`, `COPY newrelic.ini .`, generated via:
```bash
newrelic-admin generate-config <license_key> newrelic.ini
```

**Known failure mode:** License key accidentally set as `NRIA_LICENSE_KEY` (infra-agent variable) instead of `NEW_RELIC_LICENSE_KEY`.

---

### 3.3 Node.js

**Dockerfile**
```dockerfile
FROM node:20-slim

WORKDIR /app
COPY package*.json ./
RUN npm install
RUN npm install newrelic

COPY . .

ENV NEW_RELIC_LICENSE_KEY=""
ENV NEW_RELIC_APP_NAME="my-node-service"
ENV NEW_RELIC_NO_CONFIG_FILE=true
ENV NEW_RELIC_DISTRIBUTED_TRACING_ENABLED=true

EXPOSE 3000
CMD ["node", "-r", "newrelic", "server.js"]
```

**How it works:** `-r newrelic` loads the agent before any other module in the process. This is the load mechanism — there's no required config file on current agent versions.

**Known failure mode:** Process managers (PM2, nodemon, custom shell wrappers) often define their own `script`/`args` and silently drop the `-r newrelic` flag. If using PM2, add `node_args: '-r newrelic'` to the ecosystem file instead, or `require('newrelic')` as the literal first line of your entry file.

---

### 3.4 Ruby

**Dockerfile**
```dockerfile
FROM ruby:3.3-slim

WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install

COPY . .

ENV NEW_RELIC_LICENSE_KEY=""
ENV NEW_RELIC_APP_NAME="my-ruby-service"

EXPOSE 4567
CMD ["bundle", "exec", "puma", "-p", "4567"]
```

**`Gemfile`** (add this line)
```ruby
gem 'newrelic_rpm'
```

**`config/newrelic.yml`** (must live at this exact path relative to app root)
```yaml
common: &default_settings
  license_key: <%= ENV["NEW_RELIC_LICENSE_KEY"] %>
  agent_enabled: true

production:
  <<: *default_settings
  app_name: my-ruby-service-prod

development:
  <<: *default_settings
  app_name: my-ruby-service-dev
  monitor_mode: true
```

**How it works:** The gem auto-hooks into the app on Bundler load — no `-r` flag equivalent needed.

**Known failure mode:** `monitor_mode: true` is required in non-production environment blocks (e.g. `development:`), or the agent silently reports nothing in local/dev testing.

---

## 4. Where Environment Variables Actually Get Set

This is the step people get wrong most often — setting a variable in the wrong place means it never reaches the running process.

| Location | Use for | Notes |
|---|---|---|
| `Dockerfile ENV` | Non-secret defaults only (app name) | **Never** the license key — gets baked permanently into the image layer |
| `docker run -e` / `docker-compose.yml` | Local development | Fine for license key here since it isn't baked into the image |
| ECS task definition → `containerDefinitions[].environment` | Production on ECS | The only place ECS reads `NEW_RELIC_*` from |
| Kubernetes Pod spec `env:` / Helm `values.yaml` | Production on EKS | Set per-container, not via the Dockerfile |

**Quick verification command — run on any misbehaving container:**
```bash
docker exec <container> env | grep NEW_RELIC
```
If the variable isn't listed, nothing downstream matters yet — fix this first.

---

## 5. ECS-Specific Setup

### Required task definition environment variables (all languages)

```json
"environment": [
  { "name": "NEW_RELIC_HOST", "value": "collector.newrelic.com" },
  { "name": "NEW_RELIC_APP_NAME", "value": "Fargate Demo (AWS)" },
  { "name": "NEW_RELIC_LICENSE_KEY", "value": "your-license-key" }
]
```

### Infrastructure agent as a sidecar (recommended)

Running the infra agent alongside your APM container correlates application and infrastructure data in New Relic's service maps.

```json
{
  "name": "newrelic-infra",
  "image": "newrelic/nri-ecs:1.11.10",
  "cpu": 256,
  "memoryReservation": 512,
  "essential": true,
  "environment": [
    { "name": "NRIA_IS_FORWARD_ONLY", "value": "true" },
    { "name": "NRIA_LICENSE_KEY", "value": "your-license-key" },
    { "name": "NRIA_VERBOSE", "value": "1" },
    { "name": "NRIA_PASSTHROUGH_ENVIRONMENT", "value": "ECS_CONTAINER_METADATA_URI,ECS_CONTAINER_METADATA_URI_V4,FARGATE" },
    { "name": "FARGATE", "value": "true" }
  ],
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/newrelic-infra/ecs",
      "awslogs-region": "us-east-1",
      "awslogs-stream-prefix": "verbose"
    }
  }
}
```

> Note `taskRoleArn` and `executionRoleArn` must both be set on the task definition for IAM permissions to read ECS metadata.

---

## 6. EKS-Specific Setup

- **Recommended path:** Use the **New Relic Kubernetes APM auto-attach / Agent Operator** rather than baking the agent into each Dockerfile manually. It injects the agent via an init container, decoupling agent upgrades from application image builds — useful with four different language stacks to maintain.
- **Infra layer:** Install once per cluster via the `nri-bundle` Helm chart (runs as a DaemonSet across nodes), separate from per-pod APM injection.

---

## 7. Troubleshooting Checklist

Work through in this order — each step rules out a layer before moving to the next.

1. **Base image check:** `docker run --rm <image> sh -c "cat /etc/os-release; ldd --version 2>&1 | head -1"` — confirm glibc/musl and distro match expectations.
2. **Env var reached the container:** `docker exec <container> env | grep NEW_RELIC` — confirm the variable exists and has the right value (not `NRIA_*` by mistake).
3. **Agent actually loads:**
   - Java: confirm startup script reads `JAVA_OPTS`
   - Node: confirm `-r newrelic` or `require('newrelic')` survives your process manager
   - Python: confirm `newrelic-admin run-program` wraps the real start command
   - Ruby: confirm `monitor_mode: true` is set for non-production environments
4. **Network reachability:** confirm outbound 443 to `collector.newrelic.com` isn't blocked by security groups, NACLs, or mesh sidecars.
5. **Data latency:** allow 2–5 minutes after traffic before checking the APM Summary page — it's not instant.

---

## 8. Quick Reference — Config Mechanism by Language

| Language | Config mechanism | File name | Load method |
|---|---|---|---|
| Java | File-based (env-overridable) | `newrelic.yml` | `-javaagent` JVM flag |
| Python | Env vars (file optional) | `newrelic.ini` (optional) | `newrelic-admin run-program` wrapper |
| Node.js | Env vars only | None required | `-r newrelic` flag or `require('newrelic')` |
| Ruby | File-based (env-overridable) | `config/newrelic.yml` | Auto-hook via Bundler/gem |

---

*This page is a working reference — update the "Last reviewed" date and add any environment-specific deltas discovered during rollout.*
