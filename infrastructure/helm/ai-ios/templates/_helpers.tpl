{{- define "ai-ios.name" -}}
ai-ios
{{- end -}}

{{- define "ai-ios.labels" -}}
app.kubernetes.io/part-of: {{ include "ai-ios.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "ai-ios.componentLabels" -}}
{{ include "ai-ios.labels" . }}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ $.Release.Name }}-{{ .component }}
{{- end -}}
