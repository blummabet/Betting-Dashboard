"""
tests/test_card_logic_anti_drift.py — Anti-Drift-Tests für die 7 Card-Logic-Bugs
die am 09.06.2026 im ST1-Audit gefunden wurden.

Diese Tests existieren damit die Bugs NACHHALTIG nicht mehr vorkommen.
Jeder Test verweist auf den Original-Bug der ihn ausgelöst hat.
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


# ──────────────────────────────────────────────────────────────────────────
#  BUG 1: SaferAlt-Picks dürfen Engine-Downgrade nicht ignorieren
# ──────────────────────────────────────────────────────────────────────────
class TestSaferAltEngineGate(unittest.TestCase):
    """
    Original-Bug AUT-JOR ST1: SaferAlt-Pick DC X2 mit Engine -3.5pp blieb
    "Vorsichtiger Pick" obwohl Engine massiv gegen den Pick warnte.
    Fix: Engine-SKIP-Schwelle (-5pp) und CLV-Downgrade gelten auch für
    ABWÄGEN-Picks, nicht nur BET.
    """

    def test_generate_wm_picks_has_skip_threshold(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("ENGINE_SKIP_PP", src,
            "generate_wm_picks muss ENGINE_SKIP_PP-Konstante haben (für extreme Engine-Warnung)")

    def test_skip_applies_to_abwaegen_too(self):
        # Der Block "in (\"BET\", \"ABWÄGEN\")" muss existieren
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        # Engine-Block muss BET UND ABWÄGEN betrachten
        self.assertRegex(src, r'verdict.*in.*\(\s*"BET"\s*,\s*"ABWÄGEN"\s*\)',
            "Engine-Downgrade-Logik muss BET UND ABWÄGEN-Picks prüfen, nicht nur BET")

    def test_beobachten_verdict_used_for_skip(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn('"BEOBACHTEN"', src,
            "Bei massiver Engine-Warnung muss Pick auf BEOBACHTEN gesetzt werden")


# ──────────────────────────────────────────────────────────────────────────
#  BUG 2: CLV-Negativ muss Verdict beeinflussen
# ──────────────────────────────────────────────────────────────────────────
class TestClvDowngrade(unittest.TestCase):
    """
    Original-Bug CIV-ECU / GHA-PAN ST1: Picks mit klar negativem CLV
    (Markt bewegt sich gegen unseren Pick) blieben ★★★ BET ohne Warnung.
    Fix: CLV ≤ -3pp triggert ABWÄGEN-Downgrade.
    """

    def test_clv_threshold_present(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("CLV_NEG_DOWNGRADE_PP", src,
            "CLV-Downgrade-Schwelle muss als Konstante existieren")

    def test_clv_used_in_verdict_override(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        # Regex: clv_pp wird in Verdict-Logik referenziert (nicht nur als Feld zurückgegeben)
        self.assertRegex(src, r'clv_pp\s*<=\s*CLV_NEG_DOWNGRADE_PP',
            "clv_pp muss als Verdict-Override-Bedingung verwendet werden")


# ──────────────────────────────────────────────────────────────────────────
#  BUG 3: "Form schlägt Elo" nur wenn Form WIRKLICH besser
# ──────────────────────────────────────────────────────────────────────────
class TestFormBesserAlsGegner(unittest.TestCase):
    """
    Original-Bug KOR-CZE ST1: Heimsieg-Pick auf KOR mit Argument
    "Südkorea 3 Siege in 5 — Form schlägt Elo" — aber CZE hatte 4 Siege.
    Argument invertiert. Fix: Vergleiche home.wins vs away.wins.
    """

    def test_form_argument_compares_both_teams(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        # Hard-Check: "Form schlägt Elo" darf NICHT in Template-Literal-Output sein
        # (Vorkommen in // Kommentar-Zeilen ist OK — Anti-Drift-Doku).
        # Strip alle //-Kommentare zeilenweise, dann Test.
        cleaned = "\n".join(
            re.sub(r'//.*$', '', line)
            for line in src.split("\n")
        )
        self.assertNotIn("Form schlägt Elo", cleaned,
            "'Form schlägt Elo' findet sich noch als User-Text — sollte nur als // Kommentar bleiben")

    def test_form_comparison_helper_exists(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        self.assertIn("_formWins", src,
            "_formWins-Helper muss existieren für Form-Vergleich")
        self.assertRegex(src, r'homeWins\s*>\s*awayWins',
            "Form-Argument muss home.wins > away.wins check enthalten")


# ──────────────────────────────────────────────────────────────────────────
#  BUG 4: Header "Defensiv-Schlacht" bei Klassen-Unterschied falsch
# ──────────────────────────────────────────────────────────────────────────
class TestHeaderKlassenUnterschied(unittest.TestCase):
    """
    Original-Bug ESP-CPV ST1: "🛡 Defensiv-Schlacht" Header bei 88% ESP-Sieg
    (Elo +370). Fix: bei |eloDiff| >= 250 immer "Klassen-Unterschied".
    """

    def test_lopsided_overrides_torfest_defshow(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        # Suche das isLopsided-Pattern im _deriveAngle-Bereich
        self.assertIn("isLopsided", src,
            "isLopsided-Check muss existieren um Defensiv-Schlacht/Tor-Fest bei Klassen-Unterschied zu überschreiben")
        # 06.09.2026: dieser Test suchte das ERSTE Vorkommen der Literale irgendwo in der
        # Datei — auch in einem Kommentar. Ein Kommentar, der „Tor-Fest erwartet" nur ERWAEHNT,
        # liess ihn rot werden, obwohl die Reihenfolge im Code stimmte. Der Test hielt eine
        # Byte-Position fest, nicht die Regel. Jetzt: die Regel ist, dass der Lopsided-ZWEIG
        # vor dem Torfest-RUECKGABEWERT steht — beides Code, kein Prosa-Treffer moeglich.
        idx_lopsided = src.find("const isLopsided")
        idx_torfest  = src.find("label: 'Tor-Fest erwartet'")
        self.assertGreaterEqual(idx_lopsided, 0, "const isLopsided nicht gefunden")
        self.assertGreaterEqual(idx_torfest, 0, "Torfest-Rueckgabe nicht gefunden")
        self.assertLess(idx_lopsided, idx_torfest,
            "isLopsided-Check muss VOR Tor-Fest-Check stehen (sonst greift override nicht)")


# ──────────────────────────────────────────────────────────────────────────
#  DATEN-BUG 1: Phantom-Venues (Denver/Orlando) dürfen nicht vorkommen
# ──────────────────────────────────────────────────────────────────────────
class TestNoPhantomVenues(unittest.TestCase):
    """
    Original-Bug GER-CUW / ESP-CPV ST1: "Empower Field, Denver" und
    "Camping World Stadium, Orlando" sind keine WM-2026 Host-Stadien.
    Fix: alle Venues müssen in wm_venues.json bekannt sein ODER mit
    "zu bestätigen"-Marker gekennzeichnet sein.
    """

    BLACKLIST = {
        "Empower Field, Denver",
        "Empower Field",
        "Camping World Stadium, Orlando",
        "Camping World Stadium",
    }

    def test_blacklist_not_in_any_json(self):
        for fpath in REPO.rglob("*.json"):
            # Skip irrelevant dirs
            if any(skip in str(fpath) for skip in ("actions-runner", ".git/", "node_modules")):
                continue
            # 29.06.2026: Die Blacklist ist WM-spezifisch (waren KEINE WM-2026-Host-Stadien).
            # Für MLS/Liga sind „Empower Field" (Colorado) bzw. Orlando ECHTE Venues → ausnehmen.
            if fpath.name.startswith(("mls", "liga")):
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            for bad in self.BLACKLIST:
                self.assertNotIn(bad, content,
                    f"Phantom-Venue '{bad}' gefunden in {fpath.relative_to(REPO)}")

    def test_blacklist_not_in_fetcher_py(self):
        # Vorkommen in Code-Kommentaren (// oder #) erlaubt — Anti-Drift-Doku.
        # Wir prüfen nur Vorkommen ausserhalb von Kommentar-Zeilen.
        import re
        for fpath in REPO.glob("fetch_wm_*.py"):
            content = fpath.read_text(encoding="utf-8")
            # Strip # Kommentare zeilenweise
            cleaned = "\n".join(
                re.sub(r'#.*$', '', line)
                for line in content.split("\n")
            )
            for bad in self.BLACKLIST:
                self.assertNotIn(bad, cleaned,
                    f"Phantom-Venue '{bad}' als Code-Wert in Fetcher {fpath.name}")


# ──────────────────────────────────────────────────────────────────────────
#  DATEN-BUG 2: Streak-Logik muss konsistent mit angezeigter Form sein
# ──────────────────────────────────────────────────────────────────────────
class TestStreakKonsistenz(unittest.TestCase):
    """
    Original-Bug BEL-EGY ST1: "EGY Sieg-Serie 3 in Folge" widerspricht
    angezeigter last5-Form 'L W D W L'. Ursache: _winStreak schaute auf
    last10, Card-Anzeige zeigte last5. Fix: _winStreak nur auf last5.
    """

    def test_winstreak_uses_only_last5(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        # Match die _winStreak-Funktion und prüfe dass kein last10-Fallback
        match = re.search(r'function _winStreak\(form\)\s*\{(.*?)\n\s*\}', src, re.DOTALL)
        self.assertIsNotNone(match, "_winStreak nicht gefunden")
        body = match.group(1)
        self.assertNotIn("last10", body,
            "_winStreak darf nicht auf last10 fallback'en — sonst inkonsistent mit Card-Anzeige")
        self.assertIn("last5", body, "_winStreak muss last5 nutzen")

    def test_lossstreak_uses_only_last5(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        match = re.search(r'function _lossStreak\(form\)\s*\{(.*?)\n\s*\}', src, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("last10", body, "_lossStreak darf nicht auf last10 fallbacken")


# ──────────────────────────────────────────────────────────────────────────
#  DATEN-BUG 3: H2H-Raten ab n=3 nur — keine 100%-Artefakte
# ──────────────────────────────────────────────────────────────────────────
class TestH2hMinSampleSize(unittest.TestCase):
    """
    Original-Bug MEX-ZAF ST1: "H2H 100% Unter 2.5" bei nur n=1 Spiel.
    Statistisch bedeutungslos. Fix: H2H-Raten nur ab games >= 3 anzeigen.
    """

    def test_h2h_rate_guarded_by_min_games(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        # Pragmatischer Check: jeder "h2h.over25Rate"-Block der eine User-sichtbare
        # Anzeige produziert (parts.push oder signals.push) muss einen
        # games>=3 Guard im SELBEN if-Statement enthalten.
        # Wir suchen if-Statements mit h2h.over25Rate und prüfen ob games>=3 darin steht.
        if_pattern = re.compile(
            r'if\s*\([^\)]*h2h[\?\.]over25Rate[^\)]*\)\s*\{[^\}]*?(?:parts\.push|signals\.push)',
            re.DOTALL
        )
        for match in if_pattern.finditer(src):
            block = match.group(0)
            self.assertIn("games", block,
                f"H2H-Rate-Anzeige ohne games-Guard: {block[:200]}")
            self.assertRegex(block, r'games[^\)]*\>=\s*3',
                f"H2H-Rate-Anzeige ohne games>=3-Threshold: {block[:200]}")


# ──────────────────────────────────────────────────────────────────────────
#  FRONTEND-BUG (27.06.2026): Sharp-Radar-Panels müssen dataset-bewusst sein
# ──────────────────────────────────────────────────────────────────────────
class TestSharpRadarDatasetAware(unittest.TestCase):
    """
    Original-Bug: das Bayesian-Lern-Panel im Liga-Tab zeigte WM-Gewichte
    (window.SIGNAL_WEIGHTS + WM-Signal-Liste mit Travel/Wetter), weil es nicht
    dataset-bewusst war. Fix: liga → window.LIGA_SIGNAL_WEIGHTS + liga-Signal-Liste.
    Diese Tests verhindern den Rückfall.
    """

    def setUp(self):
        self.src = (REPO / "renderer.js").read_text(encoding="utf-8")

    def test_bayesian_panel_is_dataset_aware(self):
        """13.07.2026 überarbeitet: Der Test suchte wörtlich nach 'LIGA_SIGNAL_WEIGHTS' im
        Funktionsrumpf. Die Gewichte werden jetzt über SHARP_DS_META aufgelöst (nötig, weil MLS
        EIGENE Gewichte hat und vorher still auf die WM-Gewichte zurückfiel). Der Test prüft
        deshalb die ABSICHT statt des Wortlauts: jeder Datensatz muss seine eigene Gewichts-Quelle
        haben — und kein Liga-artiger Datensatz darf auf SIGNAL_WEIGHTS (=WM) landen.
        """
        m = re.search(r'function _renderBayesianWeights\(\)\s*\{(.*?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_renderBayesianWeights nicht gefunden")
        body = m.group(1)
        self.assertIn("_sharpDataset", body,
            "_renderBayesianWeights muss den aktiven Datensatz berücksichtigen")
        self.assertNotIn("window.SIGNAL_WEIGHTS", body,
            "kein harter WM-Fallback mehr — die Quelle kommt aus SHARP_DS_META")

        # Jeder Datensatz braucht eine EIGENE Gewichts-Quelle (sonst zeigt MLS/Liga WM-Gewichte).
        meta = re.search(r'const SHARP_DS_META = \{(.*?)\n\};', self.src, re.DOTALL)
        self.assertIsNotNone(meta, "SHARP_DS_META nicht gefunden")
        block = meta.group(1)
        for ds, weights_global in (("intl", "SIGNAL_WEIGHTS"),
                                   ("liga", "LIGA_SIGNAL_WEIGHTS"),
                                   ("mls",  "MLS_SIGNAL_WEIGHTS")):
            self.assertRegex(block, rf"{ds}:.*{weights_global}",
                f"{ds} muss auf {weights_global} zeigen")
        for ds, clv in (("intl", "wm_clv_summary.json"),
                        ("liga", "liga_clv_summary.json"),
                        ("mls",  "mls_clv_summary.json")):
            self.assertIn(clv, block, f"{ds} braucht seine eigene CLV-Bilanz ({clv})")

        # Liga-Signal darf in der Signal-Liste auftauchen (kein reines WM-Set mehr)
        self.assertIn("league_pressure", body,
            "Liga-Signal-Liste (league_pressure) muss im Panel vorkommen")

    def test_liga_loader_fetches_weights(self):
        m = re.search(r'function _loadLigaSharpData\(\)\s*\{(.*?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_loadLigaSharpData nicht gefunden")
        self.assertIn("liga_signal_weights.json", m.group(1),
            "_loadLigaSharpData muss liga_signal_weights.json laden (für das Liga-Bayesian-Panel)")


# ──────────────────────────────────────────────────────────────────────────
#  Smoketest: alle Module laden noch
# ──────────────────────────────────────────────────────────────────────────
class TestModulesStillLoad(unittest.TestCase):
    def test_generate_wm_picks_loads(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gwp", REPO / "generate_wm_picks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "main"))


if __name__ == "__main__":
    unittest.main()
