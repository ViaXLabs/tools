// main.go
//
// This enhanced script generates a Helm chart directory structure
// based on inputs provided in an external YAML configuration file.
// It supports additional improvements such as an overwrite option,
// verbose logging, and improved error handling.
//
// --- How to Install Go (on macOS using Homebrew) ---
//   brew install go
//
// --- How to Get the YAML Package ---
//   go get gopkg.in/yaml.v2
//
// --- How to Run This Script ---
// Create a configuration file (e.g., config.yaml) with your inputs (sample below).
// Then run the script by specifying the config file path (default is "config.yaml").
// You can use the -overwrite flag to remove an existing directory and -verbose for detailed logging:
//
//   go run main.go -config config.yaml -overwrite -verbose
//
// Sample config.yaml:
//
//   name: myawesome-chart
//   chart_version: "0.2.0"
//   app_version: "1.2.3"
//   description: "Automated Helm Chart"
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
//
// After running, a folder named after the chart (e.g., "myawesome-chart") is generated with all files.

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

// ChartData holds the customizable values used to generate the Helm chart.
// YAML tags map the configuration file keys to these fields.
type ChartData struct {
	// Core chart settings.
	Name            string `yaml:"name"`
	ChartVersion    string `yaml:"chart_version"`
	AppVersion      string `yaml:"app_version"`
	Description     string `yaml:"description"`
	ReplicaCount    int    `yaml:"replica_count"`
	ImageRepository string `yaml:"image_repository"`
	ImageTag        string `yaml:"image_tag"`
	ImagePullPolicy string `yaml:"image_pull_policy"`
	ServiceType     string `yaml:"service_type"`
	ServicePort     int    `yaml:"service_port"`

	// Additional resource settings.
	IngressEnabled bool   `yaml:"ingress_enabled"`
	IngressHost    string `yaml:"ingress_host"`
	IngressPath    string `yaml:"ingress_path"`
	ConfigMapKey   string `yaml:"configmap_key"`
	ConfigMapValue string `yaml:"configmap_value"`
}

// Global flags.
var (
	verbose   bool
	overwrite bool
)

// logVerbose prints log messages if verbose mode is enabled.
func logVerbose(format string, args ...interface{}) {
	if verbose {
		log.Printf(format, args...)
	}
}

// loadConfig reads and unmarshals the YAML configuration file into a ChartData struct.
func loadConfig(configPath string) ChartData {
	dataBytes, err := ioutil.ReadFile(configPath)
	if err != nil {
		log.Fatalf("Error reading config file '%s': %v", configPath, err)
	}

	var config ChartData
	err = yaml.Unmarshal(dataBytes, &config)
	if err != nil {
		log.Fatalf("Error unmarshalling YAML: %v", err)
	}

	// Basic validation: Check for required fields.
	if config.Name == "" {
		log.Fatalf("The configuration file must specify a 'name' for the chart.")
	}

	logVerbose("Loaded configuration for chart '%s'", config.Name)
	return config
}

// prepareDirectory creates the base chart directory and templates subdirectory.
// If the base directory exists, it is removed if the overwrite flag is set.
func prepareDirectory(chartName string) (baseDir, templatesDir string) {
	baseDir = chartName
	if _, err := os.Stat(baseDir); err == nil {
		if overwrite {
			logVerbose("Directory '%s' already exists. Removing as -overwrite flag is set.", baseDir)
			if err := os.RemoveAll(baseDir); err != nil {
				log.Fatalf("Failed to remove existing directory '%s': %v", baseDir, err)
			}
		} else {
			log.Fatalf("Directory '%s' already exists. Use -overwrite to remove it.", baseDir)
		}
	}

	templatesDir = filepath.Join(baseDir, "templates")
	if err := os.MkdirAll(templatesDir, 0755); err != nil {
		log.Fatalf("Error creating directories: %v", err)
	}
	logVerbose("Created directory structure: %s and %s", baseDir, templatesDir)
	return baseDir, templatesDir
}

