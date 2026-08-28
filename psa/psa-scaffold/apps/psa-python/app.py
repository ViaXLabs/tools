# APP: apps/psa-python/app.py
# Stdlib only, deliberately -- matches psa-java's "no framework" style.
# PORT env var is what both modules/ecs-service and modules/eks-workload
# assume the app listens on (default 8080, matches Dockerfile's EXPOSE
# and the Terraform modules' container_port default). /health is what
# .harness/templates/deploy-verify.yaml's HEALTH_URL check hits.

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"ok\n"
        else:
            body = b"Hello from the PSA Python app\n"

        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PSA Python app listening on port {PORT}")
    server.serve_forever()
