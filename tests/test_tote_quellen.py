#!/usr/bin/env python3
"""
tests/test_tote_quellen.py — 15.09.2026: der Waechter gegen tote Quellen.

🔴 Anlass sind VIER Fehler desselben Tages, die alle dieselbe Form hatten:

    $22 Phantom-Exposure   Juni-Wetten galten als offen      (Feld, das niemand schreibt)
    BIG nie abgerechnet    Nachschlag las nur das Close-File (Quelle zu eng)
    Whale-Rangliste        sortierte nach Vermoegen          (Regel am 02.09. bewegt, Kopie nicht)
    Heartbeat              zeigte Zahlen der Juli-WM         (`PLACED_FILE = wm_auto_bets_placed.json`)

Die gemeinsame Form: **eine Flaeche liest eine Quelle, die weitergezogen ist — und die tote
Quelle ist LESBAR, also wirft nichts, also merkt es niemand.** Ein Absturz haette Lucas in
Minuten erreicht. Eine Datei vom 19.07., die sich brav parsen laesst, erreichte ihn nach acht
Wochen, weil er zufaellig eine Telegram-Karte einfuegte.

Das Entdeckungsverfahren war also Lucas. Das ist der eigentliche Mangel, und dieser Test ersetzt
ihn durch eine Regel:

    Ein Modul, das in einem Workflow mit AKTIVEM Zeitplan laeuft, darf keine Datensatz-Datei
    hartkodiert lesen, die seit Tagen tot ist, waehrend ihr Geschwister frisch danebenliegt.

Bewusst eine REGEL statt einer Namensliste — eine Liste vergisst genau die Datei, die neu ist
(dieselbe Lehre wie beim Pages-Ballast am 02.09.). Und bewusst am ALTER gemessen statt am Stil:
`wm_`-Dateien hartzukodieren ist voellig in Ordnung, solange die WM laeuft. Falsch wird es erst,
wenn sie es nicht mehr tut.
"""
import ast
import os
import subprocess
import re
import sys
import glob
import time
import functools
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ab so vielen Tagen gilt eine Datensatz-Datei als tot …
TOT_AB_TAGEN = 7.0
# … und ein Geschwister bis hierher als frisch. Dazwischen liegt bewusst eine Luecke: eine Datei,
# die seit drei Tagen haengt, ist ein anderes Problem (Pipeline steht) und hat seinen eigenen
# Waechter in poly_data_integrity.py.
FRISCH_BIS_TAGEN = 2.0

PRAEFIXE = ("wm_", "liga_", "mls_", "wm-", "liga-", "mls-")
QUELLE = re.compile(r"""["']((?:wm|liga|mls)[_-][A-Za-z0-9_\-]*\.json)["']""")
# Ein auskommentierter Zeitplan ist KEIN Zeitplan — fetch-wm-data.yml traegt seinen Cron seit
# dem Turnierende hinter `#`, und sein Modul darf ruhig WM-Dateien lesen.
AKTIVER_CRON = re.compile(r"^\s+-\s*cron:", re.M)

# Dated exceptions. Leer ist der gute Zustand; jeder Eintrag braucht Datum UND Begruendung.
AUSNAHMEN: dict = {}


