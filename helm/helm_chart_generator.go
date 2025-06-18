// helm_chart_generator.go
//
// This tool generates an umbrella Helm chart using one single unified template
// based on settings from an external YAML configuration file. All file definitions
// (Chart.yaml, values.yaml, Kubernetes manifests in the `templates/` directory, and an
// optional library chart) are contained in a single source block. The tool splits the
// unified template using marker lines (--- relative/path/to/file ---) and then renders each
// file using Go's templating engine with custom delimiters.
//
// A new option, -dependencies_enabled, is added to control whether a "dependencies"
// section is generated in Chart.yaml.
//
// Usage Example:
//   go run helm_chart_generator.go -config config.yaml -overwrite -verbose -limit full
//
// Sample config.yaml:
//   name: myawesome-chart
//   chart_version: "0.2.0"
//   app_version: "1.2.3"
//   description: "Automated Umbrella Helm Chart"
//   replica_count: 3
//   image_repository: busybox
//   image_tag: "1.35"
//   image_pull_policy: Always
//   service_type: NodePort
//   service_port: 8080
//   ingress_enabled: true
//   ingress_host: example.com
//   ingress_path: "/"
//   configmap_key: app-config
//   configmap_value: production
//   dependencies_enabled: true
//   subcharts:
//     - name: subchart1
//       version: "0.1.0"
//       repository: "https://example.com/charts"
//     - name: subchart2
//       version: "0.2.0"
//       repository: "https://charts.example.org"
//   library_enabled: true
//   library_name: common-templates
//   library_version: "0.1.0"
//   library_repository: "file://charts/library"

package main

import (
	"bytes"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"strings"
	"text/template"

	"gopkg.in/yaml.v2"
)

// Subchart defines a dependency for the umbrella chart.
type Subchart struct {
	Name       string `yaml:"name"`
	Version    string `yaml:"version"`
	Repository string `yaml:"repository"`
}

// ChartData holds all settings read from the YAML configuration.
type ChartData struct {
	// Core chart settings.
	Name                string     `yaml:"name"`
	ChartVersion        string     `yaml:"chart_version"`
	AppVersion          string     `yaml:"app_version"`
	Description         string     `yaml:"description"`
	ReplicaCount        int        `yaml:"replica_count"`
	ImageRepository     string     `yaml:"image_repository"`
	ImageTag            string     `yaml:"image_tag"`
	ImagePullPolicy     string     `yaml:"image_pull_policy"`
	ServiceType         string     `yaml:"service_type"`
	ServicePort         int        `yaml:"service_port"`
	IngressEnabled      bool       `yaml:"ingress_enabled"`
	IngressHost         string     `yaml:"ingress_host"`
	IngressPath         string     `yaml:"ingress_path"`
	ConfigMapKey        string     `yaml:"configmap_key"`
	ConfigMapValue      string     `yaml:"configmap_value"`
	DependenciesEnabled bool       `yaml:"dependencies_enabled"`
	Subcharts           []Subchart `yaml:"subcharts"`

	// Library chart settings.
	LibraryEnabled    bool   `yaml:"library_enabled"`
	LibraryName       string `yaml:"library_name"`
	LibraryVersion    string `yaml:"library_version"`
	LibraryRepository string `yaml:"library_repository"`
}

// Global flags.
var (
	verbose     bool
	overwrite   bool
	limitMode   string // "full" (default) or "core"
)

// logVerbose prints log messages when verbose mode is enabled.
func logVerbose(format string, args ...interface{}) {
	if verbose {
		log.Printf(format, args...)
	}
}

// loadConfig reads the YAML configuration file and unmarshals it into a ChartData struct.
func loadConfig(configPath string) ChartData {
	dataBytes, err := ioutil.ReadFile(configPath)
	if err != nil {
		log.Fatalf("Error reading configuration file '%s': %v", configPath, err)
	}
	var config ChartData
	if err = yaml.Unmarshal(dataBytes, &config); err != nil {
		log.Fatalf("Error unmarshalling YAML: %v", err)
	}
	if config.Name == "" {
		log.Fatalf("Configuration error: 'name' must be specified.")
	}
	logVerbose("Configuration loaded for chart: %s", config.Name)
	return config
}

