# Hetzner Hosted Control Plane Chart Tests

This directory contains property-based tests for the hetzner-hosted-cp Helm chart.

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
