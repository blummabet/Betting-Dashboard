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
import subprocess
import collections
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(REPO, ".github", "workflows", "deploy-pages.yml")

# Budget fuer das Pages-Artefakt. 198 MB waren zu viel; nach dem Fix sind es ~150 MB.
# 170 laesst Luft fuers Wachsen der Daten, schlaegt aber an, bevor der Deploy wieder kippt.
#
# 02.09.2026 (Lucas-Audit): gemessen 169,3 MB — 99,6% des Budgets. Der Deckel hat also nur noch
# knapp gehalten, ohne dass es jemandem aufgefallen waere; ein Test, der bei 99,6% gruen ist,
# warnt nicht mehr, er beruhigt. Deshalb fliegen jetzt zusaetzlich die groessten Wurzel-JSONs
# raus, die keine HTML/JS-Datei fetcht (~24 MB), und das Budget geht auf 150 runter, damit der
# gewonnene Platz nicht sofort wieder stillschweigend zuwaechst.
ARTEFAKT_BUDGET_MB = 150


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
    """Die EINZELNEN Dateien, die der Ballast-Schritt loescht (rm -f, seit 02.09.2026)."""
    with open(WF, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"rm -f (.+?)\|\| true", src, re.S)
    if not m:
        return []
    return [t for t in m.group(1).replace("\\\n", " ").split() if t not in ("||", "true")]


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
        """02.09.2026: dieselbe Gegenprobe fuer die per `rm -f` entfernten Wurzel-JSONs.

        Die Dateinamen stehen im Frontend ausnahmslos als Literale (keine dynamisch gebauten
        Namen), also findet eine Textsuche sie zuverlaessig. Taucht einer wieder auf, weil jemand
        die Datei spaeter doch fetcht, faellt dieser Test — und nicht die Live-Seite."""
        dateien = _geloeschte_dateien()
        assert dateien, "Der rm -f-Schritt ist verschwunden — dann waechst das Artefakt wieder"
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

    def test_geloeschte_ordner_werden_von_keiner_seite_gefetcht(self):
        """Was rausfliegt, darf in keiner HTML/JS-Datei referenziert sein."""
        muster = [m for m in _cleanup_muster() if not m.startswith("*")]
        quellen = [f for f in _tracked()
                   if f.endswith((".js", ".html")) and not f.startswith("tests/")]
        text = ""
        for f in quellen:
            try:
                with open(os.path.join(REPO, f), encoding="utf-8", errors="replace") as fh:
                    text += fh.read()
            except OSError:
                pass
        # Nur ECHTE Referenzen zaehlen: der Pfad am Anfang eines Strings (fetch/src/href).
        # Eine blosse Erwaehnung im Kommentar („Signale liegen in sharp_signals/") ist keine.
        referenziert = []
        for m in muster:
            d = m.rstrip("/")
            if re.search(r"""["'`](?:\.\./)?%s/""" % re.escape(d), text):
                referenziert.append(m)
        assert not referenziert, f"Der Deploy loescht Pfade, die das Frontend laedt: {referenziert}"
