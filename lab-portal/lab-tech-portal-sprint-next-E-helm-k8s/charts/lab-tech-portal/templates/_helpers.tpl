{{/*
Expand the name of the chart.
*/}}
{{- define "lab-tech-portal.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited.
*/}}
{{- define "lab-tech-portal.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value.
*/}}
{{- define "lab-tech-portal.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "lab-tech-portal.labels" -}}
helm.sh/chart: {{ include "lab-tech-portal.chart" . }}
{{ include "lab-tech-portal.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used by Deployments and Services.
*/}}
{{- define "lab-tech-portal.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lab-tech-portal.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ConfigMap name helper.
*/}}
{{- define "lab-tech-portal.configMapName" -}}
{{ include "lab-tech-portal.fullname" . }}-config
{{- end }}

{{/*
SealedSecret name helper.
The SealedSecret resource itself is defined in issue #51 (separate sprint item).
This name is referenced by Deployments via envFrom.secretRef.
*/}}
{{- define "lab-tech-portal.secretName" -}}
{{ include "lab-tech-portal.fullname" . }}-secrets
{{- end }}
