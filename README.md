# Hetzner Hosted Control Plane Chart

A Helm chart for deploying Kubernetes clusters on Hetzner Cloud using k0smotron's hosted control plane architecture. This chart enables cost-effective cluster provisioning by running control plane components as pods within the management cluster while worker nodes are provisioned on Hetzner Cloud infrastructure.

## What's new in 1.3.0

Chart bump targeting k0rdent v1.9.0. Cherry-picks improvements from `k0rdent-oot/hetzner-hosted-cp` upstream and from an internal redesign proposal, while keeping the existing multi-mode access work.

### Added

| Feature | What | Why |
|---|---|---|
| `appVersion: 1.9.0` + `k0rdent.mirantis.com/min-version` annotation | Chart now declares its k0rdent dependency | Mirantis tooling can refuse to install against older mgmt clusters |
| `k0s v1.34.4+k0s.0` (was v1.34.3) | Default k0s version bump | New k0s ships with k0smotron ingress field rename (`apiPort`/`konnectivityPort`) plus security fixes |
| **CCM-in-child** (`controlPlane.ccm.enabled`) | Optional: deploy `hcloud-cloud-controller-manager` inside the child cluster via `k0sConfig.extensions.helm` instead of separately in the management cluster | Solves the chicken-and-egg with the internal `kubernetes` service. Worker nodes initialise faster, less manual post-bootstrap manifests to apply |
| **Hetzner worker `preStartCommands` defaults** | systemd-resolved disable, `/etc/resolv.conf` reset to Cloudflare DNS, `swapoff -a`, fstab swap commenting | Hetzner ubuntu-24.04 images ship with systemd-resolved which interferes with coredns. Without this fix workers come up but DNS in the cluster is flaky |
| `preStartCommands` block in `K0sWorkerConfigTemplate` | New override knob in addition to existing `preInstallCommands` / `postStartCommands` | Lets users add their own pre-k0s-start hooks |

### Kept (intentionally — these were proposed for removal in a competing 1.3.0 draft)

| Feature | Why we kept it |
|---|---|
| **Multi-mode access** (`LoadBalancer` / `NodePort` / `Ingress`) | NodePort is the simplest mode for dev/demo (no DNS needed); LoadBalancer is the simplest for production-without-ingress; Ingress is the cheapest at scale. All three have real callers in our infra |
| **KCM `@schema` annotations on `values.yaml`** | k0rdent UI uses these for auto-discovery and form generation |
| **`_helpers.tpl`** | Centralised name generation, no `{{ .Values.clusterName }}` sprinkled throughout templates |
| **`placementGroupName`, `hcloudNetwork`, `dataDisks`, `additionalSecurityGroups`** | Real Hetzner features used by real users. Removing them breaks HA setups and existing deployments |
| **`sshKeyNames` (list)** | Most operators have multiple keys (deploy + admin + CI). Single-key was a regression |
| **`tokenRef` pattern** | CAPH-standard. Tooling elsewhere expects `hcloud-token` as the secret key, not a hardcoded `hcloud` |
| **`clusterLabels` / `clusterAnnotations` / KCM cleanup finalizer** | Required for cluster tagging and clean KCM lifecycle |

### Removed

Nothing — this is a backwards-compatible upgrade. Existing values files continue to work; `controlPlane.ccm.enabled` defaults to `false` to preserve the legacy "deploy CCM separately into the user cluster" workflow.

### Upgrade notes

