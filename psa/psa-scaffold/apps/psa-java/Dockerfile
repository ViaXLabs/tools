# APP: apps/psa-java/Dockerfile
# Built and pushed by .harness/pipelines/psa-java-ci.yaml -- to Nexus
# (primary) and ECR (backup). Neither registry destination is baked in
# here; that's all connector/repo config in the CI pipeline, not this file.
#
# Multi-stage build: compile with the full JDK, run on a slim JRE.
FROM gradle:8-jdk21 AS build
WORKDIR /app
COPY . .
RUN gradle installDist --no-daemon

FROM eclipse-temurin:21-jre
WORKDIR /app

# installDist produces a start script that already reads $JAVA_OPTS at
# runtime, so we don't have to hardcode the New Relic -javaagent flag here.
# It gets set as an env var by Terraform (see modules/ecs-service and
# modules/eks-workload) so the same image works unmodified in either target.
COPY --from=build /app/build/install/psa-java ./

# Bake the New Relic Java agent into the image. Swap this for your org's
# internal mirror if you don't want to pull from New Relic's CDN at build time.
ADD https://download.newrelic.com/newrelic/java-agent/newrelic-agent/current/newrelic-java.zip /tmp/newrelic.zip
RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip \
    && unzip /tmp/newrelic.zip -d /app \
    && rm /tmp/newrelic.zip \
    && apt-get purge -y unzip \
    && rm -rf /var/lib/apt/lists/*

COPY newrelic.yml /app/newrelic/newrelic.yml

ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app/bin/psa-java"]
