"""28.08.2026 — Lucas: „push von poly kamen. in trades / aber auf der seite ist nichts".

Der letzte automatische Pages-Deploy lief um 11:55; die ausgelieferte Seite war am Abend
rund acht Stunden alt. Telegram kam durch, weil der Runner direkt sendet — die Website
braucht zusaetzlich den Deploy, und genau dort war der Bruch.

Ursache, gemessen: das Pages-Artefakt war nach dem Aufraeum-Schritt noch **198 MB**, das
alle 15 Minuten. Am 01.07.2026 gab es dieses Problem schon einmal („Deploy failt die ganze
Zeit" — Uploads dauerten 10-18 Min und wurden vom naechsten Trigger ueberholt, sichtbar als
„Error: Deployment cancelled"). Damals flog `daily-tiktok` raus. Danach entstanden
`mls_daily-tiktok` (35,7 MB) und `liga_daily-tiktok` (12,3 MB) — und die Namensliste im
Workflow kannte sie nicht. Keine einzige HTML- oder JS-Datei fasst diese PNGs an.

Eine Namensliste veraltet still. Deshalb hier eine Zahl statt einer Liste: was nach dem
Aufraeumen uebrig bleibt, hat ein Budget.
"""
import os
import re
import sys
import subprocess
import collections
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import pages_ballast as BALLAST

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(REPO, ".github", "workflows", "deploy-pages.yml")

# Budget fuer das Pages-Artefakt. 198 MB waren zu viel; nach dem Fix sind es ~150 MB.
# 170 laesst Luft fuers Wachsen der Daten, schlaegt aber an, bevor der Deploy wieder kippt.
#
# 02.09.2026 (Lucas-Audit): gemessen 169,3 MB — 99,6% des Budgets. Der Deckel hat also nur noch
# knapp gehalten, ohne dass es jemandem aufgefallen waere; ein Test, der bei 99,6% gruen ist,
# warnt nicht mehr, er beruhigt. Deshalb fliegen jetzt zusaetzlich die groessten Wurzel-JSONs
# raus, die keine HTML/JS-Datei fetcht (Regel in scripts/pages_ballast.py, ~21 MB), und das
# Budget geht runter, damit der gewonnene Platz nicht sofort wieder stillschweigend zuwaechst.
#
# 160 statt 150: gemessen bleiben 148,3 MB, ein Budget von 150 haette 1,7 MB Luft gelassen und
# waere in wenigen Tagen an normalem Datenwachstum gescheitert. Ein Test, der bei Routine-
# Wachstum rot wird, wird weggeklickt statt gelesen — dann warnt er beim echten Problem nicht mehr.
#
# 07.09.2026 (Lucas: „woher kommt das Limit?"): der Deckel ist UNSERER, nicht GitHubs. GitHub
# erlaubt 1 GB veroeffentlichte Seite — was hier wirklich beisst, ist die 10-Minuten-Grenze fuer
# einen Deploy. Bei 198 MB dauerte der Upload 10-18 Min, lief also darueber, und der naechste
# Trigger ueberholte ihn („Error: Deployment cancelled"). Das Budget misst Upload-DAUER mit
# Reserve, nicht Speicherplatz.
#
# 140 statt 160 (07.09.2026): die Ballast-Regel hatte ein Leck — ihr Sicherheitsnetz fuer
# dynamisch gebaute Namen liess jedes generische Endstueck (`ledger.json`, `_results.json`)
# gelten, und damit fuhren 34,1 MB mit, die keine Zeile Frontend-Code anfasst (allen voran
# `stake_bet_ledger.json`, 15,4 MB). Endstuecke zaehlen jetzt nur noch an einer echten
# Verkettungsgrenze; gemessen bleiben 126,3 MB. Das Budget geht mit runter — sonst waechst der
# gewonnene Platz stillschweigend wieder zu, und genau das ist am 02.09. schon einmal passiert.
#
# ⚠️ Was hier NICHT mehr rauszuholen ist, ohne eine Entscheidung: 49 MB `matches/` (1.018
# Einzel-JSONs a ~150 KB, plus 120 Event-Seiten) und ~76 MB referenzierte Wurzel-JSONs. Beide
# werden von der Seite gebraucht — die JSONs allerdings nur als RUECKFALL, denn geholt wird
# primaer von raw.githubusercontent.com/main. Wer den Rueckfall aufgibt, spart auf einen Schlag
# den groessten Teil davon; das ist eine Produktentscheidung (Verhalten bei raw-Ausfall), keine
# Aufraeumarbeit.
ARTEFAKT_BUDGET_MB = 140


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, cwd=REPO).stdout
    return [f.decode("utf-8", "replace") for f in out.split(b"\0") if f]