// generateChartFiles processes template files and writes them to the correct location.
func generateChartFiles(data ChartData, baseDir, templatesDir string) {
	// Define the list of files to be generated.
	filesToGenerate := []struct {
		path             string
		templateContent  string
		replaceChartName bool
	}{
		{filepath.Join(baseDir, "Chart.yaml"), chartTemplate, false},
		{filepath.Join(baseDir, "values.yaml"), valuesTemplate, false},
		{filepath.Join(templatesDir, "_helpers.tpl"), helpersTpl, true},
		{filepath.Join(templatesDir, "deployment.yaml"), deploymentTemplate, true},
		{filepath.Join(templatesDir, "service.yaml"), serviceTemplate, true},
	}

	// Conditionally add Ingress if enabled.
	if data.IngressEnabled {
		filesToGenerate = append(filesToGenerate, struct {
			path             string
			templateContent  string
			replaceChartName bool
		}{
			filepath.Join(templatesDir, "ingress.yaml"), ingressTemplate, true,
		})
	}

	// Always generate the ConfigMap.
	filesToGenerate = append(filesToGenerate, struct {
		path             string
		templateContent  string
		replaceChartName bool
	}{
		filepath.Join(templatesDir, "configmap.yaml"), configMapTemplate, true,
	})

	// Process and write each file.
	for _, file := range filesToGenerate {
		logVerbose("Generating file: %s", file.path)
		generateFile(file.path, file.templateContent, data, file.replaceChartName)
	}
}

// generateFile processes the given template (with custom delimiters << and >>) using the ChartData,
// then writes the output to the specified path. It also replaces the __CHART_NAME__ placeholder if needed.
func generateFile(path, tmplStr string, data ChartData, replaceChartName bool) {
	tmpl, err := template.New("file").Delims("<<", ">>").Parse(tmplStr)
	if err != nil {
		log.Fatalf("Error parsing template for %s: %v", path, err)
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		log.Fatalf("Error executing template for %s: %v", path, err)
	}
	outContent := buf.String()
	if replaceChartName {
		outContent = strings.ReplaceAll(outContent, "__CHART_NAME__", data.Name)
	}
	if err := os.WriteFile(path, []byte(outContent), 0644); err != nil {
		log.Fatalf("Error writing file %s: %v", path, err)
	}
	logVerbose("Successfully wrote file: %s", path)
}

func main() {
	// Define flags.
	configFile := flag.String("config", "config.yaml", "Path to configuration file containing chart inputs")
	flag.BoolVar(&overwrite, "overwrite", false, "Overwrite existing chart directory if it exists")
	flag.BoolVar(&verbose, "verbose", false, "Enable verbose logging")
	flag.Parse()

	// Load configuration.
	chartConfig := loadConfig(*configFile)

	// Prepare directory structure.
	baseDir, templatesDir := prepareDirectory(chartConfig.Name)

	// Generate all Helm chart files.
	generateChartFiles(chartConfig, baseDir, templatesDir)

	fmt.Printf("Helm chart '%s' generated successfully in directory '%s'.\n", chartConfig.Name, baseDir)
}

//
// --- Template Definitions ---
//
// We use custom delimiters << and >> for substitutions to avoid interference with Helm's native syntax ({{ ... }}).
// The __CHART_NAME__ placeholder is replaced with the chart name during file generation.
//

const chartTemplate = `apiVersion: v2
name: <<.Name>>
description: <<.Description>>
type: application
version: <<.ChartVersion>>
appVersion: "<<.AppVersion>>"
`

const valuesTemplate = `replicaCount: <<.ReplicaCount>>

image:
  repository: <<.ImageRepository>>
  pullPolicy: <<.ImagePullPolicy>>
  tag: "<<.ImageTag>>"

service:
  type: <<.ServiceType>>
  port: <<.ServicePort>>

# Optional overrides to customize naming
nameOverride: ""
fullnameOverride: ""
`

const helpersTpl = `{{/*
Return the chart name.
*/}}
{{- define "__CHART_NAME__.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully-qualified application name.
*/}}
{{- define "__CHART_NAME__.fullname" -}}
{{- if .Values.fullnameOverride -}}
  {{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
  {{- $name := default .Chart.Name .Values.nameOverride -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
`

const deploymentTemplate = `apiVersion: apps/v1
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
`

const serviceTemplate = `apiVersion: v1
kind: Service
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
spec:
  type: <<ServiceType>>
  ports:
  - port: <<ServicePort>>
    targetPort: <<ServicePort>>
    protocol: TCP
    name: http
  selector:
    app: {{ include "__CHART_NAME__.name" . }}
`

const ingressTemplate = `apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
spec:
  rules:
  - host: <<IngressHost>>
    http:
      paths:
      - path: <<IngressPath>>
        pathType: ImplementationSpecific
        backend:
          service:
            name: {{ include "__CHART_NAME__.fullname" . }}
            port:
              number: <<ServicePort>>
`

const configMapTemplate = `apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "__CHART_NAME__.fullname" . }}-config
  labels:
    app: {{ include "__CHART_NAME__.name" . }}
data:
  <<ConfigMapKey>>: "<<ConfigMapValue>>"
`
