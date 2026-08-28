"""28.08.2026 — Cron-Hygiene, entstanden aus Lucas' „ich hab den Push in der Früh vermisst".

Gemessen wurde damals: 585 geplante Läufe/Tag über 23 Workflows, und der 06:00-Slot von
„Liga aktualisieren" fiel am 15.08., 27.08. und 28.08. komplett aus. Drei Ursachen, drei
Testklassen hier:

  1. update-liga.yml unterscheidet PRE-/POST-Match über `github.event.schedule == '<cron>'`.
     Wer den Cron verschiebt und die if-Bedingung vergisst, schaltet den Digest STILL ab —
     der Workflow läuft grün durch und tut nichts. Genau diese Kopplung prüfen wir.
  2. Anpfiff-Fenster: die Closing-Capture lief 11-23 Uhr, die frühesten Top-5-Anpfiffe sind
     aber 10:00 UTC → für die gab es nie eine Closing-Linie.
  3. Volle Stunde: auf :00 starten repo-weit bis zu 11 Jobs gleichzeitig.
"""
import os
import re
import json
import collections
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(REPO, ".github", "workflows")

_CRON = re.compile(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", re.M)


def lies(datei):
    with open(os.path.join(WF, datei), encoding="utf-8") as f:
        return f.read()


def crons(datei):
    return _CRON.findall(lies(datei))


def _feld(teil, lo, hi):
    out = set()
    for stueck in teil.split(","):
        schritt = 1
        if "/" in stueck:
            stueck, s = stueck.split("/")
            schritt = int(s)
        if stueck == "*":
            a, b = lo, hi
        elif "-" in stueck:
            a, b = [int(x) for x in stueck.split("-")]
        else:
            a = b = int(stueck)
        out.update(range(a, b + 1, schritt))
    return {x for x in out if lo <= x <= hi}


def stunden(cron):
    return _feld(cron.split()[1], 0, 23)


def minuten(cron):
    return _feld(cron.split()[0], 0, 59)


def laeufe_pro_tag(cron):
    t = cron.split()
    tage = 7 if (t[4] == "*" and t[2] == "*") else (len(_feld(t[4], 0, 6)) if t[4] != "*" else 7)
    return len(minuten(cron)) * len(stunden(cron)) * tage / 7


def kickoff_stunden(datei):
    with open(os.path.join(REPO, datei), encoding="utf-8") as f:
        d = json.load(f)
    fx = []
    for g in (d.get("groups") or {}).values():
        fx += (g.get("fixtures") or [])
    fx += d.get("koFixtures") or []
    c = collections.Counter()
    for f in fx:
        ko = f.get("kickoff") or ""
        if len(ko) >= 13:
            c[int(ko[11:13])] += 1
    return c


class TestScheduleBedingungenPassenZuDenCrons:
    """Der Cron und das `if:` müssen zusammen wandern — sonst läuft der Digest nie wieder."""

    @pytest.mark.parametrize("datei", ["update-liga.yml", "update-mls.yml"])
    def test_jede_if_bedingung_hat_einen_cron(self, datei):
        src = lies(datei)
        genutzt = set(re.findall(r"github\.event\.schedule\s*==\s*'([^']+)'", src))
        deklariert = set(crons(datei))
        fehlend = genutzt - deklariert
        assert not fehlend, (
            f"{datei}: `if:` prüft auf {sorted(fehlend)}, aber dieser Cron ist nicht (mehr) "
            f"deklariert — diese Schritte laufen nie. Deklariert: {sorted(deklariert)}")

    @pytest.mark.parametrize("datei", ["update-liga.yml", "update-mls.yml"])
    def test_jeder_cron_wird_auch_benutzt(self, datei):
        src = lies(datei)
        genutzt = set(re.findall(r"github\.event\.schedule\s*==\s*'([^']+)'", src))
        verwaist = set(crons(datei)) - genutzt
        assert not verwaist, (
            f"{datei}: Cron {sorted(verwaist)} feuert, aber kein Schritt hört darauf.")


class TestAnpfiffFensterDeckenDieSpieleAb:
    """Eine Closing-Linie, die nach dem Anpfiff geholt wird, ist wertlos."""

    def test_liga_capture_deckt_alle_top5_anpfiffe(self):
        abgedeckt = set()
        for c in crons("capture-closing-liga.yml"):
            abgedeckt |= stunden(c)
        offen = {h: n for h, n in kickoff_stunden("liga-data.json").items()
                 if h not in abgedeckt or (h - 1) not in abgedeckt}
        assert not offen, (
            f"Top-5-Anpfiffe ohne Capture-Vorlauf (Stunde UTC → Anzahl Fixtures): {offen}. "
            f"Fenster deckt {sorted(abgedeckt)} ab.")

    def test_mls_capture_deckt_alle_anpfiffe(self):
        abgedeckt = set()
        for c in crons("capture-closing-mls.yml"):
            abgedeckt |= stunden(c)
        offen = {h: n for h, n in kickoff_stunden("mls-data.json").items() if h not in abgedeckt}
        assert not offen, f"MLS-Anpfiffe ohne Capture: {offen}"

    def test_liga_capture_laeuft_nicht_ins_leere(self):
        """Umgekehrte Richtung: Stunden ohne jeden Anpfiff kosten nur Quota.

        Toleranz: 2 h Vorlauf vor dem frühesten und 2 h Nachlauf nach dem spätesten Anpfiff.
        """
        ko = kickoff_stunden("liga-data.json")
        frueh, spaet = min(ko), max(ko)
        abgedeckt = set()
        for c in crons("capture-closing-liga.yml"):
            abgedeckt |= stunden(c)
        verschwendet = sorted(h for h in abgedeckt if h < frueh - 2 or h > spaet + 2)
        assert not verschwendet, (
            f"Capture läuft um {verschwendet} Uhr UTC, Anpfiffe gibt es aber nur "
            f"{frueh}-{spaet} Uhr.")


class TestLastBleibtImRahmen:
    def test_gesamtlast_unter_grenze(self):
        """585/Tag waren zu viel (GitHub verzögerte/verschluckte Schedules). Deckel: 540."""
        summe = sum(laeufe_pro_tag(c)
                    for f in sorted(os.listdir(WF)) if f.endswith((".yml", ".yaml"))
                    for c in crons(f))
        assert summe <= 540, f"{summe:.0f} geplante Läufe/Tag — vorher 585, Ziel <= 540"

    def test_digest_startet_nicht_auf_der_vollen_stunde(self):
        """:00 ist repo-weit UND GitHub-global die vollste Minute."""
        for c in crons("update-liga.yml"):
            assert minuten(c) != {0}, f"update-liga läuft auf :00 ({c})"

    def test_digest_hat_eine_eigene_concurrency_gruppe(self):
        """Geteilte Gruppe = wartende Läufe werden gecancelt; der seltenste verliert."""
        gruppe = re.search(r"^concurrency:.*?^\s*group:\s*(\S+)",
                           lies("update-liga.yml"), re.M | re.S).group(1)
        andere = [f for f in os.listdir(WF)
                  if f.endswith((".yml", ".yaml")) and f != "update-liga.yml"
                  and re.search(rf"^\s*group:\s*{re.escape(gruppe)}\s*$", lies(f), re.M)]
        assert not andere, f"Gruppe '{gruppe}' wird auch von {andere} benutzt"
