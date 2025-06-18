# Helm Chart Generator

This Go-based command-line tool generates an umbrella Helm chart from a single unified template and a YAML configuration file. All chart file definitions (such as `Chart.yaml`, `values.yaml`, and templates for Kubernetes manifests in the `templates/` directory, plus an optional library chart) are stored in one source block. The tool then splits this block into individual files using marker lines.

- [Helm Chart Generator](#helm-chart-generator)
  - [Overview](#overview)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
  - [Usage](#usage)
  - [Run the Generator](#run-the-generator)
- [Usage](#usage-1)
  - [Create a Configuration File](#create-a-configuration-file)
  - [Run the Script](#run-the-script)
  - [Output](#output)
  - [File Overview](#file-overview)
  - [How It Works](#how-it-works)
  - [Customization and Extensions](#customization-and-extensions)
    - [Additional Resources:](#additional-resources)
    - [Configuration Changes:](#configuration-changes)

## Overview

- Configuration Loading:
  The tool loads your settings from the YAML configuration file (which now includes a dependencies_enabled flag) into a ChartData struct.
- Directory Preparation:
  It creates an output directory (named after your chart) and, if necessary, overwrites it.
- Unified Template Splitting:
  The entire block of file templates is stored in one string constant (allTemplates). The function parseUnifiedTemplate() splits this block into individual file templates using marker lines.
- Conditional File Generation
- Files are conditionally rendered based on several options:
- If -limit core is provided, only the essential (core) files (Chart.yaml, values.yaml, deployment.yaml, service.yaml) are generated.
- The dependencies section in Chart.yaml is only output if dependencies_enabled is true.
- Ingress and ConfigMap templates are skipped if ingress_enabled is false.
- Library chart files are generated only if library_enabled is true (and are also skipped in core mode).

- Template Rendering:
  Each template is rendered using Go’s templating engine with custom delimiters (<< and >>). Any occurrence of the placeholder **CHART_NAME** is replaced with the actual chart name.
- File Writing and Logging:
  The rendered templates are written to their respective files. Verbose logging (enabled with -verbose) outputs detailed steps.
- Final Outcome:
  The umbrella Helm chart is generated in the output directory with either a full or limited set of files according to the -limit flag. You can then use this chart with Helm.

## Features

- **Unified Template:** All file templates are maintained in one single source within the tool.
- **Configuration Driven:** Provide settings via a YAML file (default: `config.yaml`).
- **Conditional Generation:** The tool conditionally renders files based on your configuration:
  - The dependencies section in `Chart.yaml` appears only if `dependencies_enabled` is true.
  - Files such as Ingress and ConfigMap are generated only if enabled.
- **Limited Output Mode:** Use the `-limit core` flag to generate only the essential files (Chart.yaml, values.yaml, deployment.yaml, and service.yaml).
- **Overwrite Option:** Use the `-overwrite` flag to remove any existing output directory.
- **Verbose Logging:** Use the `-verbose` flag to output detailed processing logs.

## Prerequisites

- **Go:**
  Install Go on your system. For example, on macOS:

  ```bash
  brew install go
  ```

  - YAML Package:
    Install the YAML package:
    `go get gopkg.in/yaml.v2`

## Usage

- Create a Configuration File
- Create a file named config.yaml in the same directory as main.go.
- For example:

```
name: myawesome-chart
chart_version: "0.2.0"
app_version: "1.2.3"
description: "Automated Umbrella Helm Chart"
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
dependencies_enabled: true
subcharts:
  - name: subchart1
    version: "0.1.0"
    repository: "https://example.com/charts"
  - name: subchart2
    version: "0.2.0"
    repository: "https://charts.example.org"
library_enabled: true
library_name: common-templates
library_version: "0.1.0"
library_repository: "file://charts/library"
```

## Run the Generator

- To generate the full umbrella chart:
  go run main.go -config config.yaml -overwrite -verbose -limit full
- To generate only the core files (limited output mode):
  go run main.go -config config.yaml -overwrite -verbose -limit core

- Flags:
- -config: Path to your YAML configuration file.
- -overwrite: Overwrite the output directory if it exists.
- -verbose: Enable detailed logging.
- -limit: Set to "full" (default) for all files or "core" for only essential files.
- Output
- The tool creates an output directory (named based on the name field in config.yaml). For full output mode, the structure may look like:

```
myawesome-chart/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── configmap.yaml
└── charts/
    └── library/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
            └── _helpers.tpl
```

- Note: In core mode, only essential files (Chart.yaml, values.yaml, deployment.yaml, and service.yaml) are generated.

How It Works

- Template Rendering:
  Each template is rendered using Go’s templating engine with custom delimiters (<< and >>). Any occurrence of the placeholder **CHART_NAME** is replaced with the actual chart name.
- File Writing and Logging:
  The rendered templates are written to their respective files. Verbose logging (enabled with -verbose) outputs detailed steps.
- Final Outcome:
  The umbrella Helm chart is generated in the output directory with either a full or limited set of files according to the -limit flag. You can then use this chart with Helm.

`````
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
2024/06/18 14:13:01 Configuration loaded for chart: myawesome-chart
2024/06/18 14:13:01 Created directory: myawesome-chart
2024/06/18 14:13:01 Generating file: myawesome-chart/Chart.yaml
2024/06/18 14:13:01 File written: myawesome-chart/Chart.yaml
...
2024/06/18 14:13:01 Generating file: myawesome-chart/charts/library/templates/_helpers.tpl
2024/06/18 14:13:01 File written: myawesome-chart/charts/library/templates/_helpers.tpl
Helm umbrella chart 'myawesome-chart' generated successfully in directory 'myawesome-chart'.
```

- The generated directory has the following structure:

```
  myawesome-chart/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml      (present because ingress_enabled=true)
│   └── configmap.yaml
└── charts/
    └── library/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
            └── _helpers.tpl

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

````
