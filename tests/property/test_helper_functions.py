"""
Property-based tests for Helm chart helper functions.

Feature: hetzner-hosted-cp-chart
Property 3: Helper function name generation
Validates: Requirements 12.6
"""

import subprocess
import re
from hypothesis import given, strategies as st, settings
from pathlib import Path


# Strategy for generating valid Release.Name values
# Kubernetes names must be DNS-1123 subdomain: lowercase alphanumeric, '-', max 63 chars
# Must start and end with alphanumeric, no consecutive hyphens
release_name_strategy = st.text(
    alphabet='abcdefghijklmnopqrstuvwxyz0123456789-',
    min_size=1,
    max_size=63
).filter(
    lambda x: (
        x and 
        x[0].isalnum() and 
        x[-1].isalnum() and 
        '--' not in x and
        not x.startswith('-') and
        not x.endswith('-')
    )
)


def render_chart_with_release_name(release_name: str) -> dict:
    """
    Render the Helm chart with a specific release name and return parsed resources.
    
    Args:
        release_name: The Helm release name to use
        
    Returns:
        Dictionary mapping resource kinds to their names
    """
    chart_path = Path(__file__).parent.parent.parent
    
    # Minimal valid values to render the chart
    values = [
        '--set', 'workersNumber=2',
        '--set', 'region=fsn1',
        '--set', 'tokenRef.name=test-token',
        '--set', 'worker.image=ubuntu-24.04',
        '--set', 'worker.type=cpx22',
        '--set', 'k0s.version=v1.34.2+k0s.0'
    ]
    
    # Run helm template
    result = subprocess.run(
        ['helm', 'template', release_name, str(chart_path)] + values,
        capture_output=True,
        text=True,
        check=True
    )
    
    # Parse YAML documents using regex to avoid YAML type conversion issues
    # Extract kind and metadata.name from each document
    resources = {}
    
    # Split by document separator
    docs = result.stdout.split('---')
    
    for doc in docs:
        if not doc.strip():
            continue
            
        # Extract kind
        kind_match = re.search(r'^kind:\s+(\S+)', doc, re.MULTILINE)
        if not kind_match:
            continue
        kind = kind_match.group(1)
        
        # Extract metadata.name (handle both quoted and unquoted values)
        # Look for "  name: <value>" under metadata section
        name_match = re.search(r'^metadata:\s*\n\s+name:\s+["\']?([^"\'\n]+)["\']?', doc, re.MULTILINE)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        
        resources[kind] = name
    
    return resources


@given(release_name=release_name_strategy)
@settings(max_examples=100, deadline=None)
def test_helper_functions_generate_consistent_names(release_name):
    """
    Property 3: Helper function name generation
    
    For any Release.Name value, all helper functions should generate consistent 
    resource names based on that Release.Name, and changing the Release.Name 
    should change all generated resource names accordingly.
    
    Validates: Requirements 12.6
    """
    resources = render_chart_with_release_name(release_name)
    
    # Truncate and trim suffix as per cluster.name helper
    expected_base = release_name[:63].rstrip('-')
    
    # Verify cluster.name helper
    assert 'Cluster' in resources, "Cluster resource should be generated"
    cluster_name = resources['Cluster']
    assert cluster_name == expected_base, \
        f"Cluster name should be {expected_base}, got {cluster_name}"
    
    # Verify k0smotroncontrolplane.name helper
    assert 'K0smotronControlPlane' in resources, "K0smotronControlPlane should be generated"
    cp_name = resources['K0smotronControlPlane']
    assert cp_name == f"{expected_base}-cp", \
        f"K0smotronControlPlane name should be {expected_base}-cp, got {cp_name}"
    
    # Verify hcloudmachinetemplate.worker.name helper
    assert 'HCloudMachineTemplate' in resources, "HCloudMachineTemplate should be generated"
    worker_mt_name = resources['HCloudMachineTemplate']
    assert worker_mt_name == f"{expected_base}-worker-mt", \
        f"HCloudMachineTemplate name should be {expected_base}-worker-mt, got {worker_mt_name}"
    
    # Verify k0sworkerconfigtemplate.name helper
    assert 'K0sWorkerConfigTemplate' in resources, "K0sWorkerConfigTemplate should be generated"
    worker_config_name = resources['K0sWorkerConfigTemplate']
    assert worker_config_name == f"{expected_base}-machine-config", \
        f"K0sWorkerConfigTemplate name should be {expected_base}-machine-config, got {worker_config_name}"
    
    # Verify machinedeployment.name helper
    assert 'MachineDeployment' in resources, "MachineDeployment should be generated"
    md_name = resources['MachineDeployment']
    assert md_name == f"{expected_base}-md", \
        f"MachineDeployment name should be {expected_base}-md, got {md_name}"


@given(name1=release_name_strategy, name2=release_name_strategy)
@settings(max_examples=100, deadline=None)
def test_different_release_names_produce_different_resource_names(name1, name2):
    """
    Property 3 (variant): Changing Release.Name changes all resource names
    
    For any two different Release.Name values, the generated resource names 
    should be different (unless the names are identical after truncation).
    
    Validates: Requirements 12.6
    """
    # Skip if names are the same or become the same after truncation
    base1 = name1[:63].rstrip('-')
    base2 = name2[:63].rstrip('-')
    
    if base1 == base2:
        return  # Skip this test case
    
    resources1 = render_chart_with_release_name(name1)
    resources2 = render_chart_with_release_name(name2)
    
    # All resource names should be different
    assert resources1['Cluster'] != resources2['Cluster'], \
        "Different release names should produce different Cluster names"
    assert resources1['K0smotronControlPlane'] != resources2['K0smotronControlPlane'], \
        "Different release names should produce different K0smotronControlPlane names"
    assert resources1['HCloudMachineTemplate'] != resources2['HCloudMachineTemplate'], \
        "Different release names should produce different HCloudMachineTemplate names"
    assert resources1['K0sWorkerConfigTemplate'] != resources2['K0sWorkerConfigTemplate'], \
        "Different release names should produce different K0sWorkerConfigTemplate names"
    assert resources1['MachineDeployment'] != resources2['MachineDeployment'], \
        "Different release names should produce different MachineDeployment names"
