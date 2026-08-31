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

    # 30.08.2026: beide Prüfungen galten nur für die LIGA. Genau diese Lücke hat die MLS
    # driften lassen — dort blieben :00-Crons und die geteilte Gruppe stehen, während die Liga
    # am 28.08. beides bekam. Jetzt gelten sie für beide Vollläufe, und zusätzlich für die
    # dichten Läufe: deren eigener Gesundheits-Log zeigte für '0 */2' tatsächliche Abstände von
    # 4,93h · 3,10h · 4,18h · 6,36h · 7,17h bei durchweg ok:true — sie scheiterten nicht,
    # sie wurden gar nicht erst gestartet.
    @pytest.mark.parametrize("datei", ["update-liga.yml", "update-mls.yml",
                                       "fetch-liga-odds-dense.yml", "fetch-mls-odds-dense.yml"])
    def test_startet_nicht_auf_der_vollen_stunde(self, datei):
        """:00 ist repo-weit UND GitHub-global die vollste Minute."""
        for c in crons(datei):
            assert minuten(c) != {0}, f"{datei} läuft auf :00 ({c})"

    @pytest.mark.parametrize("datei", ["update-liga.yml", "update-mls.yml"])
    def test_volllauf_hat_eine_eigene_concurrency_gruppe(self, datei):
        """Geteilte Gruppe = wartende Läufe werden gecancelt; der seltenste verliert.

        Der Volllauf trägt Digest und Recap und ist mit 2 von ~40 Läufen der seltenste
        Teilnehmer — also strukturell der Verlierer. Ein manuell gestarteter Backtest darf
        die Gruppe teilen (er schreibt dieselben Prior-Dateien und MUSS serialisiert sein);
        ein GETAKTETER Workflow darf es nicht."""
        gruppe = re.search(r"^concurrency:.*?^\s*group:\s*(\S+)",
                           lies(datei), re.M | re.S).group(1)
        andere = [f for f in os.listdir(WF)
                  if f.endswith((".yml", ".yaml")) and f != datei
                  and re.search(rf"^\s*group:\s*{re.escape(gruppe)}\b", lies(f), re.M)
                  and crons(f)]
        assert not andere, f"{datei}: Gruppe '{gruppe}' wird auch von getakteten {andere} benutzt"

    # 30.08.2026 (zweiter Checkup): poly-live-scan dazu. Die Übersicht meldete selbst „letzte
    # Erfassung vor 3 h — der Live-Scan (Mac-Runner) lief zuletzt nicht", und im Repo stand
    # nichts, woran man sähe warum. Der Workflow committet innerhalb seiner Loop-Schleife, hat
    # also keinen eigenen Commit-Step — der Wächter hängt hinten dran.
    @pytest.mark.parametrize("datei", ["update-liga.yml", "fetch-liga-odds-dense.yml",
                                       "update-mls.yml", "fetch-mls-odds-dense.yml",
                                       "poly-live-scan.yml"])
    def test_getakteter_lauf_meldet_seine_gesundheit(self, datei):
        """Lucas am 30.08.: „was soll ich mir bei MLS in den Actions anschauen?"

        Die ehrliche Antwort war: nichts. run_health.py lief in beiden LIGA-Workflows und in
        keinem MLS-Workflow — deshalb existierte nie eine health/mls*.json, und ob ein Lauf
        stattfand, scheiterte oder gecancelt wurde, stand nirgends."""
        src = lies(datei)
        assert "run_health.py --slug" in src, f"{datei}: kein Gesundheits-Wächter"
        assert "actions: read" in src, f"{datei}: run_health.py braucht actions:read"


