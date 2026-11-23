# Hetzner Hosted Control Plane Chart

A Helm chart for deploying Kubernetes clusters on Hetzner Cloud using k0smotron's hosted control plane architecture. This chart enables cost-effective cluster provisioning by running control plane components as pods within the management cluster while worker nodes are provisioned on Hetzner Cloud infrastructure.

## Architecture Overview

### Hosted Control Plane Architecture

Unlike traditional cluster deployments where control plane nodes run on dedicated infrastructure, this chart leverages **k0smotron** to run control plane components (API server, scheduler, controller manager, etcd) as pods within the management cluster. This approach provides several benefits:

- **Cost Reduction**: Eliminates the need for dedicated control plane machines, reducing infrastructure costs by approximately 60%
- **Simplified Operations**: Control plane lifecycle is managed by the management cluster
- **Centralized Management**: All control planes are co-located in the management cluster
- **High Availability**: Control plane pods can be scaled and distributed across management cluster nodes
- **Hostname-Based Access**: Control planes are accessible via custom hostnames through the management cluster's ingress controller

### Component Architecture

```
Management Cluster (k0rdent + k0smotron + HAProxy Ingress)
├── HAProxy Ingress Controller (with SSL passthrough)
├── LoadBalancer Service (exposes HAProxy to external traffic)
├── Control Plane Pods (API Server, Scheduler, Controller Manager, etcd)
│   └── Accessed via Ingress with hostname-based routing
├── k0smotron Controller
├── Cluster API Controllers (CAPI, CAPH)
└── k0rdent Management Platform

Hetzner Cloud Infrastructure (User Cluster)
├── Worker Nodes (run application workloads)
└── Private Network (optional)
```

### Traffic Flow for Control Plane Access

1. **External Client** → DNS resolves `api.cluster01.example.com` to Management Cluster LoadBalancer IP
2. **Management LoadBalancer** → Routes traffic to HAProxy Ingress Controller based on SNI (hostname)
3. **HAProxy Ingress** → SSL passthrough to Control Plane Pod based on hostname
4. **Control Plane Pod** → Processes Kubernetes API requests
5. **Response** → Returns through the same path with end-to-end encryption

**Key Points:**
- The LoadBalancer is deployed **once** in the management cluster and shared across all hosted control planes
- Each hosted control plane gets unique hostnames (e.g., `api.cluster01.example.com`, `api.cluster02.example.com`)
- SSL passthrough preserves end-to-end encryption from client to control plane pod
- No per-cluster LoadBalancer is created, reducing costs and complexity

### Data Flow

1. **Cluster Creation**: k0rdent renders this Helm chart and creates Cluster API resources
2. **Control Plane Deployment**: k0smotron creates control plane pods in the management cluster with ingress configuration
3. **Ingress Setup**: Ingress resources are created with hostname-based routing and SSL passthrough annotations
4. **Infrastructure Provisioning**: CAPH provisions Hetzner private network and worker machines (no load balancer)
5. **Worker Join**: Worker nodes connect to control plane via management cluster ingress using the configured hostname
6. **API Access**: External clients access the cluster via management cluster LoadBalancer using custom hostnames

## Differences from hetzner-standalone-cp

| Feature | hetzner-standalone-cp | hetzner-hosted-cp |
|---------|----------------------|-------------------|
| Control Plane Location | Dedicated Hetzner machines | Pods in management cluster |
| Control Plane Resource | K0sControlPlane | K0smotronControlPlane |
| Infrastructure Cost | Higher (CP + workers) | Lower (workers only) |
| Control Plane Scaling | Machine-based | Pod-based |
| Management Complexity | Higher | Lower |
| Ingress Support | Limited | Full support with apiHost/konnectivityHost |
| HAProxy Sidecar | Not available | Available for ingress proxying |

## Prerequisites

### Management Cluster Requirements

Before deploying hosted control plane clusters, the management cluster MUST have the following infrastructure:

1. **HAProxy Ingress Controller** with SSL passthrough support
   ```bash
   # Example installation
   helm install haproxy-ingress haproxy-ingress/haproxy-ingress \
     --namespace ingress-controller \
     --create-namespace \
     --set controller.service.type=LoadBalancer
   ```

2. **LoadBalancer Service** exposing the HAProxy ingress controller
   - This LoadBalancer is shared across all hosted control plane clusters
   - DNS records for all hosted control plane hostnames must point to this LoadBalancer IP

