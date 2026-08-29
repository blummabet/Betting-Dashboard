"""28.08.2026 — aus dem ersten Lauf mit dem Abdeckungs-Alarm.

    🚨 1 Fixture(s) mit Anpfiff <48h ohne Polymarket-Markt:
       – Lille vs Paris Saint Germain  [79-85]  2026-08-28T18:45:00+00:00
    ✓ Lille OSC vs Paris Saint-Germain FC  [79-114]  vol=$367,924

Zwei Zeilen im selben Log, dasselbe Spiel, zwei verschiedene IDs. `Paris Saint-Germain FC`
loeste auf **114 = Paris FC** auf: gegen `Paris Saint Germain` (85) scheitert der Token-Match
am Bindestrich, gegen `Paris FC` trifft er. GENAU EIN Treffer — also greift die
Mehrdeutigkeits-Bremse nicht, und der Resolver liefert selbstbewusst das falsche Team. Das ist
die gefaehrlichere Sorte als der Barcelona-Fall: kein „uebersprungen", sondern eine stille,
falsche Zuordnung.

Der Schaden ging weiter als die Preisdatei. Der Kickoff-Patch schreibt Poly-Datum und -Anpfiff
in den Spielplan, geschluesselt mit `home-away` — also stempelte er den Anpfiff von Lille–PSG
(28.08., 18:45) auf **Lille–Paris FC, 17. Spieltag**. Danach standen zwei Lille-Spiele am selben
Tag in liga-data.json, und die Gegenprobe, die genau solche Fehler finden soll, bestaetigte den
falschen Treffer mit den eigenen beschaedigten Daten. Ein Fehler, der sich selbst plausibel
macht. Gefunden wurden genau zwei kaputte Fixtures — beide PSG/Paris-FC.

Drei Schichten dagegen, eine pro Testklasse.
"""
import os
import sys
import json
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_MODULE = ("fetch_wm_poly_prices", "cocobet_dataset", "cocobet_config")


def _purge():
    for m in list(sys.modules):
        if m.startswith(_MODULE):
            del sys.modules[m]


@pytest.fixture(scope="module")
def F():
    vorher = {k: os.environ.get(k) for k in ("COCOBET_PROFILE", "COCOBET_DATASET")}
    os.environ["COCOBET_PROFILE"] = "liga_default"
    os.environ["COCOBET_DATASET"] = "liga"
    _purge()
    import fetch_wm_poly_prices as mod
    yield mod
    for k, v in vorher.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _purge()


class TestPariserNamen:
    """Schicht 1: exakte Aliase — der Fehler kann gar nicht mehr entstehen."""

    def test_psg_ist_nicht_paris_fc(self, F):
        assert F.resolve_team_id("Paris Saint-Germain FC") == "85"

    def test_paris_fc_bleibt_paris_fc(self, F):
        assert F.resolve_team_id("Paris FC") == "114"

    def test_die_beiden_sind_verschieden(self, F):
        assert F.resolve_team_id("Paris Saint-Germain FC") != F.resolve_team_id("Paris FC")

    def test_ids_zeigen_auf_die_richtigen_klubs(self):
        with open(os.path.join(REPO, "liga-data.json"), encoding="utf-8") as f:
            d = json.load(f)
        namen = {}
        for g in (d.get("groups") or {}).values():
            for t in (g.get("teams") or []):
                namen[str(t.get("id"))] = t.get("name")
        assert "Saint Germain" in (namen.get("85") or "")
        assert namen.get("114") == "Paris FC"


