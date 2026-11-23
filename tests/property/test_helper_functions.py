"""
Woraus die Namen der Objekte entstehen.

Aus `clusterName` - nicht aus `Release.Name`. Das ist die Eigenschaft, die
dieses Chart wirklich hat, und sie ist wichtig: der Name gehoert dem Cluster,
und zwei Helm-Releases desselben Clusters treffen dieselben Objekte.

**Vorher stand hier das Gegenteil.** Die Datei prueffte, dass jeder
`Release.Name` eigene Objektnamen ergibt, und erwartete Namen wie
`<release>-worker-mt`. Keine dieser Annahmen trifft auf dieses Chart zu: es
rendert `{{ .Values.clusterName }}-mt`. Gerendert wurde ausserdem mit den
Werten des **standalone**-Charts (`workersNumber`, `tokenRef`, `worker.type`),
womit dieses Chart gar nicht rendert - die Tests scheiterten also, und niemand
sah es, weil die CI sie nicht aufrief. Siehe enopax/enopax#38.
"""

from hypothesis import given, settings, strategies as st

from render import one_of_kind, render

# DNS-1123 und hoechstens 40 Zeichen: so lang darf ein Clustername bei uns
# sein (`provider-cluster` weist laengere ab, k0rdent sonst im Webhook).
cluster_names = st.text(
    alphabet='abcdefghijklmnopqrstuvwxyz0123456789-',
    min_size=1,
    max_size=40,
).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and '--' not in x)

# Jedes Beispiel ist ein `helm template`-Aufruf; hundert davon kosten Minuten
# und pruefen nichts, was zwanzig nicht pruefen.
EXAMPLES = 20


@given(cluster_name=cluster_names)
@settings(max_examples=EXAMPLES, deadline=None)
def test_every_object_is_named_after_the_cluster(cluster_name):
    docs = render(strings={'clusterName': cluster_name})

    assert one_of_kind(docs, 'Cluster')['metadata']['name'] == cluster_name
    assert one_of_kind(docs, 'K0smotronControlPlane')['metadata']['name'] == f'{cluster_name}-cp'
    assert one_of_kind(docs, 'HCloudMachineTemplate')['metadata']['name'] == f'{cluster_name}-mt'
    assert one_of_kind(docs, 'MachineDeployment')['metadata']['name'] == f'{cluster_name}-md'
    assert (
        one_of_kind(docs, 'K0sWorkerConfigTemplate')['metadata']['name']
        == f'{cluster_name}-machine-config'
    )


@given(release_name=cluster_names)
@settings(max_examples=EXAMPLES, deadline=None)
def test_the_release_name_changes_nothing(release_name):
    """
    Zwei Releases, ein Cluster, dieselben Objekte.

    Der Name des Releases taucht in keinem Objektnamen auf. Wer das aendert,
    aendert damit, welche Objekte ein zweites `helm upgrade` trifft - und das
    ist bei einem laufenden Cluster keine Kleinigkeit.
    """
    docs = render(release_name=release_name, strings={'clusterName': 'fixed-name'})
    names = {d['metadata']['name'] for d in docs if 'metadata' in d}

    assert names == {
        'fixed-name',
        'fixed-name-cp',
        'fixed-name-mt',
        'fixed-name-md',
        'fixed-name-machine-config',
    }
