#!/usr/bin/env python3
"""
run_health.py — macht verschluckte Workflow-Fehler sichtbar.

28.08.2026 (Lucas: „glaubst du nicht auch dass oft in diesen Logs Fehler stehen die wir gar
nicht mitkriegen?"). Gezaehlt: von 393 Steps stehen 135 auf `continue-on-error: true`, dazu
279 `|| true` in den run-Bloecken. Jeder dritte Schritt darf also scheitern, ohne dass der Job
rot wird. Zwei bewiesene Faelle aus genau diesem Muster:

  * resolve_picks.py starb an einem KeyError → drei Monate lang wurde KEIN Pick aufgeloest,
    315 offene Eintraege, Job durchgehend gruen.
  * fetch_wm_poly_prices.py verlor ab dem 24.08. jeden Lauf die anpfiff-nahen Maerkte, weil das
    600-Event-Budget aufgebraucht war. Hier warf niemand eine Exception — „599 events received"
    sieht aus wie Erfolg.

Dieses Skript deckt den ERSTEN Fall ab, und zwar vollstaendig: es fragt ueber die GitHub-API die
Steps des eigenen Laufs ab und meldet jeden mit conclusion=failure — auch die, die
continue-on-error gerade eben stillgelegt hat. Kein Log-Parsen, kein Raten.

Aufruf am Ende eines Jobs, VOR dem Commit-Schritt:

    - name: 🩺 Lauf-Gesundheit
      if: always()
      run: python3 run_health.py --slug liga
      env:
        GITHUB_TOKEN:            ${{ secrets.GITHUB_TOKEN }}
        TELEGRAM_TOKEN:          ${{ secrets.TELEGRAM_TOKEN }}
        TELEGRAM_TRADES_CHAT_ID: ${{ secrets.TELEGRAM_TRADES_CHAT_ID }}

Der Workflow braucht dafuer `permissions: actions: read`.

Geschrieben wird `health/<slug>.json` — EINE Datei je Workflow, nie eine geteilte. Das ist
Absicht: eine gemeinsame Datei, in die 20 Workflows schreiben, waere ein Merge-Konflikt-Magnet,
und die `git pull -X ours`-Strategie der Push-Schleifen wuerde fremde Eintraege still verwerfen.

Beendet sich IMMER mit 0. Ein Waechter, der den ueberwachten Lauf rot macht, wird abgeschaltet.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

HEALTH_DIR = "health"
API = "https://api.github.com"
# conclusion-Werte, die einen Step als kaputt gelten lassen. `skipped` gehoert bewusst NICHT dazu:
# die meisten Steps hier haengen an einem `if:` und werden im Normalbetrieb uebersprungen.
SCHLECHT = ("failure", "timed_out", "cancelled")
# Wie viele Laeufe je Workflow in der Historie bleiben. Reicht, um „seit wann?" zu beantworten,
# ohne dass die Datei ueber eine Saison waechst.
HISTORIE = 20


def _jetzt():
    return datetime.now(timezone.utc).isoformat()


def _get_json(url, token, timeout=20):
    kopf = {"Accept": "application/vnd.github+json",
            "User-Agent": "BetEdge-run-health/1.0",
            "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        kopf["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def hole_steps(repo, run_id, token, fetch=None):
    """[(job_name, step_name, conclusion, step_nummer)] fuer den ganzen Lauf.

    `fetch` ist injizierbar (Tests). Paginiert, weil ein Lauf mehrere Jobs haben kann.
    """
    _get = fetch or (lambda u: _get_json(u, token))
    raus, seite = [], 1
    while seite <= 5:
        daten = _get(f"{API}/repos/{repo}/actions/runs/{run_id}/jobs"
                     f"?per_page=100&page={seite}&filter=latest") or {}
        jobs = daten.get("jobs") or []
        for job in jobs:
            for step in (job.get("steps") or []):
                raus.append((job.get("name") or "?", step.get("name") or "?",
                             step.get("conclusion"), step.get("number")))
        if len(jobs) < 100:
            break
        seite += 1
    return raus


def hole_lauf(repo, run_id, token, fetch=None):
    """Der Lauf selbst: wann wurde er ERZEUGT, wann hat er BEGONNEN.

    🔴 20.09.2026. Im Workflow-Kommentar von `manage-liga-poly` steht seit jeher: „Alle 30 Min,
    damit garantiert ein Lauf ins 40-Min-Pre-Match-Close-Fenster jedes Spiels faellt." Gemessen
    an diesem Tag aus diesem Protokoll: 20 Laeufe in 96,7 h, also 5,0 statt 25 am Tag, kleinste
    Luecke 64 Minuten — groesser als das Fenster. Bei 0 von 7 Liga-Positionen lag je ein Lauf im
    Schliessfenster. Der Pre-Match-Close hat nie funktioniert.

    Warum er nicht laeuft, liess sich NICHT sagen: das Protokoll hielt nur fest, DASS ein Lauf
    war, nie wie lange er auf einen Runner gewartet hat. Genau diese eine Zahl trennt die beiden
    Erklaerungen — „die Macs sind dicht" (lange Wartezeit) von „der Zeitplan feuert nicht"
    (kurze Wartezeit, trotzdem wenige Laeufe).

    Fehlerklasse: eine Taktung, die als Kommentar existiert und nie nachgezaehlt wurde.
    """
    _get = fetch or (lambda u: _get_json(u, token))
    d = _get(f"{API}/repos/{repo}/actions/runs/{run_id}") or {}
    return {"createdAt": d.get("created_at"),
            "startedAt": d.get("run_started_at"),
            "event": d.get("event"),
            "workflowId": d.get("workflow_id"),
            "attempt": d.get("run_attempt")}


def _sekunden_zwischen(a, b):
    """Sekunden zwischen zwei ISO-Zeitstempeln. None, wenn einer fehlt oder unlesbar ist —
    `None` heisst „nicht gemessen" und darf nie als 0 durchgehen."""
    if not a or not b:
        return None
    try:
        ta = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        tb = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ta.tzinfo is None:
        ta = ta.replace(tzinfo=timezone.utc)
    if tb.tzinfo is None:
        tb = tb.replace(tzinfo=timezone.utc)
    return round((tb - ta).total_seconds(), 1)