// prepareDirectory creates the output directory (named after the chart).
// If the directory exists and the -overwrite flag is set, it is removed.
func prepareDirectory(chartName string) string {
	baseDir := chartName
	if _, err := os.Stat(baseDir); err == nil {
		if overwrite {
			logVerbose("Directory '%s' exists; removing due to -overwrite flag.", baseDir)
			if err := os.RemoveAll(baseDir); err != nil {
				log.Fatalf("Failed to remove directory '%s': %v", baseDir, err)
			}
		} else {
			log.Fatalf("Directory '%s' already exists. Use -overwrite to remove it.", baseDir)
		}
	}
	if err := os.MkdirAll(baseDir, 0755); err != nil {
		log.Fatalf("Error creating directory '%s': %v", baseDir, err)
	}
	logVerbose("Created base directory: %s", baseDir)
	return baseDir
}

// parseUnifiedTemplate splits the unified template content into a map,
// where keys are relative file paths and values are the template content.
func parseUnifiedTemplate(content string) map[string]string {
	result := make(map[string]string)
	lines := strings.Split(content, "\n")
	var currentKey string
	var currentLines []string
	markerPrefix := "---"
	for _, line := range lines {
		trim := strings.TrimSpace(line)
		if strings.HasPrefix(trim, markerPrefix) && strings.HasSuffix(trim, markerPrefix) {
			if currentKey != "" && len(currentLines) > 0 {
				result[currentKey] = strings.Join(currentLines, "\n")
			}
			trimmed := strings.TrimPrefix(trim, markerPrefix)
			trimmed = strings.TrimSuffix(trimmed, markerPrefix)
			currentKey = strings.TrimSpace(trimmed)
			currentLines = []string{}
		} else if currentKey != "" {
			currentLines = append(currentLines, line)
		}
	}
	if currentKey != "" && len(currentLines) > 0 {
		result[currentKey] = strings.Join(currentLines, "\n")
	}
	return result
}

// processUnifiedTemplates processes and writes out each file from the unified template.
// If limitMode is "core", only essential (core) templates are generated.
func processUnifiedTemplates(data ChartData, baseDir string) {
	templatesMap := parseUnifiedTemplate(allTemplates)
	for relPath, tmplContent := range templatesMap {
		// In "core" mode, skip non-core files.
		if limitMode == "core" {
			if strings.HasPrefix(relPath, "charts/") ||
				relPath == "templates/ingress.yaml" ||
				relPath == "templates/configmap.yaml" {
				logVerbose("Skipping template due to limited core output: %s", relPath)
				continue
			}
		}
		// Always skip library chart files if LibraryEnabled is false.
		if strings.HasPrefix(relPath, "charts/") && !data.LibraryEnabled {
			logVerbose("Skipping library template file: %s", relPath)
			continue
		}
		// Also skip ingress file if ingress is disabled.
		if relPath == "templates/ingress.yaml" && !data.IngressEnabled {
			logVerbose("Skipping ingress template (ingress_enabled is false).")
			continue
		}
		requiresReplacement := strings.Contains(tmplContent, "__CHART_NAME__")
		outPath := filepath.Join(baseDir, relPath)
		if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
			log.Fatalf("Error creating directory for file '%s': %v", outPath, err)
		}
		logVerbose("Generating file: %s", outPath)
		generateFile(outPath, tmplContent, data, requiresReplacement)
	}
}

// generateFile renders a single template string using custom delimiters and writes it to a file.
func generateFile(path, tmplStr string, data ChartData, replaceChartName bool) {
	tmpl, err := template.New("file").
		Funcs(template.FuncMap{
			"or": func(a, b bool) bool { return a || b },
			"gt": func(a, b int) bool { return a > b },
		}).
		Delims("<<", ">>").
		Parse(tmplStr)
	if err != nil {
		log.Fatalf("Error parsing template for '%s': %v", path, err)
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		log.Fatalf("Error executing template for '%s': %v", path, err)
	}
	outContent := buf.String()
	if replaceChartName {
		outContent = strings.ReplaceAll(outContent, "__CHART_NAME__", data.Name)
	}
	if err := os.WriteFile(path, []byte(outContent), 0644); err != nil {
		log.Fatalf("Error writing file '%s': %v", path, err)
	}
	logVerbose("File successfully written: %s", path)
}

