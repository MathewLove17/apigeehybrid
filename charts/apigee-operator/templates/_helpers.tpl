{{/*
  Check the helm binary version to ensure that it meets the minimum version
*/}}
{{- define "helmVersionCheck" -}}
{{- if semverCompare "<v3.10.0" .Capabilities.HelmVersion.Version -}}
{{- fail "Please use at least Helm v3.10.0 or above. You can find more about Helm releases and installation at https://github.com/helm/helm/releases." -}}
{{- end -}}
{{- end -}}

{{/*
  shortName
*/}}
{{- define "shortName" -}}
{{- substr 0 15 . -}}
{{- end -}}

{{/*
  shortSha
*/}}
{{- define "shortSha" -}}
{{- sha256sum . | trunc 7 -}}
{{- end -}}

{{/*
  orgScopeEncodedName
    @param name - string
*/}}
{{- define "orgScopeEncodedName" -}}
{{- if .name -}}
{{- printf "%s-%s" (include "shortName" .name) (include "shortSha" .name) -}}
{{- else -}}
{{ fail "Please provide org name in overrides" }}
{{- end -}}
{{- end -}}

{{/*
  nodeAffinity.runtime
*/}}
{{- define "nodeAffinity.runtime" -}}
nodeAffinity:
  {{- if .requiredForScheduling }}
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      - key: {{ quote (index .apigeeRuntime "key") }}
        operator: In
        values:
        - {{ quote (index .apigeeRuntime "value") }}
  {{- end }}
  preferredDuringSchedulingIgnoredDuringExecution:
  - weight: 100
    preference:
      matchExpressions:
      - key: {{ quote (index .apigeeRuntime "key") }}
        operator: In
        values:
        - {{ quote (index .apigeeRuntime "value") }}
{{- end -}}

{{/*
  namespace resolves the overridden namespace where a value from --namespace
  flag in the cmd line will have a higher precedence than in the override file
  or the default value from values.yaml.
*/}}
{{- define "namespace" -}}
{{- if eq .Release.Namespace "default" -}}
{{- .Values.namespace -}}
{{- else -}}
{{- .Release.Namespace -}}
{{- end -}}
{{- end -}}

{{/*
  container.image returns the image for the given component
    @param hub - string repo base url
    @param o - object component
    @param n - string image name
*/}}
{{- define "container.image" -}}
{{ if .hub }}
{{- printf "%s/%s:%s" .hub .n .o.image.tag -}}
{{ else }}
{{- printf "%s:%s" .o.image.url .o.image.tag -}}
{{- end -}}
{{- end -}}

{{/*
  metricsSA resolves the metrics service account from values.
*/}}
{{- define "metricsSA" -}}
  {{- $metricsName := "apigee-metrics" }}
  {{- $telemetryName := "apigee-telemetry" -}}
  {{- $generatedName := include "orgScopeEncodedName" (dict "name" .Values.org) -}}
  {{- if .Values.gcp.workloadIdentity.enabled -}}
  {{- printf "%s-sa" $metricsName -}}
  {{- else if .Values.multiOrgCluster -}}
  {{- printf "%s-%s" $metricsName $generatedName -}}
  {{- else -}}
  {{- printf "%s-%s" $metricsName $telemetryName -}}
  {{- end -}}
{{- end -}}

{{/*
  metricsAdapterSA resolves the previous metrics adapter service account name.
*/}}
{{- define "metricsAdapterSA" -}}
  {{- printf "apigee-metrics-adapter-apigee-telemetry" -}}
{{- end -}}

{{/*
  metricsAdapterName resolves the metrics adapter service account name.
*/}}
{{- define "metricsAdapterName" -}}
  {{- printf "apigee-metrics-adapter" -}}
{{- end -}}

{{/*
    @param values - the whole context for this
*/}}
{{- define "getGuardrailsSeccompProfileInfo" -}}
{{- $profile := "" -}}
{{- $type := "" -}}
{{- if and .values.guardrails .values.guardrails.securityContext .values.guardrails.securityContext.seccompProfile .values.guardrails.securityContext.seccompProfile.type -}}
  {{- $type = .values.guardrails.securityContext.seccompProfile.type -}}
  {{- if .values.guardrails.securityContext.seccompProfile.localhostProfile -}}
  {{- $profile = .values.guardrails.securityContext.seccompProfile.localhostProfile -}}
  {{- end -}}
{{- else if and .values .values.securityContext .values.securityContext.seccompProfile .values.securityContext.seccompProfile.type -}}
  {{- $type = .values.securityContext.seccompProfile.type -}}
  {{- if .values.securityContext.seccompProfile.localhostProfile -}}
  {{- $profile = .values.securityContext.seccompProfile.localhostProfile -}}
  {{- end -}}
{{- end -}}
{{- if and (ne $type "") (ne $type "RuntimeDefault") (ne $type "Unconfined") (ne $type "Localhost") -}}
  {{- fail "The seccomp profile type value should be empty or among RuntimeDefault, Unconfined, Localhost." -}}
{{- else if and (ne $type "Localhost") (ne $profile "") -}}
  {{- fail "The localhostProfile should be empty if the seccomp profile type is not Localhost." -}}
{{- else if and (eq $type "Localhost") (eq $profile "") -}}
  {{- fail "The localhostProfile can't be empty if the seccomp profile type is Localhost." -}}
{{- end -}}
{{- $result := dict "type" $type "localhostProfile" $profile -}}
{{- $result | toYaml -}}
{{- end -}}