def kadenz(laeufe, soll_pro_tag=None, fenster_min=None, stunden=None):
    """Was die Taktung WIRKLICH liefert — aus dem Protokoll, nicht aus dem Cron-Kommentar.

    Gibt Laufzahl, Spanne, Laeufe/Tag, die Luecken und — wenn ein `fenster_min` genannt ist —
    das Urteil, ob ein Zeitfenster dieser Groesse ueberhaupt getroffen werden KANN. Es kann nur
    dann garantiert getroffen werden, wenn die groesste Luecke kleiner ist als das Fenster; ist
    schon die KLEINSTE Luecke groesser, ist das Fenster reine Glueckssache.
    """
    ts = []
    for r in (laeufe or []):
        t = r.get("ts")
        if not t:
            continue
        try:
            d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        ts.append(d if d.tzinfo else d.replace(tzinfo=timezone.utc))
    ts.sort()
    raus = {"nLaeufe": len(ts), "spanneH": None, "proTag": None,
            "lueckeMinMin": None, "lueckeMedianMin": None, "lueckeMaxMin": None,
            "sollProTag": soll_pro_tag, "liefergradPct": None,
            "fensterMin": fenster_min, "fensterUrteil": None}
    if len(ts) < 2:
        return raus
    spanne_h = (ts[-1] - ts[0]).total_seconds() / 3600
    raus["spanneH"] = round(spanne_h, 1)
    if spanne_h > 0:
        # n Laeufe spannen n-1 Intervalle. `len(ts)/spanne` zaehlt einen Lauf zu viel und
        # meldet 50,5 statt 48 — eine Taktung, die sich selbst um 5 % zu gut rechnet.
        raus["proTag"] = round((len(ts) - 1) / spanne_h * 24, 1)
        if soll_pro_tag:
            raus["liefergradPct"] = round(raus["proTag"] / soll_pro_tag * 100)
    # Nur Luecken INNERHALB des aktiven Fensters: bei „0,30 10-21" ist die Nachtluecke 13
    # Stunden und per Konstruktion groesser als jedes Schliessfenster — ohne diesen Filter
    # koennte ein Fenster-Workflow nie „sicher" heissen, egal wie gut er laeuft.
    roh = []
    for a, b in zip(ts, ts[1:]):
        if stunden is not None and (a.hour not in stunden or b.hour not in stunden
                                    or a.date() != b.date()):
            continue
        roh.append((b - a).total_seconds() / 60)
    if not roh:
        return raus
    lue = sorted(roh)
    raus["lueckeMinMin"] = round(lue[0], 1)
    raus["lueckeMaxMin"] = round(lue[-1], 1)
    raus["lueckeMedianMin"] = round(lue[len(lue) // 2], 1)
    if fenster_min:
        if raus["lueckeMaxMin"] <= fenster_min:
            raus["fensterUrteil"] = "sicher"
        elif raus["lueckeMinMin"] > fenster_min:
            raus["fensterUrteil"] = "nie sicher"
        else:
            raus["fensterUrteil"] = "Glueckssache"
    return raus


def fehlerhafte_steps(steps):
    """Nur die kaputten — in Ausfuehrungsreihenfolge, damit der ERSTE Fehler oben steht."""
    schlecht = [s for s in steps if s[2] in SCHLECHT]
    return sorted(schlecht, key=lambda s: (s[0], s[3] if s[3] is not None else 0))


def lade(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ── Wie viele Laeufe GitHub ueberhaupt ERZEUGT (22.09.2026) ───────────────────────────────
# 🔴 Lucas' Stoerungsmeldung vom 22.09.: „Letzter Live-Scan vor 1.6h (Takt: 15 Min)". Der
# Live-Scan liefert 6,1 statt 96 Laeufe am Tag, `manage-liga-poly` 4,7 statt 25.
#
# Der Kommentar bei `hole_lauf` (20.09.) nennt die zwei Erklaerungen und die Zahl, die sie
# trennt: lange Wartezeit = „die Macs sind dicht", kurze Wartezeit = „der Zeitplan feuert nicht".
# Die Zahl ist inzwischen da, und sie ist eindeutig: **alle 20 protokollierten Laeufe hatten 0,0 s
# Wartezeit.** Wer lief, fand sofort einen Runner.
#
# Damit bleibt die zweite Erklaerung — aber „bleibt uebrig" ist kein Beweis. Es gibt eine dritte
# Moeglichkeit, die genauso aussieht: GitHub haelt je Concurrency-Gruppe hoechstens EINEN
# wartenden Lauf; ein neuer verdraengt den alten. Verdraengte Laeufe starten nie und schreiben
# deshalb nichts — dieses Protokoll kann sie per Bauart nicht sehen.
#
# Fehlerklasse: **ein Protokoll, das nur die Ueberlebenden kennt.** Deshalb ab jetzt eine
# zusaetzliche Frage an die API: wie viele Laeufe hat GitHub fuer diesen Workflow ERZEUGT, und
# wie viele davon sind gelaufen? Sind beide Zahlen klein, feuert der Zeitplan nicht. Ist die
# erste gross und die zweite klein, werden sie verdraengt. Eine Messung statt zweier Vermutungen.
def _zeit(w):
    """ISO -> datetime (UTC). REIN. None = unlesbar."""
    try:
        t = datetime.fromisoformat(str(w).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def hole_erzeugte(repo, workflow_id, token, fetch=None, seiten=1):
    """Die letzten erzeugten Schedule-Laeufe dieses Workflows. -> [{created,started,status,conclusion}]"""
    _get = fetch or (lambda u: _get_json(u, token))
    raus = []
    for seite in range(1, max(1, seiten) + 1):
        d = _get("%s/repos/%s/actions/workflows/%s/runs?event=schedule&per_page=100&page=%d"
                 % (API, repo, workflow_id, seite)) or {}
        teil = d.get("workflow_runs") or []
        for r in teil:
            raus.append({"created": r.get("created_at"), "started": r.get("run_started_at"),
                         "status": r.get("status"), "conclusion": r.get("conclusion")})
        if len(teil) < 100:
            break
    return raus


def erzeugungs_bilanz(erzeugte, jetzt=None):
    """{erzeugt, gelaufen, verdraengt, spanneH, erzeugtProTag} — REIN. Leer = None.

    `verdraengt` sind Laeufe, die erzeugt wurden und NIE begonnen haben. Das ist die Zahl, die
    „der Zeitplan feuert nicht" von „die Laeufe werden verdraengt" trennt.
    """
    rows = [r for r in (erzeugte or []) if isinstance(r, dict) and r.get("created")]
    if not rows:
        return None
    ts = []
    for r in rows:
        t = _zeit(r.get("created"))
        if t is not None:
            ts.append(t)
    if len(ts) < 2:
        return None
    spanne_h = (max(ts) - min(ts)).total_seconds() / 3600.0
    gelaufen = sum(1 for r in rows if r.get("started"))
    verdraengt = sum(1 for r in rows
                     if not r.get("started") and r.get("status") == "completed")
    return {"erzeugt": len(rows), "gelaufen": gelaufen, "verdraengt": verdraengt,
            "spanneH": round(spanne_h, 1),
            "erzeugtProTag": round(len(rows) / (spanne_h / 24.0), 1) if spanne_h > 0 else None}


def baue_eintrag(workflow, run_id, run_url, steps, api_fehler=None, lauf=None):
    """Ein Lauf als Zeile fuer die Historie.

    `apiError` ist wichtiger als es aussieht: konnten wir die Steps NICHT abfragen, heisst das
    „wir wissen es nicht" — und genau das muss dastehen, nicht „alles gruen". Fehlende
    Information ist keine Erlaubnis.
    """
    fails = fehlerhafte_steps(steps)
    lauf = lauf or {}
    _ts = _jetzt()
    return {
        "ts": _ts,
        "workflow": workflow,
        "runId": str(run_id or ""),
        "runUrl": run_url,
        "nSteps": len(steps),
        "apiError": api_fehler,
        "ok": (api_fehler is None and not fails),
        "failures": [{"job": j, "step": s, "conclusion": c} for j, s, c, _ in fails],
        # 20.09.2026: die drei Zahlen, ohne die „der Workflow laeuft nur 5x statt 25x" eine
        # Vermutung bleibt. `wartetS` ist die entscheidende: sie trennt „Runner dicht" von
        # „Zeitplan feuert nicht". None heisst „nicht gemessen" und nie 0.
        "createdAt": lauf.get("createdAt"),
        "startedAt": lauf.get("startedAt"),
        "wartetS": _sekunden_zwischen(lauf.get("createdAt"), lauf.get("startedAt")),
        # 🔴 23.09.2026 (Lucas: „betfair action hat scheinbar abgebrochen"). Der Lauf um 13:00 UTC
        # starb mit „The operation was canceled" — mitten in `ci_sichern.sh`, nach dem Commit des
        # Belegs und vor dessen Push. Der Beleg ist damit weg, die Alarme waren raus.
        #
        # Aus den Commit-Zeiten von zwoelf Laeufen: der Job braucht im Median 6,3 Minuten, der
        # Deckel steht auf 8. Anderthalb Minuten Luft — und die verbraucht der Beleg-Push selbst,
        # wenn er sich den Branch mit den ~130 Commits/Stunde teilen muss (drei Runden
        # pull+push). Der Deckel schneidet also genau dort, wo er am teuersten ist.
        #
        # Diese Zeile ist die Zahl, die das sichtbar macht, ohne sie aus git ausgraben zu muessen:
        # `run_health` laeuft als vorletzter Schritt, also ist „seit Start" hier praktisch die
        # Laufzeit. Fehlerklasse: ein Deckel, den der Lauf regelmaessig streift, ist kein Deckel,
        # sondern ein Wuerfel.
        "laeuftSeitS": _sekunden_zwischen(lauf.get("startedAt"), _ts),
        "event": lauf.get("event"),
    }


def zusammenfassen(eintrag):
    if eintrag.get("apiError"):
        return f"🩺 {eintrag['workflow']}: Lauf-Gesundheit UNBEKANNT ({eintrag['apiError']})"
    if eintrag["ok"]:
        return f"✅ {eintrag['workflow']}: alle {eintrag['nSteps']} Steps sauber"
    zeilen = [f"🚨 <b>{eintrag['workflow']}</b>: {len(eintrag['failures'])} Step(s) gescheitert "
              f"— der Job ist trotzdem grün (continue-on-error)."]
    for f in eintrag["failures"][:8]:
        zeilen.append(f"• {f['step']} <i>({f['conclusion']})</i>")
    if len(eintrag["failures"]) > 8:
        zeilen.append(f"… und {len(eintrag['failures']) - 8} weitere")
    if eintrag.get("runUrl"):
        zeilen.append(eintrag["runUrl"])
    return "\n".join(zeilen)


def alarm_noetig(eintrag, letzter):
    """Nur bei NEUEM Schaden alarmieren — sonst pingt jeder 30-Minuten-Lauf denselben Fehler.

    Neu heisst: eine Step-Kombination, die im letzten Lauf noch nicht kaputt war. Erholt sich
    ein Workflow und faellt spaeter wieder aus, ist das wieder neu → wieder ein Alarm.
    """
    if eintrag.get("apiError") or eintrag["ok"]:
        return False
    jetzt = {(f["job"], f["step"]) for f in eintrag["failures"]}
    vorher = {(f["job"], f["step"]) for f in ((letzter or {}).get("failures") or [])}
    return bool(jetzt - vorher)


def tg_send(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_TRADES_CHAT_ID")
    if not token or not chat:
        print("  📵 Kein TELEGRAM_TOKEN/CHAT_ID — Alarm nur in der Datei.")
        return False
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return bool(json.loads(resp.read()).get("ok"))
    except Exception as e:
        print(f"  ⚠️  Telegram fehlgeschlagen: {e}")
        return False


def _soll_pro_tag():
    try:
        v = float(os.environ.get("RUN_HEALTH_SOLL_PRO_TAG") or 0)
        return v or None
    except (TypeError, ValueError):
        return None


def _stunden():
    """Aktive Stunden (UTC) aus RUN_HEALTH_STUNDEN, z.B. „10-21". Ohne Angabe: kein Filter."""
    roh = (os.environ.get("RUN_HEALTH_STUNDEN") or "").strip()
    if not roh:
        return None
    raus = set()
    for stueck in roh.split(","):
        if "-" in stueck:
            try:
                a, b = (int(x) for x in stueck.split("-", 1))
            except ValueError:
                return None
            if not (0 <= a <= 23 and 0 <= b <= 23):
                return None
            raus |= set(range(a, b + 1)) if a <= b else (set(range(a, 24)) | set(range(0, b + 1)))
        else:
            try:
                v = int(stueck)
            except ValueError:
                return None
            if not 0 <= v <= 23:
                return None
            raus.add(v)
    return raus or None


def _fenster_min():
    try:
        v = float(os.environ.get("RUN_HEALTH_FENSTER_MIN") or 0)
        return v or None
    except (TypeError, ValueError):
        return None


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    slug = "lauf"
    if "--slug" in argv:
        slug = argv[argv.index("--slug") + 1]
    slug = "".join(c if (c.isalnum() or c in "-_") else "-" for c in slug) or "lauf"

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    workflow = os.environ.get("GITHUB_WORKFLOW", slug)
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    token = os.environ.get("GITHUB_TOKEN", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else None

    print("=== run_health.py ===")
    if not repo or not run_id:
        print("  ⏭️  Kein GitHub-Actions-Kontext (GITHUB_REPOSITORY/RUN_ID fehlen) — nichts zu tun.")
        return 0

    steps, api_fehler, lauf = [], None, None
    try:
        lauf = hole_lauf(repo, run_id, token)
    except Exception as e:                       # noqa: BLE001
        # Der Lauf-Kopf ist Beiwerk — sein Fehlen darf die Gesundheitsmeldung nicht kippen.
        print(f"  ⚠️  Lauf-Kopf nicht abrufbar: {str(e)[:80]}")
    try:
        steps = hole_steps(repo, run_id, token)
    except urllib.error.HTTPError as e:
        api_fehler = f"HTTP {e.code}" + (" — fehlt `permissions: actions: read`?"
                                         if e.code in (403, 404) else "")
    except Exception as e:
        api_fehler = str(e)[:120]

    eintrag = baue_eintrag(workflow, run_id, run_url, steps, api_fehler, lauf)

    # 22.09.2026: die eine Frage, die dieses Protokoll bisher nicht beantworten konnte —
    # wie viele Laeufe hat GitHub ueberhaupt erzeugt? S. `erzeugungs_bilanz`.
    bilanz = None
    wf_id = (lauf or {}).get("workflowId")
    if wf_id:
        try:
            bilanz = erzeugungs_bilanz(hole_erzeugte(repo, wf_id, token))
        except Exception as e:                   # noqa: BLE001
            print(f"  ⚠️  Erzeugungs-Bilanz nicht abrufbar: {str(e)[:80]}")

    os.makedirs(HEALTH_DIR, exist_ok=True)
    pfad = os.path.join(HEALTH_DIR, f"{slug}.json")
    datei = lade(pfad)
    letzter = (datei.get("runs") or [None])[0]
    laeufe = ([eintrag] + (datei.get("runs") or []))[:HISTORIE]
    datei = {"slug": slug, "workflow": workflow, "updatedAt": eintrag["ts"],
             "ok": eintrag["ok"],
             # Die gelieferte Taktung steht im Artefakt, nicht in einem Kommentar im Workflow.
             "kadenz": kadenz(laeufe,
                              soll_pro_tag=_soll_pro_tag(),
                              fenster_min=_fenster_min(),
                              stunden=_stunden()),
             # None heisst „nicht abgefragt/nicht abrufbar", nie „null Laeufe" — der
             # Unterschied ist der ganze Zweck dieser Zahl.
             "erzeugung": bilanz,
             "runs": laeufe}
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datei, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, pfad)

    text = zusammenfassen(eintrag)
    print("  " + text.replace("\n", "\n  "))
    print(f"  → {pfad}")
    if alarm_noetig(eintrag, letzter):
        tg_send(text)
    elif not eintrag["ok"] and not eintrag.get("apiError"):
        print("  🔁 Derselbe Fehler wie im letzten Lauf — kein zweiter Alarm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
