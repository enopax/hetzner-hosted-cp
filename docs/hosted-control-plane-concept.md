# Hosted Control Plane with Ingress Support

## Overview

A **hosted control plane** runs the Kubernetes control plane components (API server, etcd, controllers) as pods inside the management cluster rather than on dedicated infrastructure machines. Only the worker nodes are provisioned as Hetzner Cloud VMs.

This architecture is managed by **k0smotron**, which orchestrates the control plane pods and enables workers to connect from external infrastructure.

## Architecture

```
                    Management Cluster (k0s on Hetzner)
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    │  ┌─────────────┐   ┌──────────────────┐    │
                    │  │ kmc-cluster  │   │ kmc-cluster-etcd │    │
                    │  │ (API Server) │   │   (etcd store)   │    │
                    │  │  Pod         │   │   Pod            │    │
                    │  └──────┬───────┘   └──────────────────┘    │
                    │         │                                    │
                    │  ┌──────┴───────┐                           │
                    │  │  Service     │                           │
                    │  │  (ClusterIP) │                           │
                    │  └──────┬───────┘                           │
                    │         │                                    │
                    │  ┌──────┴──────────────────────┐            │
                    │  │  HAProxy Ingress Controller  │            │
                    │  │  (SSL Passthrough)           │            │
                    │  └──────┬──────────────────────┘            │
                    │         │                                    │
                    └─────────┼────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Management LB    │
                    │  (46.225.33.0)    │
                    │  Port 443         │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────┴─────┐  ┌─────┴─────┐  ┌──────┴────┐
        │  Worker 1  │  │  Worker 2  │  │  Worker N │
        │  (Hetzner) │  │  (Hetzner) │  │  (Hetzner)│
        └────────────┘  └────────────┘  └───────────┘
           Kubelet connects to api.cluster01.enopax.io:443
           via SSL passthrough through management LB
```

## How It Works

### 1. Control Plane as Pods

k0smotron creates two StatefulSets in the management cluster:
- **`kmc-<cluster-name>`**: The k0s API server pod (runs kube-apiserver, kube-controller-manager, kube-scheduler)
- **`kmc-<cluster-name>-etcd`**: The etcd storage pod

These pods are fully managed by the management cluster's scheduler. No dedicated VMs needed.

### 2. Worker Node Connection

Worker nodes need to reach the API server and the konnectivity server. There are **three access modes**:

| Mode | How Workers Connect | Extra Cost | Complexity |
|------|-------------------|------------|------------|
| **Ingress** | Via hostnames through HAProxy ingress | None (uses existing mgmt LB) | Medium (needs DNS + ingress controller) |
| **LoadBalancer** | Via dedicated Hetzner LB per cluster | ~5 EUR/month per cluster | Low |
| **NodePort** | Via mgmt node IP + static ports | None | High (k0s doesn't expose NodePorts externally) |

### 3. Ingress Mode (Recommended)

The ingress approach uses the **existing management cluster load balancer** to route traffic to hosted control planes via hostname-based routing with SSL passthrough.

#### Traffic Flow

```
Worker Node (kubelet)
    │
    │  TLS connection to api.cluster01.enopax.io:443
    ▼
Management Cluster Load Balancer (46.225.33.0:443)
    │
    │  TCP passthrough (no TLS termination)
    ▼
HAProxy Ingress Controller (in mgmt cluster)
    │
    │  SNI-based routing: api.cluster01.enopax.io → kmc-cluster01 service
    ▼
kmc-cluster01 Pod (API Server)
```

Key: **SSL passthrough** means the ingress controller does NOT terminate TLS. It inspects the SNI (Server Name Indication) header to route traffic to the correct backend, preserving the end-to-end TLS connection between the worker's kubelet and the API server.

#### Two Endpoints Per Cluster

Each hosted cluster needs **two hostnames**:

1. **API Host** (e.g., `api.cluster01.enopax.io`) — for the Kubernetes API server (port 443)
2. **Konnectivity Host** (e.g., `konnectivity.cluster01.enopax.io`) — for kubectl exec/logs/port-forward (port 443)

Both are routed through the same load balancer and ingress controller, differentiated by hostname (SNI).

## Prerequisites for Ingress Mode

### 1. HAProxy Ingress Controller

Install on the management cluster:

```bash
helm repo add haproxytech https://haproxytech.github.io/helm-charts
helm install haproxy-ingress haproxytech/kubernetes-ingress \
  --namespace haproxy-ingress --create-namespace \
  --set controller.service.type=ClusterIP \
  --set controller.ingressClass=haproxy \
  --set controller.config.ssl-passthrough=true
```

The service type is `ClusterIP` because the management cluster's existing load balancer handles external traffic. HAProxy only handles internal routing.

Alternatively, if you want HAProxy to manage its own LB:

```bash
helm install haproxy-ingress haproxytech/kubernetes-ingress \
  --namespace haproxy-ingress --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.service.annotations."load-balancer\.hetzner\.cloud/location"=nbg1 \
  --set controller.ingressClass=haproxy \
  --set controller.config.ssl-passthrough=true
```

### 2. DNS Configuration

Option A: **Wildcard DNS** (recommended for multiple clusters)
```
*.k0s.enopax.io  →  46.225.33.0   (management LB IP)
```

Then each cluster uses:
- `api.cluster01.k0s.enopax.io`
- `konnectivity.cluster01.k0s.enopax.io`

Option B: **Individual DNS records** (simpler for few clusters)
```
api.cluster01.enopax.io            →  46.225.33.0
konnectivity.cluster01.enopax.io   →  46.225.33.0
```

### 3. Load Balancer Port 443

The management cluster load balancer must forward port **443** to the HAProxy ingress controller's NodePort or directly to the controller pods.

## Chart Configuration

### Ingress Mode

```yaml
# ClusterDeployment config section
controlPlane:
  replicas: 1
  service:
    type: ClusterIP                              # ClusterIP for ingress routing
  ingress:
    apiHost: api.cluster01.k0s.enopax.io         # DNS must resolve to mgmt LB
    konnectivityHost: konnectivity.cluster01.k0s.enopax.io
```

### LoadBalancer Mode (for comparison)

```yaml
controlPlane:
  replicas: 1
  service:
    type: LoadBalancer                           # Hetzner CCM creates a new LB
```

### What the Chart Generates

When ingress is configured, the chart creates:

**K0smotronControlPlane** with ingress block:
```yaml
spec:
  ingress:
    enabled: true
    className: haproxy
    annotations:
      haproxy.org/ssl-passthrough: "true"
    apiHost: api.cluster01.k0s.enopax.io
    konnectivityHost: konnectivity.cluster01.k0s.enopax.io
  service:
    type: ClusterIP
```

**HetznerCluster** with ingress endpoint:
```yaml
spec:
  controlPlaneEndpoint:
    host: "api.cluster01.k0s.enopax.io"
    port: 443
```

k0smotron then automatically creates two Kubernetes Ingress resources:
1. `kmc-<name>-api` — routes `api.cluster01.k0s.enopax.io` to port 30443
2. `kmc-<name>-konnectivity` — routes `konnectivity.cluster01.k0s.enopax.io` to port 30132

## Full ClusterDeployment Example (Ingress Mode)

```yaml
apiVersion: k0rdent.mirantis.com/v1beta1
kind: ClusterDeployment
metadata:
  name: cluster01
  namespace: kcm-system
spec:
  template: hetzner-hosted-cp-1-2-0
  credential: hcloud-cluster-provisioning
  config:
    workersNumber: 2

    controlPlane:
      replicas: 1
      service:
        type: ClusterIP
      ingress:
        apiHost: api.cluster01.k0s.enopax.io
        konnectivityHost: konnectivity.cluster01.k0s.enopax.io

    region: nbg1
    sshKeyNames:
      - "felix@chump"
    tokenRef:
      name: hcloud-cluster-provisioning-token
      key: HCLOUD_TOKEN

    hcloudNetwork:
      enabled: true
      cidrBlock: "10.0.0.0/16"
      subnetCidrBlock: "10.0.0.0/24"
      networkZone: "eu-central"

    worker:
      image: ubuntu-24.04
      type: cpx22

    k0s:
      version: v1.34.3+k0s.0
      network:
        provider: custom
```

## Cost Comparison

| Setup | Monthly Cost (per child cluster) |
|-------|--------------------------------|
| **Ingress mode** | 0 EUR (shared mgmt LB) |
| **LoadBalancer mode** | ~5 EUR (dedicated LB11 per cluster) |
| **Standalone CP** (3 control plane VMs) | ~15-30 EUR (3x cpx11/cpx22) |

The ingress approach is the most cost-effective for running multiple hosted clusters, as all share a single management cluster load balancer.

## Requirements

- **k0s version**: v1.34.1+k0s.0 or later (ingress support was added in this release)
- **Ingress controller**: HAProxy, NGINX, or Traefik with SSL passthrough capability
- **DNS**: Wildcard or individual records pointing to management cluster LB
- **Management LB**: Port 443 forwarded to ingress controller

## Limitations

- **DNS required**: Hostnames must resolve to the management LB before deploying
- **SSL passthrough**: The ingress controller must support SSL passthrough (no TLS termination)
- **Slight latency**: One additional network hop through the ingress controller
- **Shared capacity**: All hosted clusters share the management cluster's resources

## References

- [k0smotron Ingress Support Documentation](https://docs.k0smotron.io/stable/ingress-support/)
- [k0rdent Hosted Control Plane Overview](https://docs.k0rdent.io/head/admin/hosted-control-plane/)
- [HAProxy Ingress Controller](https://haproxytech.github.io/helm-charts/)
