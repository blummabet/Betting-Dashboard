"""🔴 27.10.2026: betfair.yml lief zwei Tage gar nicht. Beim Abschalten des Live-Scans (25.10.)
stand `if:` zweimal im selben Schritt. PyYAML nimmt stumm den letzten Wert — alle Tests waren
grün —, GitHub lehnt die Datei ab („workflow file issue") und startet den Workflow nie.
Dieser Test liest jede Workflow-Datei mit einem Loader, der doppelte Schlüssel ablehnt."""
from pathlib import Path

import pytest
import yaml

WF = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


class _Streng(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    keys = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in keys:
            raise yaml.constructor.ConstructorError(None, None, f"doppelter Schlüssel {key!r}", k.start_mark)
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_Streng.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@pytest.mark.parametrize("pfad", WF, ids=lambda p: p.name)
def test_keine_doppelten_schluessel(pfad):
    yaml.load(pfad.read_text(encoding="utf-8"), Loader=_Streng)


def test_gegentest_erkennt_doppeltes_if():
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load("steps:\n  - name: x\n    if: ${{ false }}\n    if: always()\n", Loader=_Streng)
