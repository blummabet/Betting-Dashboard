"""🔴 21.09.2026 (Lucas: „Stake / Pini und poly reparieren").

Drei rote Punkte auf der Statusseite. Nachgemessen war KEINER davon das, was dastand:

  „🎰 Stake Radar: seit 336 h kein Lauf mehr verzeichnet"
      → `stake_highroller.json` trug `asof` von vor 12 Minuten und `status: ok`. Der Sammler
        läuft alle 15 Minuten — seit dem 03.09. als Schritt in betfair.yml. `stake-radar.yml`
        hat seither BEWUSST keinen Cron; der Wächter verlangte eine Taktung, die dieser
        Workflow nie versprochen hat.
        Fehlerklasse: ein Wächter, der die Taktung eines Workflows misst, der bewusst keine hat.

  „⚡ Poly-Live-Scan: Letzter Live-Scan vor 2.1 h (Takt: 15 Min) — der Job startet nicht"
      → Gemessen an den Commits auf `poly_money_broad_live.json`: 57–66 Läufe je Tag, also
        ~60 von 96. Der Job startet sehr wohl. Seine Health-Datei kam nur 6–8 mal am Tag durch:
        sie wurde in einem eigenen commit+push OHNE Retry geschrieben, verlor das Push-Rennen
        gegen die anderen Committer und wurde beim nächsten `actions/checkout --force`
        verworfen. `scripts/ci_sichern.sh` hat den 3-fach-Retry seit dem 19.09. — er wurde hier
        nur nie benutzt.
        Fehlerklasse: ein Buch, das seine eigene Zustellung misst statt des Ereignisses.

  „Pinnacle-Odds 22.9 h alt"
      → Derselbe Vorfall wie der tote API-Schlüssel: letzter erfolgreicher Odds-Schreibvorgang
        20.09. 14:01 UTC, genau als der Schlüssel ablief.

Zwei der drei roten Punkte waren Fehlalarme, und sie haben zusammen Wochen an Aufmerksamkeit
gekostet. Eine Fläche, deren rote Punkte man nicht glauben kann, macht die übrige Arbeit
wertlos — und der teure Teil ist nicht der einzelne Fehlalarm, sondern dass man danach auch
dem echten nicht mehr glaubt.
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import wm_data_integrity as W

NOW = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)


class _Ctx:
    now = NOW


class TestKeineTaktungOhneVersprechen(unittest.TestCase):
    def test_stake_radar_hat_keinen_cron(self):
        self.assertFalse(W._hat_cron("stake-radar"),
                         "stake-radar.yml ist seit dem 03.09. bewusst dispatch-only")

    def test_die_workflows_mit_cron_werden_weiter_gemessen(self):
        for slug in ("poly-live-scan", "betfair"):
            self.assertTrue(W._hat_cron(slug), slug)

    def test_ein_unbekannter_slug_wird_weiter_gemeldet(self):
        """Die sichere Richtung. Nur ein GEFUNDENER Workflow ohne Cron entschaerft den Befund —
        sonst wuerde jeder Lesefehler einen echten Ausfall stillstellen, also fehlende
        Information als harmloser Default, und zwar in der teuren Richtung.
        (tests/test_run_health_guard.py hat genau das aufgedeckt: dort liegt die Health-Datei
        in einem tmp-Verzeichnis, und mein erster Entwurf schwieg deshalb.)"""
        self.assertTrue(W._hat_cron("gibt-es-nicht-xyz"))

    def test_ein_alter_dispatch_workflow_meldet_nicht_mehr(self):
        """Der Vorfall: 336 h ohne Lauf bei einem Workflow, der gar nicht laufen soll."""
        alt = (NOW - timedelta(hours=336)).isoformat()
        d = {"slug": "stake-radar", "workflow": "🎰 Stake Radar",
             "runs": [{"ts": alt, "ok": True, "failures": []}]}
        with mock.patch.object(W, "_run_health_dateien", return_value=[_Datei(d)]):
            c = W.check_run_health(_Ctx())
        self.assertEqual(c["failures"], [], "ein Workflow ohne Cron schuldet keine Taktung")

    def test_ein_alter_cron_workflow_meldet_sehr_wohl(self):
        alt = (NOW - timedelta(hours=336)).isoformat()
        d = {"slug": "poly-live-scan", "workflow": "⚡ Poly Live-Scan",
             "runs": [{"ts": alt, "ok": True, "failures": []}]}
        with mock.patch.object(W, "_run_health_dateien", return_value=[_Datei(d)]):
            c = W.check_run_health(_Ctx())
        self.assertIn("kein Lauf mehr verzeichnet", " ".join(c["failures"]))

    def test_gescheiterte_steps_melden_unabhaengig_vom_cron(self):
        """Der Cron-Test darf nur die TAKTUNG entschaerfen, nicht die Fehler."""
        d = {"slug": "stake-radar", "workflow": "🎰 Stake Radar",
             "runs": [{"ts": NOW.isoformat(), "ok": False,
                       "failures": [{"step": "Sammeln", "conclusion": "failure"}]}]}
        with mock.patch.object(W, "_run_health_dateien", return_value=[_Datei(d)]):
            c = W.check_run_health(_Ctx())
        self.assertIn("Step 'Sammeln'", " ".join(c["failures"]))


class TestStakeWirdAmArtefaktGemessen(unittest.TestCase):
    def _c(self, **kw):
        d = {"asof": NOW.isoformat(), "status": "ok"}
        d.update(kw)
        with mock.patch.object(W, "_lazy", side_effect=lambda n: d if "stake" in n else None):
            return W.check_stake_sammelt(_Ctx())

    def test_frische_daten_sind_still(self):
        self.assertTrue(self._c()["ok"])

    def test_der_echte_stand_von_heute_ist_still(self):
        """12 Minuten alt, status ok — genau der Stand, waehrend die Seite 336 h meldete."""
        self.assertTrue(self._c(asof=(NOW - timedelta(minutes=12)).isoformat())["ok"])

    def test_ein_stehender_sammler_faellt_auf(self):
        c = self._c(asof=(NOW - timedelta(hours=5)).isoformat())
        self.assertFalse(c["ok"])
        self.assertIn("5.0 h alt", " ".join(c["failures"]))

    def test_ein_fehlstatus_ist_kein_leerer_tag(self):
        """Stake sitzt hinter Cloudflare: ein 403 saehe sonst aus wie „keine grossen Wetten"."""
        c = self._c(status="fehler", notiz="HTTP 403")
        self.assertFalse(c["ok"])
        self.assertIn("gescheiterter Abruf", " ".join(c["failures"]))

    def test_ohne_zeitstempel_behauptet_er_nichts_gutes(self):
        c = self._c(asof=None)
        self.assertFalse(c["ok"])
        self.assertIn("ohne Zeitstempel", " ".join(c["failures"]))

    def test_ohne_datei_behauptet_er_gar_nichts(self):
        with mock.patch.object(W, "_lazy", side_effect=lambda n: None):
            c = W.check_stake_sammelt(_Ctx())
        self.assertTrue(c["ok"])
        self.assertIn("sagt dieser Waechter nichts", c["note"])

    def test_er_ist_registriert(self):
        self.assertIn("check_stake_sammelt", [f.__name__ for f in W.INTEGRITY_CHECKS])


