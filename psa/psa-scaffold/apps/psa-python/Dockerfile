# APP: apps/psa-python/Dockerfile
# Built and pushed by .harness/pipelines/psa-python-ci.yaml -- to Nexus
# (primary) and ECR (backup). Neither registry destination is baked in
# here; that's all connector/repo config in the CI pipeline, not this file.
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["python", "app.py"]