class TestGegenprobeSpielplan:
    """Schicht 2: eine Paarung, die es an dem Tag nicht gibt, ist falsch aufgeloest."""

    PAARE = {("79", "85", "2026-08-28"), ("81", "114", "2026-09-06")}
    TAGE = {"2026-08-28", "2026-09-06"}

    def _p(self, F, h, a, d):
        return F.paarung_im_spielplan(h, a, d, paare=self.PAARE, tage=self.TAGE)

    def test_echte_paarung_passt(self, F):
        assert self._p(F, "79", "85", "2026-08-28") is True

    def test_gespiegelte_paarung_passt(self, F):
        """Polymarket dreht Heim/Auswaerts — das ist kein Fehler."""
        assert self._p(F, "85", "79", "2026-08-28") is True

    def test_falsches_team_faellt_auf(self, F):
        """Genau der PSG-Fall: Lille gegen Paris FC gibt es an dem Tag nicht."""
        assert self._p(F, "79", "114", "2026-08-28") is False

    def test_exaktes_datum_schlaegt_nachbartage(self, F):
        """Der erste Anlauf erlaubte ±1 Tag als Toleranz — und winkte damit genau den
        Fehler durch, den er finden sollte. Gibt es fuer den Tag einen Spielplan, zaehlt nur er."""
        paare = {("79", "114", "2026-08-27")}
        assert F.paarung_im_spielplan("79", "114", "2026-08-28",
                                      paare=paare, tage={"2026-08-28", "2026-08-27"}) is False

    def test_nachbartag_hilft_wo_wir_nichts_wissen(self, F):
        """Zeitzonen-Fall: fuer den Tag selbst haben wir keinen Spielplan."""
        paare = {("79", "85", "2026-08-27")}
        assert F.paarung_im_spielplan("79", "85", "2026-08-28",
                                      paare=paare, tage={"2026-08-27"}) is True

    def test_ohne_spielplan_kein_urteil(self, F):
        """Fehlende Information ist keine Erlaubnis — aber auch kein Schuldspruch."""
        assert self._p(F, "79", "85", "2030-01-01") is None
        assert F.paarung_im_spielplan("79", "85", "2026-08-28", paare=set(), tage=set()) is None

    def test_kaputtes_datum_kein_urteil(self, F):
        assert self._p(F, "79", "85", "kaputt") is None
        assert self._p(F, "79", "85", "") is None


class TestKickoffPatchDriftet:
    """Schicht 3: Poly darf einen Anpfiff praezisieren, aber kein Spiel verschieben."""

    def test_kleine_korrektur_erlaubt(self, F):
        """12.06.2026: Seed-Daten lagen ~5 Tage daneben, die Korrektur muss durchgehen."""
        assert F._tage_auseinander("2026-06-19", "2026-06-24") == 5
        assert 5 <= F.KO_PATCH_MAX_DRIFT_D

    def test_sprung_ueber_spieltage_wird_erkannt(self, F):
        """Lille–Paris FC (17. Spieltag) wurde auf den 28.08. gestempelt."""
        assert F._tage_auseinander("2026-12-20", "2026-08-28") > F.KO_PATCH_MAX_DRIFT_D

    def test_grenze_ist_gesetzt_und_eng_genug(self, F):
        assert 7 <= F.KO_PATCH_MAX_DRIFT_D <= 21

    def test_unlesbares_datum_gibt_none(self, F):
        assert F._tage_auseinander("kaputt", "2026-08-28") is None
        assert F._tage_auseinander("2026-08-28", None) is None

    def test_guard_haengt_im_patch_pfad(self):
        """Ein Guard, der nicht aufgerufen wird, ist keiner."""
        with open(os.path.join(REPO, "fetch_wm_poly_prices.py"), encoding="utf-8") as f:
            src = f.read()
        assert "KO_PATCH_MAX_DRIFT_D" in src.split("ko_patched = 0")[1][:2000], \
            "Drift-Guard steht nicht im Kickoff-Patch-Block"
        assert "ko_verweigert" in src, "verweigerte Patches werden nicht gemeldet"


class TestSpielplanIstHeil:
    """Regression auf die Daten selbst: ein Team kann an einem Tag nur EIN Spiel haben.

    Am 28.08.2026 waren es zwei kaputte Fixtures (Lille zweimal am 28.08., Monaco zweimal am
    04.09.) — beide durch den PSG-Fehler entstanden. Dieser Test faellt, solange sie im
    Datensatz stehen, und schuetzt danach vor der Wiederkehr.
    """

    # 29.08.2026: geheilt. Der naechste volle Daten-Lauf hat die beiden Fixtures neu geseedet —
    # Lille–Paris FC steht wieder am 23.01.2027 (17. Spieltag), Paris FC–Monaco am 31.10.2026.
    # Der Test stand einen Tag als xfail hier und ist jetzt ein echter Waechter: der Drift-Guard
    # im Kickoff-Patch soll verhindern, dass so etwas ueberhaupt wieder entsteht — dieser Test
    # merkt es, falls er es doch nicht tut.
    def test_kein_team_spielt_zweimal_am_selben_tag(self):
        import collections
        with open(os.path.join(REPO, "liga-data.json"), encoding="utf-8") as f:
            d = json.load(f)
        pro_tag = collections.Counter()
        for g in (d.get("groups") or {}).values():
            for fx in (g.get("fixtures") or []):
                tag = str(fx.get("date"))[:10]
                if len(tag) != 10:
                    continue
                pro_tag[(tag, str(fx.get("home")))] += 1
                pro_tag[(tag, str(fx.get("away")))] += 1
        doppelt = {k: v for k, v in pro_tag.items() if v > 1}
        assert not doppelt, f"Team(s) mit zwei Spielen am selben Tag: {sorted(doppelt)[:6]}"