3. **DNS Configuration**
   - Create DNS A/AAAA records pointing to the management cluster LoadBalancer IP
   - Example: `*.clusters.example.com` → `<management-lb-ip>`
   - Or individual records: `api.cluster01.example.com` → `<management-lb-ip>`

### Software Requirements

- **k0rdent**: v1.6.0 or newer
- **k0smotron**: v1.10.2 or newer  
- **Cluster API**: v1.0.7 or newer
- **CAPH (Cluster API Provider Hetzner)**: v1.0.7 or newer
- **Hetzner Cloud API Token**: With appropriate permissions

## Installation

### 1. Install as ClusterTemplate

```bash
# Add the chart repository (if using Helm repository)
helm repo add enopax https://enopax.github.io/helm-charts

# Or install directly from OCI registry
kubectl apply -f - <<EOF
apiVersion: kcm.enopax.io/v1alpha1
kind: ClusterTemplate
metadata:
  name: hetzner-hosted-cp
  namespace: kcm-system
spec:
  helm:
    chartRef:
      kind: HelmChart
      name: oci://ghcr.io/enopax/templates/hetzner-hosted-cp
      version: "0.1.0"
EOF
```

### 2. Create Cluster Deployment

```bash
kubectl apply -f - <<EOF
apiVersion: kcm.enopax.io/v1alpha1
kind: ClusterDeployment
metadata:
  name: my-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp
  credential: hetzner-credential
  config:
    clusterName: my-hosted-cluster
    region: fsn1
    sshKeyName: my-ssh-key
    hetznerSecretName: hetzner
    worker:
      serverType: cpx32
      imageName: ubuntu-24.04
      replicas: 3
    clusterNetwork:
      pods:
        cidrBlock: "10.244.0.0/16"
      services:
        cidrBlock: "10.96.0.0/12"
    k0s:
      version: v1.35.4+k0s.0
    ingress:
      enabled: true
      apiHost: api.my-hosted-cluster.example.com
      konnectivityHost: k.my-hosted-cluster.example.com
EOF
```

## Configuration Options

### Basic Configuration

```yaml
# Required
clusterName: "my-cluster"        # Name of the child cluster; every object is named after it
region: "fsn1"                   # Hetzner location
sshKeyName: "my-ssh-key"         # Exactly one key name, singular

# Worker machines
worker:
  serverType: "cpx32"            # Machine type
  imageName: "ubuntu-24.04"      # OS image
  replicas: 2                    # Number of worker nodes — this is what scaling changes
```

