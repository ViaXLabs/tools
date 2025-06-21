# Helm Chart Generator

This Go-based command-line tool generates an umbrella Helm chart from a single unified template and a YAML configuration file. All chart file definitions (such as `Chart.yaml`, `values.yaml`, and templates for Kubernetes manifests in the `templates/` directory, plus an optional library chart) are stored in one source block. The tool then splits this block into individual files using marker lines.

- [Helm Chart Generator](#helm-chart-generator)
  - [Overview](#overview)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
  - [Usage](#usage)
  - [Run the Generator](#run-the-generator)
- [Umbrella Helm Chart Generator](#umbrella-helm-chart-generator)
  - [Features](#features-1)
  - [Prerequisites](#prerequisites-1)
  - [LicenseThis tool is provided under the MIT License. See the LICENSE file for details.Enjoy using the Umbrella Helm Chart Generator to streamline your Helm deployments!](#licensethis-tool-is-provided-under-the-mit-license-see-the-license-file-for-detailsenjoy-using-the-umbrella-helm-chart-generator-to-streamline-your-helm-deployments)

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

How It Works
Configuration Loading: The tool reads config.yaml into a structured ChartData object. The new dependencies_enabled flag controls whether the dependencies section is included in Chart.yaml.

Directory Preparation: An output directory is created (or overwritten if -overwrite is set).

Unified Template Splitting: A single unified template (stored in the tool) containing all file definitions is split into individual files based on marker lines of the format:

--- relative/path/to/file ---
Conditional Rendering: The tool uses the -limit flag to determine whether to generate all files ("full") or only core files ("core"). Additionally, it conditionally skips files (e.g., Ingress, ConfigMap, library chart files) based on the configuration settings.

File Rendering and Writing: Each file template is rendered by substituting in values from the configuration (using custom delimiters << and >>), and then written to the specified location.

Final Outcome: The umbrella Helm chart is generated and is ready for use with Helm for packaging or deployment.

````


# Umbrella Helm Chart Generator

This Go-based command-line tool generates an umbrella Helm chart from a single unified template and a YAML configuration file. All chart file definitions (such as `Chart.yaml`, `values.yaml`, and templates for Kubernetes manifests in the `templates/` directory, plus an optional library chart) are stored in one source block. The tool then splits this block into individual files using marker lines.

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


Explanation Recap
- Configuration Loading:
The tool loads your settings from the YAML configuration file (which now includes a dependencies_enabled flag) into a ChartData struct.
- Directory Preparation:
It creates an output directory (named after your chart) and, if necessary, overwrites it.
- Unified Template Splitting:
The entire block of file templates is stored in one string constant (allTemplates). The function parseUnifiedTemplate() splits this block into individual file templates using marker lines.

- Conditional File Generation:
Files are conditionally rendered based on several options:
- If -limit core is provided, only the essential (core) files (Chart.yaml, values.yaml, deployment.yaml, service.yaml) are generated.
- The dependencies section in Chart.yaml is only output if dependencies_enabled is true.
- Ingress and ConfigMap templates are skipped if ingress_enabled is false.
- Library chart files are generated only if library_enabled is true (and are also skipped in core mode).
- Template Rendering:
Each template is rendered using Go’s templating engine with custom delimiters (<< and >>). Any occurrence of the placeholder __CHART_NAME__ is replaced with the actual chart name.
- File Writing and Logging:
The rendered templates are written to their respective files. Verbose logging (enabled with -verbose) outputs detailed steps.
- Final Outcome:
The umbrella Helm chart is generated in the output directory with either a full or limited set of files according to the -limit flag. You can then use this chart with Helm.


- YAML Package:
Install the YAML package:
go get gopkg.in/yaml.v2


Usage
- Create a Configuration File
- Create a file named config.yaml in the same directory as main.go. For example:
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

- Run the Generator
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

- In core mode, only essential files (Chart.yaml, values.yaml, deployment.yaml, and service.yaml) are generated.
How It Works- Configuration Loading:
The tool reads config.yaml into a structured ChartData object. The new dependencies_enabled flag controls whether the dependencies section is included in Chart.yaml.
- Directory Preparation:
An output directory is created (or overwritten if -overwrite is set).
- Unified Template Splitting:
A single unified template (stored in the tool) containing all file definitions is split into individual files based on marker lines of the format:
`--- relative/path/to/file ---`


- Conditional Rendering:
The tool uses the -limit flag to determine whether to generate all files ("full") or only core files ("core"). Additionally, it conditionally skips files (e.g., Ingress, ConfigMap, library chart files) based on the configuration settings.
- File Rendering and Writing:
Each file template is rendered by substituting in values from the configuration (using custom delimiters << and >>), and then written to the specified location.
- Final Outcome:
The umbrella Helm chart is generated and is ready for use with Helm for packaging or deployment.
LicenseThis tool is provided under the MIT License. See the LICENSE file for details.Enjoy using the Umbrella Helm Chart Generator to streamline your Helm deployments!
---

This completes our testing and explanation of the updated script. In summary, by adding the new `dependencies_enabled` option and the `-limit` flag, you now have more control over which output files are generated. You can run the tool in full mode to generate all files or in core mode to limit outputs to essential files—all while leveraging a single unified template.

`--- relative/path/to/file ---`













````
