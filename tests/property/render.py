"""
Rendern, wie es wirklich gerendert wird.

Jeder Test hier geht durch `helm template` mit `test-values.yaml` als Grundlage
- derselben Datei, die auch `helm lint` und die CI benutzen. Damit kann die
Datei nicht unbemerkt veralten: eine Fassung, mit der das Chart nicht rendert,
faellt beim ersten Test auf.

Vorher stand in den Tests ein eigener Satz `--set`-Werte im Vokabular des
**standalone**-Charts (`workersNumber`, `tokenRef`, `worker.type`). Damit
rendert dieses Chart nicht, und die Tests scheiterten - was niemand sah, weil
die CI sie nicht aufrief. Siehe enopax/enopax#38.
"""

import subprocess
from pathlib import Path
from typing import Optional

import yaml

CHART = Path(__file__).resolve().parents[2]
BASE_VALUES = CHART / 'test-values.yaml'


def render(
    release_name: str = 'test',
    sets: Optional[dict] = None,
    strings: Optional[dict] = None,
    values_file: Optional[Path] = None,
):
    """
    Rendert das Chart und gibt die Objekte als Liste von dicts zurueck.

    `sets` sind `--set`-Werte ueber der Grundlage, `strings` dieselben als
    `--set-string`. Der Unterschied ist nicht Geschmack: `--set clusterName=0`
    macht Helm daraus eine **Zahl**, und das Schema weist sie ab. Wer einen
    Namen setzt, setzt ihn als Zeichenkette.

    Ein Fehler von Helm wird weitergegeben, damit ein Test auch eine *Absage*
    pruefen kann.
    """
    args = ['helm', 'template', release_name, str(CHART), '-f', str(values_file or BASE_VALUES)]
    for key, value in (sets or {}).items():
        args += ['--set', f'{key}={value}']
    for key, value in (strings or {}).items():
        args += ['--set-string', f'{key}={value}']

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise HelmError(result.stderr.strip())

    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


class HelmError(RuntimeError):
    """Helm hat abgelehnt - Schema oder Vorlage."""


def of_kind(docs, kind: str):
    return [d for d in docs if d.get('kind') == kind]


def one_of_kind(docs, kind: str):
    found = of_kind(docs, kind)
    assert len(found) == 1, f'expected exactly one {kind}, got {len(found)}'
    return found[0]
