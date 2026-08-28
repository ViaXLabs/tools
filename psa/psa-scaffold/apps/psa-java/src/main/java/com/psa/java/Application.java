// APP: apps/psa-java/src/main/java/com/psa/java/Application.java
// Deliberately dependency-free (com.sun.net.httpserver is part of the
// JDK itself, module jdk.httpserver) -- no framework to keep this a
// genuine "hello world" for showcase purposes. PORT env var is what both
// modules/ecs-service and modules/eks-workload assume the app listens on
// (default 8080, matches both Dockerfiles' EXPOSE and the Terraform
// modules' container_port default). /health is what
// .harness/templates/deploy-verify.yaml's HEALTH_URL check hits.

package com.psa.java;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;

public class Application {
    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        server.createContext("/", exchange -> {
            String response = "Hello from the PSA Java app\n";
            exchange.sendResponseHeaders(200, response.length());
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response.getBytes());
            }
        });

        server.createContext("/health", exchange -> {
            String response = "ok\n";
            exchange.sendResponseHeaders(200, response.length());
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response.getBytes());
            }
        });

        server.setExecutor(null);
        server.start();
        System.out.println("PSA Java app listening on port " + port);
    }
}
