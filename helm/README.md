# Helm Chart Generator

This is a Go-based command-line tool that generates a complete Helm chart directory structure using inputs from an external YAML configuration file. The generated chart includes core files (like `Chart.yaml` and `values.yaml`) and a set of Kubernetes resource templates (in the `templates` directory such as deployment, service, ingress, and ConfigMap). The tool uses custom template delimiters to properly preserve Helm’s native templating syntax.

- [Helm Chart Generator](#helm-chart-generator)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
- [Usage](#usage)
  - [Create a Configuration File](#create-a-configuration-file)
  - [Run the Script](#run-the-script)
  - [Output](#output)
  - [File Overview](#file-overview)
  - [How It Works](#how-it-works)
  - [Customization and Extensions](#customization-and-extensions)
    - [Additional Resources:](#additional-resources)
    - [Configuration Changes:](#configuration-changes)

## Features

- **Configuration Driven:** Reads all inputs from a YAML file (`config.yaml` by default) so you can separate configuration from code.
- **Resource Generation:** Produces a Helm chart with:
  - `Chart.yaml`
  - `values.yaml`
  - Templates in the `templates` directory:
    - `_helpers.tpl`
    - `deployment.yaml`
    - `service.yaml`
    - `ingress.yaml` (generated only if enabled)
    - `configmap.yaml`
- **Conditional Ingress:** Support to generate an Ingress resource when enabled in the configuration.
- **Overwrite Capability:** Use the `-overwrite` flag to remove a pre-existing chart directory.
- **Verbose Logging:** The `-verbose` flag provides detailed logging throughout the execution.

## Prerequisites

- **Go Installation:**
  [Go](https://golang.org) must be installed on your system. On macOS, you can install it using Homebrew:
  ```bash
  brew install go
  ```

# Usage

## Create a Configuration File

- Create a file named config.yaml in the same directory as `helm_chart_generator.go`
- Below is a sample configuration file:

```
name: myawesome-chart
chart_version: "0.2.0"
app_version: "1.2.3"
description: "Automated Helm Chart"
replica_count: 3
image_repository: busybox
image_tag: "1.35"
image_pull_policy: Always
service_type: NodePort
service_port: 8080
ingress_enabled: true
ingress_host: example.com
ingress_path: "/"
configmap_key: app-config
configmap_value: production
```

## Run the Script

- Use the following command to run the tool.
- The `-config` flag (default config.yaml) tells the tool where to read the configuration from.
- The `-overwrite` flag allows the existing directory to be removed
- The `-verbose` will print detailed logs.
- Execute: `go run helm_chart_generator.go -config config.yaml -overwrite -verbose`

## Output

- On successful execution, the tool prints a confirmation message:

```
  Loaded configuration for chart 'myawesome-chart'
  Helm chart 'myawesome-chart' generated successfully in directory 'myawesome-chart'.
```

- The generated directory has the following structure:

```
  myawesome-chart/
  ├── Chart.yaml
  ├── values.yaml
  └── templates/
  ├── \_helpers.tpl
  ├── deployment.yaml
  ├── service.yaml
  ├── ingress.yaml # Only if ingress_enabled is true
  └── configmap.yaml

```

## File Overview

- Chart.yaml: Contains basic metadata such as name, description, version, and app version.
- values.yaml: Holds default values for replica count, image settings, and service configurations.
- templates/\_helpers.tpl: Provides helper functions for consistent naming of resources.
- templates/deployment.yaml: A Deployment manifest that uses your custom values.
- templates/service.yaml: A Service manifest configured per your input.
- templates/ingress.yaml: (Optional) An Ingress manifest generated if ingress_enabled is set to true.
- templates/configmap.yaml: A ConfigMap manifest that includes the key-value pair from your configuration file.

## How It Works

- Configuration Loading:
  The script reads the YAML configuration file and unmarshals it into a ChartData struct. Required fields (e.g., chart name) are validated.
- Directory Preparation:
  It creates the chart directory (named after the name field in the config). With the -overwrite flag, an existing directory will be removed before generating new files.
- Template Processing:
  The tool processes pre-defined templates using Go's text/template package with custom delimiters (<< and >>). This prevents conflicts with Helm’s native templating (which uses {{ and }}). If the template contains a **CHART_NAME** placeholder, it is replaced with the actual chart name.
- Resource Generation:
  In addition to core chart files, the tool conditionally generates extra Kubernetes resources (Ingress and ConfigMap) based on the configuration.
- Logging:
  When the -verbose flag is enabled, the tool prints detailed log messages about each step—making it easier to trace the processing and troubleshoot if needed.

## Customization and Extensions

### Additional Resources:

- The code is modular, making it straightforward to add new resource templates or configuration options.
- Template Edits:
  You can modify any of the template files defined within the script to better suit your deployment needs.

### Configuration Changes:

Changes to the configuration file are immediately reflected on subsequent runs without modifying the code.
LicenseThis tool is provided under the MIT License. See the LICENSE file for details.