def _cleanup_muster():
    """Die Ordner-Muster, die der Ballast-Schritt loescht — direkt aus dem Workflow gelesen."""
    with open(WF, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"rm -rf (.+?)\|\| true", src, re.S)
    assert m, "Ballast-Schritt (rm -rf …) nicht gefunden"
    return [t for t in m.group(1).replace("\\\n", " ").split() if t not in ("||", "true")]


def _geloeschte_dateien():
    """Die EINZELNEN Dateien, die der Ballast-Schritt loescht.

    Seit 02.09.2026 keine Namensliste im Workflow mehr, sondern eine Regel in
    scripts/pages_ballast.py — genau weil eine Liste am 28.08. still veraltet ist und den Deploy
    gekippt hat. Der Test faehrt DIESELBE Regel, nicht eine nachgebaute.
    """
    return BALLAST.unbenutzte_wurzel_jsons(_tracked(), REPO)


def _passt(top, muster):
    import fnmatch
    return any(fnmatch.fnmatch(top, mu) for mu in muster)


def _groessen_nach_cleanup():
    muster = _cleanup_muster()
    gr = collections.Counter()
    for f in _tracked():
        top = f.split("/")[0] if "/" in f else "(Wurzel)"
        if "/" in f and _passt(top, muster):
            continue
        try:
            gr[top] += os.path.getsize(os.path.join(REPO, f))
        except OSError:
            pass
    # Einzeln geloeschte Wurzel-Dateien (rm -f) abziehen.
    for f in _geloeschte_dateien():
        try:
            gr["(Wurzel)"] -= os.path.getsize(os.path.join(REPO, f))
        except OSError:
            pass
    return gr


def _ohne_kommentare(text: str, name: str) -> str:
    """Kommentare raus, Code drin — vorsichtig genug, um keine echte Referenz zu schlucken.

    Nur GANZE Kommentarzeilen (`//` als erstes Zeichen der Zeile) und Bloecke werden entfernt.
    Ein `//` mitten in einer Zeile bleibt stehen: das ist meistens `https://` in einem String,
    und eine Zeile wegzuwerfen, die auch Code enthaelt, waere genau das Loch, das dieser Test
    zustopfen soll.
    """
    if name.endswith(".html"):
        return re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return "\n".join("" if z.lstrip().startswith("//") else z for z in text.splitlines())


class TestArtefaktBudget:
    def test_artefakt_bleibt_unter_dem_budget(self):
        gr = _groessen_nach_cleanup()
        mb = sum(gr.values()) / 1e6
        groesste = ", ".join(f"{k} {v/1e6:.0f}MB" for k, v in gr.most_common(4))
        assert mb <= ARTEFAKT_BUDGET_MB, (
            f"Pages-Artefakt {mb:.0f} MB > {ARTEFAKT_BUDGET_MB} MB — der Deploy wird langsam "
            f"und vom naechsten Trigger ueberholt. Groesste Posten: {groesste}")

    def test_tiktok_bilder_landen_nicht_im_artefakt(self):
        """Der konkrete Rueckfall vom 28.08.: zwei Varianten, die die Liste nicht kannte."""
        gr = _groessen_nach_cleanup()
        drin = [k for k in gr if "daily-tiktok" in k]
        assert not drin, f"TikTok-Bilder im Artefakt: {drin}"

    def test_cleanup_nutzt_ein_glob_statt_einer_namensliste(self):
        """Damit die naechste `<datensatz>_daily-tiktok` automatisch mitfliegt."""
        assert any("daily-tiktok" in mu and "*" in mu for mu in _cleanup_muster()), \
            "Ballast-Schritt zaehlt TikTok-Ordner einzeln auf — die naechste Variante wird vergessen"


