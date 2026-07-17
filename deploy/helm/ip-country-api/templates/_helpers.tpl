{{- define "ip-country-api.name" -}}
ip-country-api
{{- end }}

{{- define "ip-country-api.fullname" -}}
{{- printf "%s" (include "ip-country-api.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ip-country-api.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{ include "ip-country-api.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ip-country-api
{{- end }}

{{- define "ip-country-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ip-country-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ip-country-api.serviceAccountName" -}}
{{- printf "%s" (include "ip-country-api.fullname" .) }}
{{- end }}

{{- define "ip-country-api.secretName" -}}
{{- printf "%s-runtime" (include "ip-country-api.fullname" .) }}
{{- end }}

{{- define "ip-country-api.image" -}}
{{- if .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must be a sha256 digest" -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else if .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- else -}}
{{- fail "either image.digest or image.tag must be set" -}}
{{- end -}}
{{- end }}
