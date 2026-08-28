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


def baue_eintrag(workflow, run_id, run_url, steps, api_fehler=None):
    """Ein Lauf als Zeile fuer die Historie.

    `apiError` ist wichtiger als es aussieht: konnten wir die Steps NICHT abfragen, heisst das
    „wir wissen es nicht" — und genau das muss dastehen, nicht „alles gruen". Fehlende
    Information ist keine Erlaubnis.
    """
    fails = fehlerhafte_steps(steps)
    return {
        "ts": _jetzt(),
        "workflow": workflow,
        "runId": str(run_id or ""),
        "runUrl": run_url,
        "nSteps": len(steps),
        "apiError": api_fehler,
        "ok": (api_fehler is None and not fails),
        "failures": [{"job": j, "step": s, "conclusion": c} for j, s, c, _ in fails],
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

    steps, api_fehler = [], None
    try:
        steps = hole_steps(repo, run_id, token)
    except urllib.error.HTTPError as e:
        api_fehler = f"HTTP {e.code}" + (" — fehlt `permissions: actions: read`?"
                                         if e.code in (403, 404) else "")
    except Exception as e:
        api_fehler = str(e)[:120]

    eintrag = baue_eintrag(workflow, run_id, run_url, steps, api_fehler)

    os.makedirs(HEALTH_DIR, exist_ok=True)
    pfad = os.path.join(HEALTH_DIR, f"{slug}.json")
    datei = lade(pfad)
    letzter = (datei.get("runs") or [None])[0]
    laeufe = ([eintrag] + (datei.get("runs") or []))[:HISTORIE]
    datei = {"slug": slug, "workflow": workflow, "updatedAt": eintrag["ts"],
             "ok": eintrag["ok"], "runs": laeufe}
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