class TestDigestZustandUeberlebtDenLauf:
    """30.08.2026 (Lucas-Checkup): der Digest ging raus, aber `lastDigestDate` blieb auf dem
    Vortag stehen — der Lauf starb, bevor er am Jobende committen konnte. Der Versand steht
    frueh im Job, der Commit ganz hinten; alles dazwischen ist Risiko.

    Die Folge war nicht kosmetisch: notify_new_picks prueft `lastDigestDate == heute`. Steht dort
    ein alter Tag, haelt es sich fuer VOR dem Digest, setzt stumm die Basis und sendet den ganzen
    Tag nichts — genau die Luecke, fuer die die Intraday-Noti gebaut wurde.

    Dieselbe Lehre wie am 27.08. („Digest kam heute frueh nicht"), eine Ebene hoeher: damals
    fehlte die Datei in der Commit-Liste, jetzt kam die Commit-Liste zu spaet."""

    DATEIEN = ["update-liga.yml", "update-mls.yml"]

    def _steps(self, datei):
        yaml = pytest.importorskip('yaml', reason='PyYAML fehlt')
        with open(os.path.join(WF, datei), encoding="utf-8") as f:
            jobs = (yaml.safe_load(f).get("jobs") or {}).values()
        raus = []
        for job in jobs:
            raus.extend((job or {}).get("steps") or [])
        return raus

    @staticmethod
    def _sendet(step):
        """Ruft dieser Step telegram_wm.py wirklich AUF? Ein Treffer im Kommentar zaehlt nicht —
        der Kommentar vom 27.08. steht ausgerechnet im finalen Commit-Step."""
        for zeile in str(step.get("run") or "").splitlines():
            z = zeile.strip()
            if z.startswith("#"):
                continue
            if re.match(r"^python3? telegram_wm\.py\b", z):
                return True
        return False

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_nach_jedem_versand_wird_der_zustand_gesichert(self, datei):
        steps = self._steps(datei)
        sender = [i for i, s in enumerate(steps) if self._sendet(s)]
        assert sender, f"{datei}: kein telegram_wm.py-Versand gefunden — Test zeigt ins Leere"
        for i in sender:
            folge = steps[i + 1] if i + 1 < len(steps) else {}
            assert "Digest-Zustand sofort sichern" in str(folge.get("name") or ""), (
                f"{datei}: nach '{steps[i].get('name')}' folgt '{folge.get('name')}' statt der "
                f"Zustands-Sicherung — ein Abbruch danach kostet die Intraday-Noti fuer den Tag")

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_die_sicherung_laeuft_auch_nach_einem_fehler(self, datei):
        """Ohne `if: always()` liefe sie genau dann nicht, wenn der Versand geknirscht hat."""
        for s in self._steps(datei):
            if "Digest-Zustand sofort sichern" in str(s.get("name") or ""):
                assert str(s.get("if", "")).strip() == "always()", \
                    f"{datei}: Zustands-Sicherung ohne `if: always()`"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_die_sicherung_macht_den_lauf_nicht_rot(self, datei):
        for s in self._steps(datei):
            if "Digest-Zustand sofort sichern" in str(s.get("name") or ""):
                assert s.get("continue-on-error") is True, \
                    f"{datei}: ein fehlgeschlagener Push darf den Lauf nicht kippen"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_gesichert_wird_genau_der_zustand_der_verloren_ging(self, datei):
        pre = "liga" if "liga" in datei else "mls"
        for s in self._steps(datei):
            if "Digest-Zustand sofort sichern" in str(s.get("name") or ""):
                run = str(s.get("run") or "")
                assert f"{pre}_pick_announce_state.json" in run, "lastDigestDate war der Verlust"
                assert f"{pre}_telegram_sent.json" in run, "sonst droht ein Doppel-Post"
                assert f"{pre}-telegram-log.json" in run
                return
        pytest.fail(f"{datei}: keine Zustands-Sicherung gefunden")


