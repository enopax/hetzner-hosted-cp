"""
Was aus den Werten wirklich wird.

Diese Datei prueft nicht, *dass* das Chart rendert, sondern **was** dabei
herauskommt. Der Unterschied ist der Grund, warum enopax/enopax#38 so lange
unbemerkt blieb: `provider-cluster` schrieb die Arbeiterzahl nach
`workersNumber`, der hosted-Chart liest `worker.replicas`, und weil niemand das
Ergebnis ansah, fiel es erst am Kunden auf.
"""

import pytest
from hypothesis import given, settings, strategies as st

from render import HelmError, one_of_kind, of_kind, render


def worker_md(docs):
    """Der skalierbare Pool. Ohne Autoskalierung ist er der einzige."""
    return one_of_kind(docs, 'MachineDeployment')


@pytest.mark.parametrize('replicas', [0, 1, 2, 7])
def test_worker_replicas_reach_the_machinedeployment(replicas):
    docs = render(sets={'worker.replicas': replicas})
    assert worker_md(docs)['spec']['replicas'] == replicas


def test_worker_server_type_reaches_the_machine_template():
    docs = render(strings={'worker.serverType': 'cpx42'})
    template = one_of_kind(docs, 'HCloudMachineTemplate')
    assert template['spec']['template']['spec']['type'] == 'cpx42'


def test_workers_number_changes_nothing():
    """
    Die Falle aus enopax/enopax#38.

    `workersNumber` ist der Schluessel des **standalone**-Charts. Hier ist er
    ein Fremdwort: `values.schema.json` setzt kein `additionalProperties:
    false`, die Kubernetes-API nimmt ihn an, und kein Template liest ihn. Ein
    Skalieren darueber erreicht keine Maschine.

    Dieser Test haelt das fest, damit es jemand merkt, falls das Chart den
    Schluessel eines Tages doch liest - oder zurueckweist.
    """
    docs = render(sets={'workersNumber': 9, 'worker.replicas': 2})
    assert worker_md(docs)['spec']['replicas'] == 2


def test_the_core_pool_exists_only_with_autoscaling():
    """
    Der statische `core`-Pool steht vollstaendig hinter
    `{{ if .Values.autoscaling.enabled }}` - MachineDeployment,
    MachineTemplate und WorkerConfigTemplate.

    Deshalb hat ein PaaS-Cluster ohne Autoskalierung genau `worker.replicas`
    Knoten und nicht einen mehr. Die Gegenannahme hat enopax/enopax#35
    verursacht: `core.replicas: 1` stand im Objekt, und zwei Server liefen.
    """
    without = render(sets={'autoscaling.enabled': 'false', 'core.replicas': 1})
    assert len(of_kind(without, 'MachineDeployment')) == 1
    assert all('core' not in d['metadata']['name'] for d in of_kind(without, 'MachineDeployment'))

    with_scaling = render(sets={'autoscaling.enabled': 'true', 'core.replicas': 1})
    pools = {d['metadata']['name']: d['spec']['replicas'] for d in of_kind(with_scaling, 'MachineDeployment')}
    assert len(pools) == 2
    assert any(name.endswith('-core-md') for name in pools)


def test_ingress_hosts_reach_the_control_plane():
    docs = render(
        sets={'ingress.enabled': 'true'},
        strings={
            'ingress.apiHost': 'api.c.example.test',
            'ingress.konnectivityHost': 'k.c.example.test',
        },
    )
    cp = one_of_kind(docs, 'K0smotronControlPlane')
    assert cp['spec']['ingress']['apiHost'] == 'api.c.example.test'
    assert cp['spec']['ingress']['konnectivityHost'] == 'k.c.example.test'
    # Cilium im Kind muss dieselbe API erreichen, sonst findet kein Pod sie.
    cilium = next(
        c for c in cp['spec']['k0sConfig']['spec']['extensions']['helm']['charts']
        if c['name'] == 'cilium'
    )
    assert 'k8sServiceHost: api.c.example.test' in cilium['values']


