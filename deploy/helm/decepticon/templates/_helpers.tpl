{{/*
Expand the name of the chart.
*/}}
{{- define "decepticon.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "decepticon.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "decepticon.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "decepticon.labels" -}}
helm.sh/chart: {{ include "decepticon.chart" . }}
{{ include "decepticon.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "decepticon.selectorLabels" -}}
app.kubernetes.io/name: {{ include "decepticon.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "decepticon.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "decepticon.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference helper. Constructs registry/repo:tag.
Usage: {{ include "decepticon.image" (dict "image" .Values.litellm.image "global" .Values.global) }}
*/}}
{{- define "decepticon.image" -}}
{{- $registry := .global.imageRegistry -}}
{{- $repo := .image.repository -}}
{{- $tag := default .global.imageTag (.image.tag | default "") -}}
{{- printf "%s/%s:%s" $registry $repo $tag -}}
{{- end }}

{{/*
PostgreSQL DSN from values.
*/}}
{{- define "decepticon.postgresDSN" -}}
{{- printf "postgresql://%s:%s@%s:%v/%s" .Values.postgres.username .Values.postgres.password .Values.postgres.host (int .Values.postgres.port) .Values.postgres.database -}}
{{- end }}