- If you previously rendered against the old defaults you now also get `preStartCommands` applied — these are no-ops on most Hetzner ubuntu-24.04 images, but if you have a custom image without systemd-resolved set `workerConfig.preStartCommands: []` to silence them.
- Setting `controlPlane.ccm.enabled=true` in **LoadBalancer mode** fails the helm render with a helpful error (the LB IP isn't known at bootstrap time). Use ingress or NodePort mode, or keep CCM deployed separately.

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

- **k0rdent**: v1.9.0 or newer (declared via the `k0rdent.mirantis.com/min-version` annotation in `Chart.yaml`)
- **k0s**: v1.34.4+k0s.0 (default in `values.yaml`)
- **k0smotron**: bundled with k0rdent 1.9.0
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
    region: fsn1
    workersNumber: 3
    sshKeyNames:
      - my-ssh-key
    tokenRef:
      name: hcloud-token
      key: token
EOF
```

## Configuration Options

### Basic Configuration

```yaml
# Required settings
region: "fsn1"                    # Hetzner region
workersNumber: 2                  # Number of worker nodes
tokenRef:
  name: "hcloud-token"           # Secret containing Hetzner API token
  key: "token"
sshKeyNames:
  - "my-ssh-key"                 # SSH keys for node access

# Worker machine configuration
worker:
  type: "cpx22"                  # Machine type
  image: "ubuntu-24.04"          # OS image
```

### Advanced Configuration

#### Ingress Configuration

Enable hostname-based access to your cluster using ingress:

```yaml
controlPlane:
  ingress:
    enabled: true
    apiHost: "api.my-cluster.example.com"              # Kubernetes API hostname
    konnectivityHost: "konnectivity.my-cluster.example.com"  # Konnectivity hostname
```

When ingress is enabled:
- Clients can access the Kubernetes API using the custom hostname instead of IP addresses
- Requires an ingress controller in the management cluster
- DNS must be configured to point hostnames to the ingress controller
- See [k0smotron ingress documentation](https://docs.k0smotron.io/stable/ingress-support/) for detailed setup

#### Worker lifecycle hooks

```yaml
workerConfig:
  args:
    - --enable-cloud-provider
    - --kubelet-extra-args="--cloud-provider=external"
  preInstallCommands:
    - "echo 'Before k0s install'"
  preStartCommands:
    - "echo 'Before k0s start (defaults include systemd-resolved disable and swap off for Hetzner)'"
  postStartCommands:
    - "echo 'After k0s start'"
```

Three phases are exposed:
- `preInstallCommands` — before `k0s install`
- `preStartCommands` — after install, before `systemctl start k0sworker`. **The chart ships defaults** to work around Hetzner ubuntu-24.04 quirks (systemd-resolved + swap). Override with `workerConfig.preStartCommands: []` to disable, or extend with your own
- `postStartCommands` — after the worker is up

#### CCM in child cluster (new in 1.3.0)

```yaml
controlPlane:
  ccm:
    enabled: true
    chartVersion: ""  # empty = latest hcloud-cloud-controller-manager
```

When enabled, k0smotron deploys `hcloud-cloud-controller-manager` into the child cluster as part of bootstrap (via `k0sConfig.extensions.helm`). This avoids the chicken-and-egg between the in-cluster `kubernetes` service and the CCM that's supposed to make it work. Required values:
- `tokenRef.name` / `tokenRef.key` — the chart reuses the Hetzner token secret for the CCM
- Either `controlPlane.ingress.apiHost` (ingress mode) or `controlPlane.endpoint.host` + `service.apiNodePort` (NodePort mode)

LoadBalancer mode is intentionally unsupported here — the LB IP isn't known at bootstrap time, so CCM-in-child would not be able to reach the API. Use ingress/NodePort, or keep `ccm.enabled=false` and deploy CCM separately.

#### Private Networking

```yaml
hcloudNetwork:
  enabled: true
  cidrBlock: "10.0.0.0/16"
  subnetCidrBlock: "10.0.0.0/24"
  networkZone: "eu-central"
```

#### Control Plane Scaling

```yaml
controlPlane:
  replicas: 3  # Scale control plane pods for high availability
```

#### Custom k0s Configuration

```yaml
k0s:
  version: "v1.34.2+k0s.0"
  api:
    extraArgs:
      audit-log-maxage: "30"
  network:
    podCIDR: "10.244.0.0/16"
    serviceCIDR: "10.96.0.0/12"

workerConfig:
  preInstallCommands:
    - "apt-get update"
  postStartCommands:
    - "systemctl enable k0s"
  files:
    - path: "/etc/custom-config.yaml"
      content: |
        custom: configuration
```

## Usage Examples

### Example 1: Basic Hosted Cluster

```yaml
apiVersion: kcm.enopax.io/v1alpha1
kind: ClusterDeployment
metadata:
  name: basic-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp
  credential: hetzner-credential
  config:
    region: fsn1
    workersNumber: 2
    tokenRef:
      name: hcloud-token
      key: token
    sshKeyNames:
      - production-key
    worker:
      type: cpx22
      image: ubuntu-24.04
```

### Example 2: Production Cluster with Ingress

```yaml
apiVersion: kcm.enopax.io/v1alpha1
kind: ClusterDeployment
metadata:
  name: production-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp
  credential: hetzner-credential
  config:
    region: fsn1
    workersNumber: 5
    controlPlane:
      replicas: 3
      ingress:
        enabled: true
        apiHost: api.prod-cluster.company.com
        konnectivityHost: konnectivity.prod-cluster.company.com
    tokenRef:
      name: hcloud-token
      key: token
    sshKeyNames:
      - production-key
    worker:
      type: cpx31
      image: ubuntu-24.04
      placementGroupName: prod-workers
    hcloudNetwork:
      enabled: true
      cidrBlock: "10.100.0.0/16"
      subnetCidrBlock: "10.100.1.0/24"
    workerConfig:
      args:
        - --enable-cloud-provider
        - --kubelet-extra-args="--cloud-provider=external"
```

### Example 3: Development Cluster

```yaml
apiVersion: kcm.enopax.io/v1alpha1
kind: ClusterDeployment
metadata:
  name: dev-hosted-cluster
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp
  credential: hetzner-credential
  config:
    region: nbg1
    workersNumber: 1
    controlPlane:
      replicas: 1
    tokenRef:
      name: hcloud-token
      key: token
    sshKeyNames:
      - dev-key
    worker:
      type: cx21
      image: ubuntu-24.04
    hcloudNetwork:
      enabled: false  # Disable private networking for simplicity
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