{{/*
    @param component - the component block for the seccomp profile
    @param values - the context of the whole charts
*/}}
{{- define "getSeccompProfileInfo" -}}
{{- $profile := "" -}}
{{- $type := "" -}}
{{- if and .component.securityContext .component.securityContext.seccompProfile .component.securityContext.seccompProfile.type -}}
  {{- $type = .component.securityContext.seccompProfile.type -}}
  {{- if .component.securityContext.seccompProfile.localhostProfile -}}
  {{- $profile = .component.securityContext.seccompProfile.localhostProfile -}}
  {{- end -}}
{{- else if and .values.securityContext .values.securityContext.seccompProfile .values.securityContext.seccompProfile.type -}}
  {{- $type = .values.securityContext.seccompProfile.type -}}
  {{- if .values.securityContext.seccompProfile.localhostProfile -}}
  {{- $profile = .values.securityContext.seccompProfile.localhostProfile -}}
  {{- end -}}
{{- end -}}
{{- if and (ne $type "") (ne $type "RuntimeDefault") (ne $type "Unconfined") (ne $type "Localhost") -}}
  {{- fail "The seccomp profile type value should be empty or among RuntimeDefault, Unconfined, Localhost." -}}
{{- else if and (ne $type "Localhost") (ne $profile "") -}}
  {{- fail "The localhostProfile should be empty if the seccomp profile type is not Localhost." -}}
{{- else if and (eq $type "Localhost") (eq $profile "") -}}
  {{- fail "The localhostProfile can't be empty if the seccomp profile type is Localhost." -}}
{{- end -}}
{{- $result := dict "type" $type "localhostProfile" $profile -}}
{{- $result | toYaml -}}
{{- end -}}

{{/*
  tryFileContent.get returns file content otherwise error if file is empty or unreachable
    @param files - .Files object
    @param f - string filepath
*/}}
{{- define "tryFileContent.get" -}}
{{- $tr := (trimPrefix "./" .f) -}}
{{- $c := .files.Get $tr -}}
{{- if empty $c -}}
{{- fail (printf "'%s' is either an empty file or unreachable" $tr) -}}
{{- else -}}
{{- $c -}}
{{- end -}}
{{- end -}}

{{/*
  fwi.enabled will return true if federated workload identity is enabled
  It will also validate the FWI configuration
*/}}
{{- define "fwi.enabled" -}}
    {{- if .Values.gcp.federatedWorkloadIdentity.enabled -}}
        {{- if .Values.gcp.workloadIdentity.enabled -}}
            {{- fail "gcp.workloadIdentity.enabled must be false to use federated workload identity" -}}
        {{- end -}}
        {{- if empty .Values.gcp.federatedWorkloadIdentity.audience -}}
            {{- fail "audience required for federatedWorkloadIdentity" -}}
        {{- end -}}
        {{- if empty .Values.gcp.federatedWorkloadIdentity.credentialSourceFile -}}
            {{- fail "credentialSourceFile required for federatedWorkloadIdentity" -}}
        {{- end -}}
        {{- if or (empty .Values.gcp.federatedWorkloadIdentity.tokenExpiration) (lt (int64 .Values.gcp.federatedWorkloadIdentity.tokenExpiration) 600) -}}
            {{- fail "tokenExpiration >= 600 required for federatedWorkloadIdentity" -}}
        {{- end -}}
        {{- print true -}}
    {{- end -}}
{{- end -}}

{{- define "fwi.tokenPath" -}}
    {{- print (clean (dir .Values.gcp.federatedWorkloadIdentity.credentialSourceFile)) -}}
{{- end -}}

{{- define "fwi.tokenFile" -}}
    {{- print (base .Values.gcp.federatedWorkloadIdentity.credentialSourceFile) -}}
{{- end -}}
