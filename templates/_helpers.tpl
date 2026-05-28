{{/*
Cluster name - base name for all resources
*/}}
{{- define "cluster.name" -}}
    {{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
K0smotronControlPlane name - hosted control plane resource
*/}}
{{- define "k0smotroncontrolplane.name" -}}
    {{- include "cluster.name" . }}-cp
{{- end }}

{{/*
HCloudMachineTemplate name for worker nodes
*/}}
{{- define "hcloudmachinetemplate.worker.name" -}}
    {{- include "cluster.name" . }}-worker-mt
{{- end }}

{{/*
K0sWorkerConfigTemplate name - worker node k0s configuration
*/}}
{{- define "k0sworkerconfigtemplate.name" -}}
    {{- include "cluster.name" . }}-machine-config
{{- end }}

{{/*
MachineDeployment name - worker node deployment
*/}}
{{- define "machinedeployment.name" -}}
    {{- include "cluster.name" . }}-md
{{- end }}
