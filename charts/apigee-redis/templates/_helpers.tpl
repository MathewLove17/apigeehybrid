{{/*
  Check the helm binary version to ensure that it meets the minimum version
*/}}
{{- define "helmVersionCheck" -}}
{{- if semverCompare "<v3.10.0" .Capabilities.HelmVersion.Version -}}
{{- fail "Please use at least Helm v3.10.0 or above. You can find more about Helm releases and installation at https://github.com/helm/helm/releases." -}}
{{- end -}}
{{- end -}}

{{/*
  validateVersion
    @param version - version 
*/}}
{{- define "validateVersion" -}}
{{- $v := lower .version | replace "." "" }}
{{- if mustRegexMatch "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$" $v }}
{{- $v -}}
{{- else -}}
{{- fail "version .version is not a valid format" }}
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
  check whether external secret store is enabled and liveness probe also has a custom exec.
  these two are not compatible and will result in the custom exec not being used.
*/}}
{{- define "essLivenessProbeCheck" -}}
{{- with .Values.redis -}}
  {{- if and .auth.secretProviderClass .livenessProbe.exec -}}
  {{- fail "Using an external secret store (e.g. Vault) to provide Redis credentials and a custom livenessProbe.exec will cause the exec to be overridden and is unsupported." -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/*
  check whether external secret store is enabled and readiness probe also has a custom exec.
  these two are not compatible and will result in the custom exec not being used.
*/}}
{{- define "essReadinessProbeCheck" -}}
{{- with .Values.redis -}}
  {{- if and .auth.secretProviderClass .readinessProbe.exec -}}
  {{- fail "Using an external secret store (e.g. Vault) to provide Redis credentials and a custom readinessProbe.exec will cause the exec to be overridden and is unsupported." -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/*
    @param component - the component block for the seccomp profile.
    @param values - the whole context for this
*/}}
{{- define "getSeccompProfileInfo" -}}
{{- $profile := "" -}}
{{- $type := "" -}}
{{- if and .component .component.securityContext .component.securityContext.seccompProfile .component.securityContext.seccompProfile.type -}}
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