func main() {
	// Define command-line flags.
	configFile := flag.String("config", "config.yaml", "Path to YAML configuration file")
	flag.BoolVar(&overwrite, "overwrite", false, "Overwrite existing chart directory if it exists")
	flag.BoolVar(&verbose, "verbose", false, "Enable verbose logging")
	flag.StringVar(&limitMode, "limit", "full", "Output mode: 'full' for all files or 'core' for essential files only")
	flag.Parse()

	// Load configuration.
	configData := loadConfig(*configFile)
	// Prepare the output directory.
	baseDir := prepareDirectory(configData.Name)
	// Process the unified template and generate files.
	processUnifiedTemplates(configData, baseDir)

	fmt.Printf("Helm umbrella chart '%s' generated successfully in directory '%s'.\n", configData.Name, baseDir)
}

//
// --- Unified Template ---
// All file templates are embedded below in one single block.
// Marker lines of the format: --- relative/path/to/file --- separate each file's content.
const allTemplates = `--- Chart.yaml ---
apiVersion: v2
name: <<.Name>>
description: <<.Description>>
type: application
version: <<.ChartVersion>>
appVersion: "<<.AppVersion>>"
<<- if .DependenciesEnabled >>
dependencies:
<<- if .LibraryEnabled >>
- name: <<.LibraryName>>
  version: "<<.LibraryVersion>>"
  repository: "<<.LibraryRepository>>"
<<- end >>
<<- range .Subcharts >>
- name: <<.Name>>
  version: "<<.Version>>"
  repository: "<<.Repository>>"
<<- end >>
<<- end >>
--- values.yaml ---
replicaCount: <<.ReplicaCount>>

image:
  repository: <<.ImageRepository>>
  pullPolicy: <<.ImagePullPolicy>>
  tag: "<<.ImageTag>>"

service:
  type: <<.ServiceType>>
  port: <<.ServicePort>>

# Optional overrides
nameOverride: ""
fullnameOverride: ""
--- templates/_helpers.tpl ---
{{/*
Return the base chart name.
*/}}
{{- define "__CHART_NAME__.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return a fully-qualified name.
*/}}
{{- define "__CHART_NAME__.fullname" -}}
{{- if .Values.fullnameOverride -}}
  {{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
  {{- $name := default .Chart.Name .Values.nameOverride -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
--- templates/deployment.yaml ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
spec:
  replicas: <<ReplicaCount>>
  selector:
    matchLabels:
      app: {{ include "__CHART_NAME__.name" . }}
  template:
    metadata:
      labels:
        app: {{ include "__CHART_NAME__.name" . }}
    spec:
      containers:
      - name: {{ include "__CHART_NAME__.name" . }}
        image: "<<ImageRepository>>:<<ImageTag>>"
        imagePullPolicy: <<ImagePullPolicy>>
        ports:
        - containerPort: <<ServicePort>>
--- templates/service.yaml ---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
spec:
  type: <<.ServiceType>>
  ports:
  - port: <<.ServicePort>>
    targetPort: <<.ServicePort>>
    protocol: TCP
    name: http
  selector:
    app: {{ include "__CHART_NAME__.name" . }}
--- templates/ingress.yaml ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
spec:
  rules:
  - host: <<.IngressHost>>
    http:
      paths:
      - path: <<.IngressPath>>
        pathType: ImplementationSpecific
        backend:
          service:
            name: {{ include "__CHART_NAME__.fullname" . }}
            port:
              number: <<.ServicePort>>
--- templates/configmap.yaml ---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}-config
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
data:
  <<.ConfigMapKey>>: "<<.ConfigMapValue>>"
--- charts/library/Chart.yaml ---
apiVersion: v2
name: <<.LibraryName>>
description: "Library chart containing common helper templates."
type: library
version: <<.LibraryVersion>>
--- charts/library/values.yaml ---
# Library chart values (customize if needed).
--- charts/library/templates/_helpers.tpl ---
{{/*
Common helper functions for shared usage.
Part of the library chart.
*/}}
{{- define "common.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "common.fullname" -}}
{{- if .Values.fullnameOverride -}}
  {{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
  {{- $name := default .Chart.Name .Values.nameOverride -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
`
