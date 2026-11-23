# Hetzner Hosted Control Plane Chart Tests

Property-based tests for the hetzner-hosted-cp Helm chart. **Sie laufen in der
CI** (`.github/workflows/ci.yaml`, Schritt „Property tests") - vorher lagen sie
hier und wurden nie aufgerufen; sie scheiterten dabei, weil sie das Chart mit
den Werten des **standalone**-Charts rendern wollten. Siehe enopax/enopax#38.

Alles rendert ueber `tests/property/render.py` mit `test-values.yaml` als
Grundlage - derselben Datei, mit der auch `helm lint` laeuft. Eine Fassung, mit
der das Chart nicht rendert, faellt damit beim ersten Test auf.

| Datei | Was sie festhaelt |
|---|---|
| `test_helper_functions.py` | Die Objektnamen kommen aus `clusterName`, nicht aus `Release.Name` |
| `test_rendered_values.py` | Was aus den Werten wird: `worker.replicas` → MachineDeployment, `worker.serverType` → MachineTemplate, der core-Pool nur mit Autoskalierung, `workersNumber` wirkt nicht, und das Schema weist eine falsche k0s-Schreibweise ab |

## Prerequisites

- Python 3.8 or newer
- Helm 3.x installed and available in PATH
- pip for installing Python dependencies

## Setup

Install test dependencies:

```bash
pip install -r requirements.txt
```

## Running Tests

Run all property tests:

```bash
pytest property/ -v
```

Run specific test file:

```bash
pytest property/test_helper_functions.py -v
```

Run with increased verbosity and show hypothesis examples:

```bash
pytest property/test_helper_functions.py -v --hypothesis-show-statistics
```

## Test Structure

- `property/` - Property-based tests that verify universal correctness properties
  - `test_helper_functions.py` - Tests for Helm template helper functions (Property 3)

## Property-Based Testing

These tests use [Hypothesis](https://hypothesis.readthedocs.io/) to generate random valid inputs and verify that correctness properties hold across all inputs. Each test runs 100 iterations by default with randomly generated values.

### Property 3: Helper Function Name Generation

Validates that:
- All helper functions generate consistent resource names based on Release.Name
- Changing Release.Name changes all generated resource names accordingly
- Names follow Kubernetes naming conventions (DNS-1123 subdomain format)

**Validates Requirements**: 12.6

## Troubleshooting

If tests fail with "helm: command not found":
- Ensure Helm is installed and available in your PATH
- Verify with: `helm version`

If tests fail with import errors:
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Verify Python version: `python --version` (should be 3.8+)