class TestMacRunnerDisziplin:
    """28.08.2026 (Lucas: „mmn ist polymarket tot").

    Befund: manage-liga-poly hatte seit 04:26 UTC keinen Lauf mehr committet — 13 Stunden, bei
    25 geplanten Laeufen pro Tag. Die committeten Laeufe zerfielen ueber vier Tage von 13 auf 1
    (MLS parallel von 10 auf 2). Auf DEMSELBEN Mac lief betfair.yml im 15-Minuten-Takt sauber
    durch. Der Unterschied: betfair hat `timeout-minutes: 8` und eine eigene concurrency-Gruppe.

    Ohne timeout gilt GitHubs Default von 360 Minuten. Ein haengender Lauf besetzt damit einen
    der zwei Mac-Runner sechs Stunden lang — und blockiert, wenn er sich die Spur mit anderen
    teilt, zusaetzlich jeden wartenden Lauf, der dann vom naechsten Ankoemmling gecancelt wird.
    """
    import os as _os

    @staticmethod
    def _jobs(datei):
        # 30.08.2026: lokaler Import mit Netz — ohne PyYAML sollen diese vier Prüfungen
        # übersprungen werden, nicht scheitern. PyYAML steht jetzt in requirements.txt;
        # das hier ist die Rückfallebene, falls der Install einmal ausfällt.
        yaml = pytest.importorskip('yaml', reason='PyYAML fehlt')
        with open(os.path.join(WF, datei), encoding="utf-8") as f:
            return list((yaml.safe_load(f).get("jobs") or {}).values())

    @staticmethod
    def _self_hosted():
        yaml = pytest.importorskip('yaml', reason='PyYAML fehlt')
        raus = []
        for f in sorted(os.listdir(WF)):
            if not f.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(WF, f), encoding="utf-8") as fh:
                src = fh.read()
            if "self-hosted" in src:
                raus.append(f)
        return raus

    def test_jeder_mac_workflow_hat_ein_timeout(self):
        ohne = []
        for f in self._self_hosted():
            for jd in self._jobs(f):
                ro = (jd or {}).get("runs-on")
                ro = ",".join(ro) if isinstance(ro, list) else str(ro)
                if "self-hosted" in ro and (jd or {}).get("timeout-minutes") is None:
                    ohne.append(f)
        assert not ohne, (
            f"Mac-Workflows ohne timeout-minutes: {sorted(set(ohne))} — GitHubs Default sind "
            f"360 Minuten, das blockiert einen von zwei Runnern einen halben Tag.")

    def test_timeouts_bleiben_im_rahmen(self):
        zu_lang = []
        for f in self._self_hosted():
            for jd in self._jobs(f):
                t = (jd or {}).get("timeout-minutes")
                if t is not None and t > 75:
                    zu_lang.append((f, t))
        assert not zu_lang, f"Mac-Workflows mit sehr langem timeout: {zu_lang}"

    def test_poly_manager_teilen_ihre_spur_nicht_mit_ubuntu_workflows(self):
        """Mac und ubuntu teilen keine Dateien — die gemeinsame Spur kostete nur Laeufe."""
        yaml = pytest.importorskip('yaml', reason='PyYAML fehlt')
        import re as _re
        for datei in ("manage-liga-poly.yml", "manage-mls-poly.yml"):
            with open(os.path.join(WF, datei), encoding="utf-8") as f:
                src = f.read()
            gruppe = _re.search(r"^concurrency:.*?^\s*group:\s*(\S+)", src, _re.M | _re.S).group(1)
            andere = []
            for f2 in sorted(os.listdir(WF)):
                if not f2.endswith((".yml", ".yaml")) or f2 == datei:
                    continue
                with open(os.path.join(WF, f2), encoding="utf-8") as fh:
                    s2 = fh.read()
                if _re.search(rf"^\s*group:\s*{_re.escape(gruppe)}\s*$", s2, _re.M):
                    andere.append(f2)
            assert not andere, f"{datei}: Gruppe '{gruppe}' wird auch von {andere} benutzt"

    def test_clob_client_wird_nicht_bei_jedem_lauf_neu_gebaut(self):
        """Der Preis-Fetch nutzt nur urllib. Ein Netz-Schluckauf beim CLOB-Build darf den
        Daten-Pfad nicht mitreissen — genau daran ist der Poly-Lauf gestorben."""
        yaml = pytest.importorskip('yaml', reason='PyYAML fehlt')
        for datei in ("manage-liga-poly.yml", "manage-mls-poly.yml"):
            with open(os.path.join(WF, datei), encoding="utf-8") as f:
                wf = yaml.safe_load(f)
            steps = [s for jd in (wf.get("jobs") or {}).values() for s in (jd.get("steps") or [])]
            bau = [s for s in steps if "py-clob-client-v2.git" in str(s.get("run") or "")]
            assert len(bau) == 1, f"{datei}: {len(bau)} CLOB-Bau-Schritte, erwartet 1"
            schritt = bau[0]
            assert schritt.get("continue-on-error") is True, \
                f"{datei}: CLOB-Bau ohne continue-on-error — reisst den ganzen Job mit"
            assert schritt.get("timeout-minutes") is not None, \
                f"{datei}: CLOB-Bau ohne timeout — kann den Runner blockieren"
            assert "from py_clob_client_v2.client import ClobClient" in str(schritt.get("run")), \
                f"{datei}: CLOB-Bau prueft nicht erst, ob der Client schon da ist"


class TestPreMatchNachzuegler:
    """31.08.2026 — der Morgen-Digest fiel WIEDER aus (kein update-liga-Lauf, kein Eintrag in
    liga_telegram_sent.json). Gegen einen verschluckten Cron hilft kein besserer Cron, nur ein
    zweiter Versuch. Damit der Nachzügler nicht selbst still verschwindet, wird hier festgehalten:

      · er existiert,
      · JEDER Schritt, der auf den PRE-Cron hört, hört auch auf ihn (sonst läuft der Nachzügler
        durch und tut genau das Falsche: alles außer dem Digest),
      · er liegt vor den frühesten Top-5-Anpfiffen.
    """

    PRE = "7 6 * * *"
    NACH = "37 7 * * *"

    def test_nachzuegler_ist_deklariert(self):
        assert self.NACH in crons("update-liga.yml"), (
            "Der PRE-Match-Nachzügler fehlt — ein ausgefallener 06:07-Lauf wird dann nicht "
            "mehr aufgefangen.")

    def test_jeder_pre_schritt_hoert_auch_auf_den_nachzuegler(self):
        src = lies("update-liga.yml")
        zeilen = [z for z in src.splitlines()
                  if "github.event.schedule" in z and self.PRE in z]
        assert zeilen, "keine PRE-Bedingung gefunden — Struktur geändert?"
        ohne = [z.strip() for z in zeilen if self.NACH not in z]
        assert not ohne, (
            "Diese PRE-Schritte kennen den Nachzügler nicht und laufen bei ihm NICHT: "
            f"{ohne}. Cron und if müssen zusammen wandern.")

    def test_nachzuegler_liegt_vor_den_fruehesten_anpfiffen(self):
        stunde = int(self.NACH.split()[1])
        fruehester = min(kickoff_stunden("liga-data.json") or {10: 1})
        assert stunde < fruehester, (
            f"Nachzügler um {stunde}:xx UTC liegt nicht mehr vor dem frühesten Anpfiff "
            f"({fruehester}:00 UTC) — ein Digest nach Anpfiff ist wertlos.")
