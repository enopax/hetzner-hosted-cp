{{/*
Die Fassung in der Form, die der kubelet meldet.

Es gibt zwei Schreibweisen derselben Fassung, und sie sind nicht austauschbar:

  v1.36.3+k0s.0   die k0s-Release-Nummer. Die installiert k0s, die steht im
                  `K0sWorkerConfigTemplate`, und sie steht in `k0s.version`.
  v1.36.3+k0s     was der Knoten danach in
                  `Node.status.nodeInfo.kubeletVersion` meldet - ohne den
                  Zaehler hinter `+k0s`.

k0rdent vergleicht `Machine.spec.version` mit der **gemeldeten** Form, und
zwar als Zeichenkette, nicht als Semver. Am 2026-11-26 am laufenden Cluster
gemessen (enopax/enopax#49):

  spec.version: v1.36.3+k0s.0  →  "kubeletVersion v1.36.3+k0s,
                                   v1.36.3+k0s.0 required"  → UpToDate=False
  spec.version: v1.36.3+k0s    →  UpToDate=True

Deshalb rendert das MachineDeployment die gemeldete Form und das
`K0sWorkerConfigTemplate` weiter die Release-Nummer. Das ist **nicht**
Redundanz: k0smotron nimmt die Fassung aus dem WorkerConfig, wenn sie dort
steht, und nur sonst die vom Machine-Objekt - und dann normalisiert es sie mit
`fmt.Sprintf("%s+%s", version, "k0s.0")`. Aus `v1.36.3+k0s` wuerde dabei
`v1.36.3+k0s+k0s.0`, also Unsinn. Solange das so ist, muss die Release-Nummer
ausdruecklich im WorkerConfig stehen bleiben.

Das Schema laesst fuer `k0s.version` nur `vX.Y.Z+k0s.N` zu, deshalb genuegt
hier ein Schnitt am Zaehler.
*/}}
{{- define "hetzner-hosted-cp.kubeletVersion" -}}
{{- regexReplaceAll "\\+k0s\\.\\d+$" .Values.k0s.version "+k0s" -}}
{{- end -}}
