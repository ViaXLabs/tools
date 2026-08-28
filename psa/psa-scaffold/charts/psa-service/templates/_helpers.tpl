{{/*
CHART: charts/psa-service (templates/_helpers.tpl)
psa.fullname is deliberately just {{ .Release.Name }} -- when Terraform's
helm_release sets name = "psa-java" or "psa-python", every resource in
this chart is named after that release automatically, no extra plumbing.
*/}}
{{- define "psa.fullname" -}}
{{ .Release.Name }}
{{- end -}}

{{- define "psa.labels" -}}
app.kubernetes.io/name: {{ include "psa.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "psa.selectorLabels" -}}
app.kubernetes.io/name: {{ include "psa.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
