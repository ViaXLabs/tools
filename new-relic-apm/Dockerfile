# ---- Stage 1: compile the app and fetch the New Relic Java agent ----
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app

COPY HelloWorld.java .
RUN javac HelloWorld.java

# Grab the latest New Relic Java agent bundle (newrelic.jar, newrelic.yml, newrelic-api.jar).
# This is New Relic's own "always current" download URL for the Java agent.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL -o newrelic-java.zip \
       https://download.newrelic.com/newrelic/java-agent/newrelic-agent/current/newrelic-java.zip \
    && unzip -q newrelic-java.zip \
    && rm newrelic-java.zip

# ---- Stage 2: slim runtime image ----
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY --from=build /app/HelloWorld.class .
COPY --from=build /app/newrelic ./newrelic

# Required New Relic config. Set the REAL license key at container run time
# (docker run -e / compose env / secrets manager) -- never bake it into the image.
ENV NEW_RELIC_LICENSE_KEY="" \
    NEW_RELIC_APP_NAME="hello-java-sample" \
    NEW_RELIC_LOG_FILE_NAME="STDOUT" \
    NEW_RELIC_LABELS="Environment:dev;Team:platform;Service:hello-java-sample"

# The -javaagent flag is what actually attaches the agent to the JVM.
ENTRYPOINT ["java", "-javaagent:/app/newrelic/newrelic.jar", "HelloWorld"]