class TestDieHealthDateiWirdGesichertStattGepusht(unittest.TestCase):
    """Die Zustellung war das Problem, nicht das Ereignis."""

    def test_beide_workflows_nutzen_den_retry(self):
        for name in ("poly-live-scan", "stake-radar"):
            t = (BASE / ".github/workflows" / f"{name}.yml").read_text(encoding="utf-8")
            self.assertIn("ci_sichern.sh", t, name)

    def test_kein_eigener_push_der_health_datei_mehr(self):
        for name in ("poly-live-scan", "stake-radar"):
            t = (BASE / ".github/workflows" / f"{name}.yml").read_text(encoding="utf-8")
            self.assertNotIn("Push der Gesundheitsdatei fehlgeschlagen", t,
                             f"{name}: der Push ohne Retry ist zurueck")

    def test_das_hilfsskript_hat_wirklich_einen_retry(self):
        """Sonst zeigt der Test oben nur auf einen Namen."""
        t = (BASE / "scripts/ci_sichern.sh").read_text(encoding="utf-8")
        self.assertIn("for versuch in 1 2 3", t)


class _Datei:
    """Minimaler Ersatz fuer ein Path-Objekt mit .read_text()/.stem/.name."""

    def __init__(self, daten):
        self._t = json.dumps(daten)
        self.stem = daten.get("slug", "x")
        self.name = self.stem + ".json"

    def read_text(self, encoding=None):
        return self._t


if __name__ == "__main__":
    unittest.main()