@functools.lru_cache(maxsize=256)
def nur_code(src: str) -> str:
    """Quelltext OHNE Kommentare und Docstrings. REIN.

    🔴 Diese Funktion gibt es, weil der Waechter im ersten Anlauf genau den Fehler machte, gegen
    den er schuetzen soll: `poly_heartbeat.py` enthaelt das Wort `cocobet_dataset` — in einem
    KOMMENTAR, der erklaert, warum das Modul es NICHT benutzt. Die Regel las den Kommentar wie
    Code, erklaerte das Modul fuer datensatz-bewusst und haette den echten Fehler vom 15.09.
    durchgewunken. Ein Waechter, der Prosa fuer Verhalten haelt, ist keiner.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            koerper = getattr(node, "body", None)
            if (koerper and isinstance(koerper[0], ast.Expr)
                    and isinstance(koerper[0].value, ast.Constant)
                    and isinstance(koerper[0].value.value, str)):
                koerper.pop(0)
    try:
        return ast.unparse(tree)
    except Exception:
        return src


@functools.lru_cache(maxsize=1)
def aktive_module() -> tuple:
    """Module, die in einem Workflow mit aktivem Zeitplan wirklich laufen. Abgeleitet, nicht gelistet."""
    raus = set()
    for wf in glob.glob(os.path.join(REPO, ".github", "workflows", "*.yml")):
        with open(wf, encoding="utf-8", errors="ignore") as f:
            t = f.read()
        if not AKTIVER_CRON.search(t):
            continue
        for m in re.finditer(r"([A-Za-z0-9_]+)\.py", t):
            p = os.path.join(REPO, m.group(1) + ".py")
            if os.path.isfile(p):
                raus.add(m.group(1) + ".py")
    return tuple(sorted(raus))


_ALTER_CACHE = {}


def alter_tage(datei, jetzt=None):
    """Alter einer Repo-Datei in Tagen. None = gibt es nicht.

    🔴 19.09.2026: hier stand nur `os.path.getmtime`. Die mtime ist aber keine Eigenschaft der
    DATEN, sondern des Checkouts: jedes `git checkout`, `stash pop` oder Rebase schreibt die
    Datei neu und macht sie damit „frisch", ohne dass sich ein Byte geaendert haette. Genau so
    stand `wm_auto_bets_placed.json` — inhaltlich seit dem 12.07. unveraendert — ploetzlich mit
    zwoelf Minuten Alter da und riss die Gegenprobe des Waechters.

    Fuer eine getrackte Datei zaehlt deshalb der letzte COMMIT, der sie angefasst hat. Nur fuer
    ungetrackte faellt es auf die mtime zurueck — dort gibt es nichts Besseres."""
    p = os.path.join(REPO, datei)
    if not os.path.exists(p):
        return None
    if datei not in _ALTER_CACHE:
        ts = None
        try:
            out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", datei],
                                 cwd=REPO, capture_output=True, text=True, timeout=20).stdout.strip()
            ts = float(out) if out else None
        except (OSError, ValueError, subprocess.SubprocessError):
            ts = None
        if ts is None:
            try:
                ts = os.path.getmtime(p)
            except OSError:
                ts = None
        _ALTER_CACHE[datei] = ts
    ts = _ALTER_CACHE[datei]
    if ts is None:
        return None
    return ((jetzt or time.time()) - ts) / 86400.0


def geschwister(datei) -> list:
    """Dieselbe Datei in den anderen Datensaetzen ('wm_x.json' -> ['liga_x.json', 'mls_x.json'])."""
    for p in PRAEFIXE:
        if datei.startswith(p):
            rest = datei[len(p):]
            trenner = p[-1]
            return [q + trenner + rest for q in ("wm", "liga", "mls")
                    if q + trenner != p and os.path.isfile(os.path.join(REPO, q + trenner + rest))]
    return []


def liest_alle_varianten(src, datei) -> bool:
    """Liest das Modul ALLE Datensatz-Varianten dieser Datei? Dann ist es nicht blind.

    betfair_alerts.py macht genau das mit den Serien-Dateien — es fuehrt liga/mls/wm zusammen.
    Das ist kein toter Zweig, sondern ein bewusster Pool, und darf nicht angemahnt werden."""
    gs = geschwister(datei)
    return bool(gs) and all(g in src for g in gs)


def datensatz_bewusst(src) -> bool:
    """Modul waehlt seine Dateien ueber die geteilten Helfer statt sie festzunageln."""
    return ("cocobet_dataset" in src or "DATENSATZ_PRAEFIXE" in src
            or "D.file(" in src or "PREIS_DATENSAETZE" in src)


@functools.lru_cache(maxsize=1)
def tote_quellen(jetzt=None) -> tuple:
    """[(Modul, Datei, Alter in Tagen, frische Geschwister)] — der eigentliche Befund."""
    jetzt = jetzt or time.time()
    raus = []
    for mod in aktive_module():
        if mod in AUSNAHMEN:
            continue
        with open(os.path.join(REPO, mod), encoding="utf-8", errors="ignore") as f:
            src = nur_code(f.read())          # Kommentare sind kein Verhalten, s. nur_code
        if datensatz_bewusst(src):
            continue
        for datei in sorted({m.group(1) for m in QUELLE.finditer(src)}):
            a = alter_tage(datei, jetzt)
            if a is None or a <= TOT_AB_TAGEN:
                continue
            if liest_alle_varianten(src, datei):
                continue
            frisch = [g for g in geschwister(datei)
                      if (alter_tage(g, jetzt) or 99) < FRISCH_BIS_TAGEN]
            if frisch:
                raus.append((mod, datei, a, tuple(frisch)))
    return tuple(raus)


class TestKeineTotenQuellen:
    def test_kein_aktives_modul_liest_eine_tote_quelle(self):
        funde = tote_quellen()
        assert not funde, "Tote Quellen:\n" + "\n".join(
            "  %s liest %s (%.0f Tage alt) — frisch waere: %s" % (m, d, a, ", ".join(g))
            for m, d, a, g in funde)

    def test_die_regel_faengt_die_heartbeat_falle(self):
        """⭐ Die Gegenprobe: findet die Regel ueberhaupt etwas, oder ist sie nur gruen?

        Hier steht der echte Fehler vom 15.09. als Quelltext-Schnipsel. Faellt dieser Test,
        ist der Waechter blind — und ein blinder Waechter ist schlimmer als keiner, weil man
        sich auf ihn verlaesst."""
        falle = 'PLACED_FILE = BASE / "wm_auto_bets_placed.json"'
        assert not datensatz_bewusst(falle)
        assert not liest_alle_varianten(falle, "wm_auto_bets_placed.json")
        a = alter_tage("wm_auto_bets_placed.json")
        if a is None:
            pytest.skip("wm_auto_bets_placed.json gibt es nicht mehr")
        assert a > TOT_AB_TAGEN, "die WM-Wettdatei ist wieder frisch — dann taugt sie nicht als Probe"
        geschw = geschwister("wm_auto_bets_placed.json")
        assert geschw, "ohne Geschwister kann die Regel hier nichts finden"
        # 🔴 23.09.2026: hier stand `alter_tage(g)` gegen die echte Uhr — und die Gegenprobe
        # wurde rot, weil seit dem 21.09. 20:16 kein Auto-Play mehr lief und beide Geschwister
        # damit 2,1 bzw. 2,5 Tage alt waren, knapp ueber FRISCH_BIS_TAGEN=2. Kaputt war nichts;
        # das Haus hatte nur ein ruhiges Wochenende.
        # Fehlerklasse: ein Test, dessen Ergebnis vom Kalender abhaengt — er wird rot, wenn
        # nichts passiert ist, und dann liest man ueber ihn hinweg.
        # Die Gegenprobe stellt den Fall deshalb selbst her: `jetzt` wird auf einen halben Tag
        # nach dem juengsten Geschwister gesetzt. Damit ist per Konstruktion eines frisch und
        # die Probe weiter 70+ Tage tot — geprueft wird die REGEL, nicht der Kalender.
        juengstes = min((alter_tage(g) or 99) for g in geschw)
        jetzt = time.time() - (juengstes - 0.5) * 86400.0
        frisch = [g for g in geschw if (alter_tage(g, jetzt) or 99) < FRISCH_BIS_TAGEN]
        assert frisch, "kein frisches Geschwister — die Regel koennte hier gar nicht anschlagen"
        assert (alter_tage("wm_auto_bets_placed.json", jetzt) or 0) > TOT_AB_TAGEN

    def test_ein_modul_das_alle_varianten_liest_gilt_nicht_als_blind(self):
        # betfair_alerts fuehrt liga/mls/wm-Serien zu EINEM Pool zusammen — Absicht, kein Fund.
        src = '("liga_streaks.json", "mls_streaks.json", "wm_streaks.json")'
        assert liest_alle_varianten(src, "wm_streaks.json")
        assert not liest_alle_varianten('"wm_streaks.json"', "wm_streaks.json")

    def test_ein_auskommentierter_zeitplan_zaehlt_nicht(self):
        # fetch-wm-data.yml traegt seinen Cron seit dem Turnierende hinter `#`. Sein Modul
        # pre_match_readiness.py liest vier tote WM-Dateien — voellig in Ordnung, es laeuft nicht.
        assert not AKTIVER_CRON.search("  # schedule:\n  #   - cron: '0 4 * * *'\n")
        assert AKTIVER_CRON.search("  schedule:\n    - cron: '0 4 * * *'\n")
        assert "pre_match_readiness.py" not in aktive_module()

    def test_ein_kommentar_ist_kein_verhalten(self):
        """🔴 Der Waechter machte im ersten Anlauf selbst den Fehler, gegen den er schuetzt.

        `poly_heartbeat.py` nennt `cocobet_dataset` in einem Kommentar, der erklaert, warum es
        das Modul NICHT benutzt. Die Regel las das als Code — und haette den echten Fehler vom
        15.09. durchgewunken. Diese Mutation ueberlebte, bis `nur_code` dazukam."""
        mit_kommentar = ('# wir benutzen cocobet_dataset ABSICHTLICH NICHT\n'
                         'PLACED_FILE = "wm_auto_bets_placed.json"\n')
        assert not datensatz_bewusst(nur_code(mit_kommentar))
        docstring = ('"""Warum nicht cocobet_dataset: weil D.file( ) die Env liest."""\n'
                     'PLACED_FILE = "wm_auto_bets_placed.json"\n')
        assert not datensatz_bewusst(nur_code(docstring))
        # und der echte Gebrauch wird weiterhin erkannt
        assert datensatz_bewusst(nur_code('import cocobet_dataset as D\nx = D.file("a", "b")\n'))

    def test_das_echte_heartbeat_modul_gilt_nicht_wegen_seiner_kommentare_als_sauber(self):
        p = os.path.join(REPO, "poly_heartbeat.py")
        if not os.path.isfile(p):
            pytest.skip("poly_heartbeat.py gibt es nicht")
        roh = open(p, encoding="utf-8").read()
        assert "cocobet_dataset" in roh, "Kommentar weg — dann taugt die Datei nicht als Probe"
        # Sauber ist es, weil es PREIS_DATENSAETZE benutzt — nicht, weil ein Kommentar ein Wort nennt.
        code = nur_code(roh)
        assert "cocobet_dataset" not in code
        assert "PREIS_DATENSAETZE" in code

    def test_die_modulliste_ist_abgeleitet_nicht_gepflegt(self):
        # Eine Namensliste vergisst genau das Modul, das neu ist — dieselbe Lehre wie beim
        # Pages-Ballast am 02.09.
        mods = aktive_module()
        assert len(mods) > 30, "die Ableitung findet fast nichts — dann prueft der Test nichts"
        assert "poly_heartbeat.py" in mods, "der Heartbeat laeuft taeglich und muss geprueft werden"

    def test_ausnahmen_tragen_datum_und_grund(self):
        for mod, grund in AUSNAHMEN.items():
            assert re.search(r"\d{2}\.\d{2}\.\d{4}", str(grund)), "%s ohne Datum" % mod
            assert len(str(grund)) > 40, "%s ohne echte Begruendung" % mod


def test_eine_getrackte_datei_wird_durch_anfassen_nicht_juenger():
    """🔴 19.09.2026 — die Gegenprobe zur Gegenprobe.

    `alter_tage` las die mtime, und die ist keine Eigenschaft der Daten: ein `git checkout`,
    `stash pop` oder Rebase schreibt die Datei neu und macht sie „frisch". Genau so stand
    `wm_auto_bets_placed.json` — inhaltlich seit dem 12.07. unveraendert — mit zwoelf Minuten
    Alter da und riss `test_die_regel_faengt_die_heartbeat_falle`. Ein Waechter, dessen Probe
    davon abhaengt, wer zuletzt im Arbeitsverzeichnis herumgelaufen ist, misst nicht die Sache.
    """
    datei = "wm_auto_bets_placed.json"
    p = os.path.join(REPO, datei)
    if not os.path.isfile(p):
        pytest.skip("Probe-Datei gibt es nicht mehr")
    _ALTER_CACHE.pop(datei, None)
    vorher = alter_tage(datei)
    assert vorher is not None
    os.utime(p, None)                      # genau das, was ein Checkout tut
    _ALTER_CACHE.pop(datei, None)
    nachher = alter_tage(datei)
    assert nachher is not None
    assert abs(nachher - vorher) < 0.01, (
        "Anfassen hat die Datei um %.2f Tage verjuengt — dann misst der Waechter den Checkout, "
        "nicht die Daten." % (vorher - nachher))
    assert vorher > TOT_AB_TAGEN, "die Probe-Datei muss tot sein, sonst taugt sie nicht als Probe"