> **Dies ist nicht das Vokabular von `hetzner-standalone-cp`.** Hier stand es
> einmal — `workersNumber`, `sshKeyNames` als Liste, `tokenRef`, `worker.type`,
> `worker.image` — und genau daraus ist ein Fehler entstanden: ein Dienst
> schrieb beim Skalieren `workersNumber`, die Kubernetes-API nahm den
> Schlüssel an, kein Template las ihn, und es entstand keine Maschine
> (enopax/enopax#38). Was dieses Chart liest, steht vollständig in der Tabelle
> unten.

### Alle Werte, die dieses Chart liest

Erzeugt aus `grep -rho '\.Values\.[A-Za-z0-9_.]*' templates | sort -u`. Was
hier nicht steht, wird nicht gelesen — auch wenn das Schema es annimmt.

| Wert | Wirkung |
|---|---|
| `clusterName` | Name aller Objekte (`-cp`, `-mt`, `-md`, `-machine-config`) |
| `region` | Hetzner-Standort der Maschinen |
| `sshKeyName` | Schlüsselname, **einer** |
| `hetznerSecretName` | Secret, auf das `HetznerCluster.spec.hetznerSecretRef` zeigt |
| `clusterNetwork.pods.cidrBlock`, `clusterNetwork.services.cidrBlock` | Netze, **Singular** |
| `etcd.autoDeletePVCs` | etcd-PVCs der Steuerungsebene |
| `k0s.version` | k0s-Schreibweise, Muster `v<x>.<y>.<z>+k0s.<n>` |
| `core.serverType`, `core.imageName`, `core.replicas` | der statische Pool — **nur mit Autoskalierung** |
| `worker.serverType`, `worker.imageName`, `worker.replicas` | der skalierbare Pool |
| `autoscaling.enabled`, `.minSize`, `.maxSize`, `.capacityHints` | Autoskalierung und der core-Pool |
| `ingress.enabled`, `.apiHost`, `.konnectivityHost`, `.className`, `.port`, `.annotations` | Zugang zur Steuerungsebene |

KCM schickt beim Anlegen zusätzlich `clusterIdentity`, `clusterLabels` und
`clusterAnnotations` mit. Dieses Chart liest sie nicht; sie stehen im Schema,
damit niemand sie für eine Einstellung dieses Charts hält.

### Advanced Configuration

#### Ingress Configuration

Enable hostname-based access to your cluster using ingress:

```yaml
ingress:
  enabled: true
  apiHost: "api.my-cluster.example.com"    # Kubernetes API hostname
  konnectivityHost: "k.my-cluster.example.com"
  className: "haproxy"
  port: 443
  annotations:
    haproxy.org/ssl-passthrough: "true"
```

Der Schlüssel heißt `ingress`, nicht `controlPlane.ingress` — ein
`controlPlane` kennt dieses Chart nicht.

**Und er schaltet mehr als den Ingress:** das `{{- if and .Values.ingress.enabled … }}`
in `templates/k0smotroncontrolplane.yaml` umschließt auch `k0sConfig` bis zum
Dateiende, also Netz, CNI, CCM und CSI. Mit `ingress.enabled: false` — der
Vorgabe des Charts — entsteht eine Steuerungsebene ohne Netzkonfiguration. Das
ist vermutlich unbeabsichtigt und in `tests/property/test_rendered_values.py`
festgehalten, nicht gebilligt.

When ingress is enabled:
- Clients can access the Kubernetes API using the custom hostname instead of IP addresses
- Requires an ingress controller in the management cluster
- DNS must be configured to point hostnames to the ingress controller
- See [k0smotron ingress documentation](https://docs.k0smotron.io/stable/ingress-support/) for detailed setup

#### HAProxy Sidecar Configuration

Enable additional worker configuration:

> **Dieses Chart liest das nicht.** Kein Template verweist auf `workerConfig` -
> nachzusehen mit `grep -rho '\.Values\.[A-Za-z0-9_.]*' templates | sort -u`.
> Der Abschnitt beschreibt etwas, das es hier nicht gibt; ob es kommen soll
> oder gehen, ist offen. Bis dahin: kopieren bringt nichts.

```yaml
workerConfig:
  args:
    - --enable-cloud-provider
    - --kubelet-extra-args="--cloud-provider=external"
  preInstallCommands:
    - "echo 'Setting up worker node'"
  postStartCommands:
    - "echo 'Worker node ready'"
```

This allows customization of the k0s worker configuration and lifecycle hooks.

#### Autoscaling with Split Worker Pools

When autoscaling is enabled, the chart creates two separate node pools:

- **Core pool** — A static pool (not autoscaled) that runs system and infrastructure pods (coredns, metrics-server, hcloud-ccm, hcloud-csi-controller, cilium-operator, sveltos-agent)
- **Worker pool** — An autoscaled pool with a `NoSchedule` taint, exclusively for user workloads

This separation ensures that autoscaled worker nodes only run user workloads and can be cleanly removed during scale-down without system pods blocking eviction.

```yaml
# Core pool (static, runs system pods)
core:
  serverType: "cpx22"
  imageName: "ubuntu-24.04"
  replicas: 1

# Worker pool (autoscaled, runs user workloads)
worker:
  serverType: "cpx22"
  imageName: "ubuntu-24.04"
  replicas: 1                    # Initial replica count

autoscaling:
  enabled: true
  minSize: 1                     # Minimum worker nodes
  maxSize: 5                     # Maximum worker nodes
  capacityHints:                 # Optional, helps autoscaler estimate capacity
    cpu: "4"
    memory: "8Gi"
```

**Resources created when autoscaling is enabled:**

| Resource | Core Pool | Worker Pool |
|----------|-----------|-------------|
| HCloudMachineTemplate | `{cluster}-core-mt` | `{cluster}-mt` |
| K0sWorkerConfigTemplate | `{cluster}-core-machine-config` | `{cluster}-machine-config` |
| MachineDeployment | `{cluster}-core-md` (static) | `{cluster}-md` (autoscaler annotations) |

**Taint strategy:**

Worker pool nodes are tainted with `node-role.kubernetes.io/worker=:NoSchedule`. User workloads must include a toleration:

```yaml
tolerations:
  - key: node-role.kubernetes.io/worker
    operator: Exists
    effect: NoSchedule
```

DaemonSets (cilium, kube-proxy, konnectivity, hcloud-csi-node) tolerate all taints and still run on worker nodes. System Deployments without this toleration naturally stay on core nodes.

When autoscaling is disabled (default), the chart creates a single MachineDeployment identical to previous versions — fully backwards compatible.

#### Private Networking

> **Dieses Chart liest das nicht.** Kein Template verweist auf `hcloudNetwork` -
> nachzusehen mit `grep -rho '\.Values\.[A-Za-z0-9_.]*' templates | sort -u`.
> Der Abschnitt beschreibt etwas, das es hier nicht gibt; ob es kommen soll
> oder gehen, ist offen. Bis dahin: kopieren bringt nichts.

```yaml
hcloudNetwork:
  enabled: true
  cidrBlock: "10.0.0.0/16"
  subnetCidrBlock: "10.0.0.0/24"
  networkZone: "eu-central"
```

#### Control Plane Scaling

> **Dieses Chart liest das nicht.** Kein Template verweist auf `controlPlane` -
> nachzusehen mit `grep -rho '\.Values\.[A-Za-z0-9_.]*' templates | sort -u`.
> Der Abschnitt beschreibt etwas, das es hier nicht gibt; ob es kommen soll
> oder gehen, ist offen. Bis dahin: kopieren bringt nichts.

```yaml
controlPlane:
  replicas: 3  # Scale control plane pods for high availability
```

#### Custom k0s Configuration

Gelesen wird genau **eine** Angabe, und sie ist Pflichtform:

```yaml
k0s:
  version: "v1.35.4+k0s.0"   # Muster v<x>.<y>.<z>+k0s.<n>, vom Schema erzwungen
```

Die Schreibweise ist keine Formalie: die Vorlage baut aus der Version eine
Download-URL. `1.30.4` ergibt eine, die es nicht gibt - und das fällt erst
auf, wenn die Maschine schon läuft und bezahlt wird. `values.schema.json`
weist es deshalb vorher ab.

Das Netz des Kindclusters kommt aus `clusterNetwork` (Singular `cidrBlock`),
nicht aus `k0s.network`.

> **Dieses Chart liest `k0s.api`, `k0s.network` und `workerConfig` nicht.**
> Hier stand ein Beispiel mit allen dreien. Die k0s-Konfiguration der
> Steuerungsebene steht fest in `templates/k0smotroncontrolplane.yaml`; wer
> daran etwas einstellen will, braucht erst einen Wert im Chart.

## Usage Examples

> Die Beispiele 1, 2 und 4 standen hier im Vokabular des
> **standalone**-Charts und mit einer `apiVersion`, die es nicht gibt
> (`kcm.enopax.io/v1alpha1`). Sie sind durch Fassungen ersetzt, die diesem
> Chart entsprechen; Beispiel 3 war schon richtig. Vorlage und Felder sind an
> einem Cluster nachgesehen, der läuft, nicht aus den Chart-Vorgaben
> hergeleitet.

### Example 1: Basic Hosted Cluster

```yaml
apiVersion: k0rdent.mirantis.com/v1beta1
kind: ClusterDeployment
metadata:
  name: basic-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp-1-5-1
  credential: hcloud-cluster-provisioning
  config:
    clusterName: basic-hosted-cluster
    region: fsn1
    sshKeyName: production-key
    hetznerSecretName: hetzner
    worker:
      serverType: cpx32
      imageName: ubuntu-24.04
      replicas: 2
    k0s:
      version: v1.35.4+k0s.0
    ingress:
      enabled: true
      apiHost: api.basic-hosted-cluster.example.com
      konnectivityHost: k.basic-hosted-cluster.example.com
```

### Example 2: Production Cluster with Ingress

```yaml
apiVersion: k0rdent.mirantis.com/v1beta1
kind: ClusterDeployment
metadata:
  name: production-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp-1-5-1
  credential: hcloud-cluster-provisioning
  config:
    clusterName: production-hosted-cluster
    region: fsn1
    sshKeyName: production-key
    hetznerSecretName: hetzner
    worker:
      serverType: cpx42
      imageName: ubuntu-24.04
      replicas: 5
    clusterNetwork:
      pods:
        cidrBlock: "10.244.0.0/16"
      services:
        cidrBlock: "10.96.0.0/12"
    etcd:
      autoDeletePVCs: true
    k0s:
      version: v1.35.4+k0s.0
    ingress:
      enabled: true
      apiHost: api.prod-cluster.company.com
      konnectivityHost: k.prod-cluster.company.com
      className: haproxy
      port: 443
      annotations:
        haproxy.org/ssl-passthrough: "true"
```

Die Steuerungsebene ist hier **nicht** hochverfügbar konfiguriert, und das
lässt sich mit diesem Chart auch nicht: `controlPlane.replicas` stand im
vorigen Beispiel, existiert aber nicht — siehe unten, § Control Plane
Scaling.

### Example 3: Autoscaled Cluster with Split Worker Pools

```yaml
apiVersion: k0rdent.mirantis.com/v1beta1
kind: ClusterDeployment
metadata:
  name: autoscaled-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp-1-5-0
  credential: hcloud-cluster-provisioning
  config:
    clusterName: autoscaled-cluster
    region: nbg1
    sshKeyName: my-key
    core:
      serverType: cpx22
      imageName: ubuntu-24.04
      replicas: 1
    worker:
      serverType: cpx22
      imageName: ubuntu-24.04
      replicas: 1
    autoscaling:
      enabled: true
      minSize: 1
      maxSize: 5
    ingress:
      enabled: true
      apiHost: api.autoscaled.k8s.example.com
      konnectivityHost: k.autoscaled.k8s.example.com
    k0s:
      version: v1.35.4+k0s.0
```

### Example 4: Development Cluster

```yaml
apiVersion: k0rdent.mirantis.com/v1beta1
kind: ClusterDeployment
metadata:
  name: dev-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp-1-5-1
  credential: hcloud-cluster-provisioning
  config:
    clusterName: dev-hosted-cluster
    region: nbg1
    sshKeyName: dev-key
    hetznerSecretName: hetzner
    worker:
      serverType: cpx22
      imageName: ubuntu-24.04
      replicas: 1
    k0s:
      version: v1.35.4+k0s.0
    ingress:
      enabled: true
      apiHost: api.dev-hosted-cluster.example.com
      konnectivityHost: k.dev-hosted-cluster.example.com
```

## Monitoring and Troubleshooting

### Check Cluster Status

```bash
# List clusters
kubectl get clusters -n kcm-system

# Check cluster deployment status
kubectl describe clusterdeployment my-hosted-cluster -n kcm-system

# Check control plane pods
kubectl get pods -n kcm-system -l cluster.x-k8s.io/cluster-name=my-hosted-cluster
```

### Access Cluster

```bash
# Get kubeconfig (when cluster is ready)
kubectl get secret my-hosted-cluster-kubeconfig -n kcm-system -o jsonpath='{.data.value}' | base64 -d > my-cluster-kubeconfig.yaml

# Use the cluster
kubectl --kubeconfig my-cluster-kubeconfig.yaml get nodes
```

### Common Issues

1. **Control Plane Pods Not Starting**: Check k0smotron controller logs and ensure management cluster has sufficient resources
2. **Workers Not Joining**: Verify load balancer configuration and network connectivity
3. **Ingress Not Working**: Ensure ingress controller is running in management cluster and DNS is configured
4. **HAProxy Sidecar Issues**: Check ingress endpoint configuration and network policies

## Security Considerations

- **API Token**: Store Hetzner API token in a Kubernetes Secret with appropriate RBAC
- **SSH Keys**: Use dedicated SSH keys for cluster nodes, rotate regularly
- **Network Security**: Enable private networking and configure security groups appropriately
- **Control Plane Access**: Use ingress with TLS termination for production clusters
- **RBAC**: Configure appropriate RBAC policies for cluster access

## Cost Optimization

- **Control Plane**: No infrastructure cost (runs in management cluster)
- **Worker Nodes**: Choose appropriate machine types based on workload requirements
- **Load Balancer**: Single load balancer per cluster (shared across all workers)
- **Private Network**: Optional, adds minimal cost but improves security
- **Scaling**: Scale worker nodes based on actual usage

## Migration from hetzner-standalone-cp

To migrate from the standalone control plane chart:

1. **Backup**: Export existing cluster configurations and workloads
2. **Deploy**: Create new hosted control plane cluster with this chart
3. **Migrate**: Move workloads to the new cluster
4. **Cleanup**: Delete old standalone cluster

Note: Direct in-place migration is not supported due to architectural differences.

## Contributing

This chart is part of the Enopax ecosystem. For issues, feature requests, or contributions, please visit the project repository.

## License

This chart is licensed under the same terms as the parent project.