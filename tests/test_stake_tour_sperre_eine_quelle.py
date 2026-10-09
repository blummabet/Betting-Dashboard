"""08.10.2026 (Lucas: „ATP und WTA können wir da draus nehmen" — gemeint: die Stake-Kacheln der
Uebersicht, nachdem „Ben Shelton - Daniel Altmaier · ATP Shanghai · $76.4K" oben stand).

Die Tour-Sperre galt seit 04.10. nur im Push (`stake_burst_push._TOUR_RX`, hart im Code). Jetzt
lebt das Muster EINMAL beim Sammler und steht im Artefakt; Push und Uebersicht lesen es.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stake_highroller_fetch as F  # noqa: E402
import stake_burst_push as S  # noqa: E402


def test_push_nimmt_das_muster_des_sammlers():
    assert S._TOUR_RX.pattern == F.GESPERRT_LIGEN_MUSTER


def test_muster_trifft_atp_wta_aber_nicht_itf():
    for liga in ("ATP Shanghai, China Men Singles", "WTA Wuhan, China Women Singles"):
        assert S._TOUR_RX.search(liga), liga
    for liga in ("ITF W15 Trelew", "Challenger Shanghai", "Primera Division"):
        assert not S._TOUR_RX.search(liga), liga


def test_artefakt_traegt_das_muster():
    src = (Path(F.__file__)).read_text(encoding="utf-8")
    assert '"gesperrtLigenMuster": GESPERRT_LIGEN_MUSTER' in src