class TestNichtsNoetigesWirdGeloescht:
    """Gegenprobe: der Aufraeum-Schritt darf nichts wegwerfen, was die Seite fetcht."""

    @pytest.mark.parametrize("noetig", ["matches", "icons", "(Wurzel)"])
    def test_wichtige_pfade_ueberleben(self, noetig):
        assert noetig in _groessen_nach_cleanup(), f"{noetig} fehlt im Artefakt"

    def test_geloeschte_einzeldateien_werden_von_keiner_seite_gefetcht(self):
        """Gegenprobe zur Ballast-Regel: nichts Geloeschtes darf irgendwo referenziert sein.

        Faellt jemandem spaeter ein, eine dieser Dateien doch zu fetchen, faellt dieser Test —
        und nicht die Live-Seite."""
        dateien = _geloeschte_dateien()
        assert dateien, "Die Ballast-Regel findet nichts mehr — dann waechst das Artefakt wieder"
        quellen = [f for f in _tracked()
                   if f.endswith((".js", ".html")) and not f.startswith("tests/")]
        text = ""
        for f in quellen:
            try:
                with open(os.path.join(REPO, f), encoding="utf-8", errors="replace") as fh:
                    text += fh.read()
            except OSError:
                pass
        referenziert = [d for d in dateien if d in text]
        assert not referenziert, (
            f"Der Deploy loescht Dateien, die das Frontend laedt: {referenziert}")

    def test_dynamisch_gebaute_namen_ueberleben(self):
        """`poly-wallets.js` baut `ds + '_poly_prices.json'` zusammen — der volle Name steht nirgends.
        Die Regel sucht deshalb auch Namens-Endstuecke ab einem Unterstrich."""
        raus = set(_geloeschte_dateien())
        for f in ("mls_poly_prices.json", "liga_poly_wallets.json", "wm_poly_prices.json"):
            if os.path.exists(os.path.join(REPO, f)):
                assert f not in raus, f"{f} wird geloescht, obwohl der Name dynamisch gebaut wird"

    def test_die_regel_steht_im_workflow_nicht_als_namensliste(self):
        """Der Rueckfall, den es zu verhindern gilt: wieder eine Handliste im Workflow."""
        with open(WF, encoding="utf-8") as f:
            src = f.read()
        assert "scripts/pages_ballast.py" in src, "Der Workflow ruft die Ballast-Regel nicht auf"
        assert not re.search(r"rm -f .*\.json", src), \
            "Im Workflow steht wieder eine Namensliste — genau die veraltet still"

    def test_geloeschte_ordner_werden_von_keiner_seite_gefetcht(self):
        """Was rausfliegt, darf in keiner HTML/JS-Datei referenziert sein."""
        muster = [m for m in _cleanup_muster() if not m.startswith("*")]
        quellen = [f for f in _tracked()
                   if f.endswith((".js", ".html")) and not f.startswith("tests/")]
        text = ""
        for f in quellen:
            try:
                with open(os.path.join(REPO, f), encoding="utf-8", errors="replace") as fh:
                    text += _ohne_kommentare(fh.read(), f)
            except OSError:
                pass
        # Nur ECHTE Referenzen zaehlen: der Pfad am Anfang eines Strings (fetch/src/href).
        # Eine blosse Erwaehnung im Kommentar („Signale liegen in sharp_signals/") ist keine —
        # 🔴 12.09.2026: genau daran ist der Test aufgeschlagen. Ein Kommentar in poly-wallets.js
        # nennt `tests/test_zeitstempel_iso.py` in Backticks, und Backtick + Pfad + "/" ist fuer
        # das Muster nicht von einem Template-String zu unterscheiden. Der Test sagte also
        # „das Frontend laedt tests/" ueber eine Zeile, die gar kein Code ist. Kommentare fliegen
        # jetzt vorher raus — das war die Absicht des Tests von Anfang an.
        referenziert = []
        for m in muster:
            d = m.rstrip("/")
            if re.search(r"""["'`](?:\.\./)?%s/""" % re.escape(d), text):
                referenziert.append(m)
        assert not referenziert, f"Der Deploy loescht Pfade, die das Frontend laedt: {referenziert}"


class TestBallastRegelLeck:
    """07.09.2026 — das Sicherheitsnetz gegen dynamische Namen war zu grob.

    Es liess JEDES Namens-Endstueck ab einem Unterstrich gelten. `ledger.json` ist aber kein
    seltenes Endstueck, sondern ein haeufiges: sobald irgendwo `liga_signal_ledger.json` steht,
    blieb auch `stake_bet_ledger.json` im Deploy — 15,4 MB, die keine Zeile Frontend-Code je
    anfasst. Gemessen fuhren so 34,1 MB als blinde Passagiere mit.
    """

    def test_generisches_endstueck_haelt_eine_unreferenzierte_datei_nicht_am_leben(self):
        text = "fetch('liga_signal_ledger.json'); fetch('mls_results.json')"
        assert not BALLAST._wird_erwaehnt("stake_bet_ledger.json", text), \
            "ein fremdes Ledger im Code haelt unser Ledger im Deploy"
        assert not BALLAST._wird_erwaehnt("betfair_draw_results.json", text)

    def test_dynamisch_gebauter_name_ueberlebt_weiterhin(self):
        """Der Fall, wegen dem es das Netz gibt — in allen drei Schreibweisen."""
        for code in ("fetch(ds + '_poly_prices.json')",
                     'fetch(ds + "_poly_prices.json")',
                     "fetch(`${ds}_poly_prices.json`)"):
            assert BALLAST._wird_erwaehnt("mls_poly_prices.json", code), code

    def test_der_volle_name_zaehlt_ueberall(self):
        """Wer den ganzen Namen schreibt, meint ihn — auch mitten in einem Kommentar."""
        assert BALLAST._wird_erwaehnt("liga-data.json", "// siehe liga-data.json")

    def test_stake_ledger_faehrt_nicht_mehr_mit(self):
        """Der konkrete Fall, 15,4 MB. Kein Frontend holt ihn; der Erzeuger liest ihn lokal."""
        raus = set(_geloeschte_dateien())
        if os.path.exists(os.path.join(REPO, "stake_bet_ledger.json")):
            assert "stake_bet_ledger.json" in raus
