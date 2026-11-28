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
Redundanz: fuer den Aufbau nimmt k0smotron die Fassung aus dem WorkerConfig,
wenn sie dort steht, und nur sonst die vom Machine-Objekt - und dann
normalisiert es sie: aus `v1.36.3+k0s` wuerde `v1.36.3+k0s+k0s.0`, also
Unsinn. Solange das so ist, muss die Release-Nummer ausdruecklich im
WorkerConfig stehen bleiben.

**Fuer In-Place-Upgrades reicht das nicht, und es ist nicht zu reparieren.**
Am 2026-11-28 am laufenden `dev-box1` gemessen (enopax/enopax#65):
`extensions/inplaceversionupdate/autopilot.go` nimmt die Fassung
**unbedingt** vom Machine-Objekt und aus der Bootstrap-Config nur die
Download-URL:

  downloadURL, _ := getDownloadURLFromBootstrapConfig(..., desiredMachine.Spec.Bootstrap.ConfigRef, ...)
  version := util.NormalizeK0sVersion(desiredMachine.Spec.Version)

`NormalizeK0sVersion` prueft auf `+k0s.` **mit Punkt**; unsere kubelet-Form
hat keinen, also wird `+k0s.0` angehaengt. Der Autopilot-Plan trug dann

  version: v1.37.2+k0s+k0s.0
  url:     https://get.k0sproject.io/v1.37.2+k0s+k0s.0/k0s-...-amd64   → 404

und blieb auf `ApplyFailed`. Die beiden Anforderungen widersprechen sich:
k0rdent will hier die kubelet-Form, die In-Place-Extension will die
Release-Nummer. **Eine Chart kann nicht beides.** Wer hier also die
Release-Nummer wieder einsetzt, um In-Place zu heilen, bricht `UpToDate` an
jedem Cluster - der Weg ist gemessen und zu.

Das Schema laesst fuer `k0s.version` nur `vX.Y.Z+k0s.N` zu, deshalb genuegt
hier ein Schnitt am Zaehler.
*/}}
{{- define "hetzner-hosted-cp.kubeletVersion" -}}
{{- regexReplaceAll "\\+k0s\\.\\d+$" .Values.k0s.version "+k0s" -}}
{{- end -}}