def test_without_ingress_the_control_plane_has_no_k0sconfig():
    """
    So ist es heute - und es ist vermutlich unbeabsichtigt.

    Das `{{- if and .Values.ingress.enabled ... }}` in
    `templates/k0smotroncontrolplane.yaml` umschliesst nicht nur den
    Ingress-Teil, sondern auch `k0sConfig` bis zum Dateiende: Netz, CNI, CCM
    und CSI. Mit `ingress.enabled: false` - der Vorgabe des Charts - entsteht
    also eine Steuerungsebene ohne Netzkonfiguration.

    Festgehalten, nicht gebilligt: wer die Bedingung richtet, sieht diesen Test
    rot werden und soll ihn dann aendern.
    """
    docs = render(sets={'ingress.enabled': 'false'})
    cp = one_of_kind(docs, 'K0smotronControlPlane')
    assert 'ingress' not in cp['spec']
    assert 'k0sConfig' not in cp['spec']


def test_the_schema_refuses_a_version_that_is_not_k0s_notation():
    """
    `1.30.4` ist keine k0s-Version. Die Vorlage baut daraus eine
    Download-URL, die es nicht gibt - und das faellt sonst erst auf, wenn die
    Maschine schon laeuft und bezahlt wird.
    """
    with pytest.raises(HelmError) as refused:
        render(strings={'k0s.version': '1.30.4'})
    assert 'k0s' in str(refused.value)


def test_a_cluster_name_is_required():
    with pytest.raises(HelmError) as refused:
        render(strings={'clusterName': ''})
    assert 'clusterName' in str(refused.value)


# Wenige Beispiele mit Absicht: jedes ist ein `helm template`-Aufruf.
@given(replicas=st.integers(min_value=0, max_value=20))
@settings(max_examples=8, deadline=None)
def test_any_worker_count_lands_unchanged(replicas):
    docs = render(sets={'worker.replicas': replicas})
    assert worker_md(docs)['spec']['replicas'] == replicas


def control_plane(docs):
    """Die hosted Steuerungsebene."""
    return one_of_kind(docs, 'K0smotronControlPlane')


def test_etcd_image_reaches_the_control_plane():
    """
    Das etcd-Bild steht am Objekt, nicht in der Vorgabe der CRD.

    Das ist der Kern von k0rdent/kcm#3047: die CRD hat einen Vorgabewert, und
    der wandert mit k0smotron - unter 2.0.4 `v3.5.13`, ab k0rdent 1.12
    `v3.7.1`. Weil die Vorgabe beim Schreiben eingesetzt wird, bekaeme ein
    bestehender Cluster beim naechsten Schreiben 3.7.1, und etcd kann nicht
    zwei Minor-Fassungen auf einmal. Steht die Fassung im gerenderten Objekt,
    kann keine neue Vorgabe sie verschieben.

    Gerendert wird die **v1beta1**-Form (`spec.etcd.image`); gelesen wird das
    Objekt als v1beta2, wo dasselbe Feld unter `spec.storage.etcd.image`
    liegt. Den Weg macht die Konvertierung - am laufenden `dev-box1`
    nachgesehen.
    """
    docs = render(strings={'etcd.image': 'ghcr.io/enopax/etcd:v3.5.36'})
    assert control_plane(docs)['spec']['etcd']['image'] == 'ghcr.io/enopax/etcd:v3.5.36'


def test_etcd_image_is_never_left_empty():
    """
    Eine leere Angabe ist schlimmer als keine: sie rendert ein Feld, das die
    API verwirft, und dann greift wieder die Vorgabe - genau die, vor der das
    Festnageln schuetzen soll.
    """
    with pytest.raises(HelmError):
        render(strings={'etcd.image': ''})


def test_etcd_pvcs_are_kept_by_default():
    """
    `autoDeletePVCs` wirkt wirklich, trotz des Formwechsels zwischen v1beta1
    und v1beta2. Dass unser Wert ankommt, ist am laufenden Cluster
    nachgesehen: `spec.storage.etcd.autoDeletePVCs: true`.
    """
    assert control_plane(render())['spec']['etcd']['autoDeletePVCs'] is True
