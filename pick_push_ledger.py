#!/usr/bin/env python3
"""pick_push_ledger.py — Schattenbuch für den Card-Push (30.08.2026, Lucas).

Lucas wollte die ABWÄGEN im Public-Push reduzieren und vermutete den Markt als Ursache
(„1X2 ist schwächer"). Gemessen trennt nicht der Markt, sondern das GEGENSIGNAL — ein ABWÄGEN,
zu dem mindestens ein Signal widerspricht, verliert; eines ohne Widerspruch gewinnt deutlich
(n=47, 78,7% Treffer, ROI +40,0%, einseitige 95%-Untergrenze +19,3%). Der Filter dazu steht in
pick_announce_state.push_ok.

Dieses Modul ist die Gegenprobe zu genau diesem Schnitt. Es schreibt JEDEN announce-fähigen
Pick mit — den gesendeten wie den aussortierten — und rechnet beide ab. Damit gilt:

  · Der Schnitt kann sich nicht selbst bestätigen. Wären die Aussortierten in Wahrheit gut,
    stünde es hier, statt unsichtbar zu bleiben.
  · Die öffentliche Bilanz kann sagen, was WIRKLICH gepostet wurde, statt es aus der heutigen
    Regel zu rekonstruieren. Ein später geänderter Filter schreibt sonst rückwirkend die
    Vergangenheit um.
  · Die Frage landet in freigabe.py und wird dort nach denselben Regeln beurteilt wie jede
    andere Schublade — ROI-Untergrenze über null, und zwar getrennt für „gepusht" und
    „aussortiert".

Aufbau: Schlüssel `{dataset}|{pick_key}|{market}`. Der Zustand (Verdikt, Markt, Quote,
Signalzahlen, push ja/nein) wird bis zum ANPFIFF mitgeführt und dort eingefroren — danach nie
wieder angefasst. Der Grund ist gemessen: über 14 Tage blieben 87% der Picks in ihrem Zustand,
aber 13% kippten noch (4 von sauber zu Gegensignal, 2 zurück). Zwei Konsequenzen:

  · Beim ersten Sehen einzufrieren wäre falsch — das wäre nicht der Stand, mit dem der Pick
    ins Rennen ging. Nach Anpfiff weiterzuschreiben wäre auch falsch — dann wanderte ein Pick
    nachträglich in die Schublade, die gerade besser aussieht. Also: letzter Stand VOR Anpfiff,
    genau wie betfair_track_record.capture es für die Börsen-Signale hält.
  · Die Vorab-Messung (+40% ROI für „ohne Gegensignal") las den Stand bei ABRECHNUNG. Der
    Filter entscheidet aber vorher. Wo ein Gegensignal erst spät auftaucht, ist der Filter in
    der Praxis durchlässiger als die Messung nahelegt — mit welchem Abschlag, sagt genau
    dieses Buch. Bis dahin ist +40% eine Obergrenze, keine Erwartung.

Läuft je Datensatz (COCOBET_DATASET), schreibt {prefix}pick_push_ledger.json.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
import pick_announce_state as S

BASE = Path(__file__).resolve().parent
KEEP = 4000        # Zeilen je Datensatz; älteste fliegen raus


def ledger_file() -> Path:
    return BASE / f"{D.prefix()}pick_push_ledger.json"


def _now():
    return datetime.now(timezone.utc)


def _load(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _ko_map(wm: dict) -> dict:
    """pick_key → Anpfiff. Die Picks selbst tragen keinen; ohne ihn kann nicht abgerechnet
    werden, wann ein Spiel vorbei ist."""
    out = {}
    for gkey, g in (wm.get("groups") or {}).items():
        for fx in (g.get("fixtures") or []):
            if fx.get("home") and fx.get("away"):
                out[f"{gkey}-{fx.get('matchday')}-{fx['home']}-{fx['away']}"] = fx.get("kickoff") or fx.get("date")
    for kf in (wm.get("koFixtures") or []):
        if kf.get("home") and kf.get("away"):
            out[f"KO-{kf.get('round')}-{kf['home']}-{kf['away']}"] = kf.get("kickoff") or kf.get("date")
    return out


def _alle_picks(wm: dict):
    """(pick_key, pick) über alle Picks — auch die auf bereits angepfiffenen Spielen.
    iter_pick_units liefert nur KOMMENDE; fürs Abrechnen brauchen wir die vergangenen."""
    for k, arr in (wm.get("picks") or {}).items():
        for p in (arr or []):
            yield k, p


def erfassen(ledger: list, wm: dict, dataset: str, now=None) -> list:
    """Announce-fähige Picks auf KOMMENDEN Spielen eintragen bzw. fortschreiben.

    iter_pick_units liefert ausschliesslich Spiele vor Anpfiff — damit ist das Einfrieren
    automatisch: sobald angepfiffen ist, taucht der Pick hier nicht mehr auf und die Zeile
    bleibt auf ihrem letzten Vor-Anpfiff-Stand stehen."""
    now = now or _now()
    idx = {r["k"]: i for i, r in enumerate(ledger)}
    out = [dict(r) for r in ledger]
    for u in S.iter_pick_units(wm, now, alle=True):
        k = f"{dataset}|{u['id']}"
        pos, neg = u.get("sigPos") or 0, u.get("sigNeg") or 0
        stand = {
            "verdict": u["verdict"], "push": bool(u.get("push")),
            "sigPos": pos, "sigNeg": neg, "gegensignal": neg > 0 or pos == 0,
            "conv": u.get("convictionScore"), "kickoff": u.get("kickoff"),
            "standAm": now.isoformat(),
        }
        if isinstance(u.get("odds"), (int, float)):
            stand["odds"] = u["odds"]
        i = idx.get(k)
        if i is None:
            r = {"k": k, "dataset": dataset, "pickKey": u["pick_key"], "markt": u["market"],
                 "odds": u.get("odds"), "gesehenAm": now.isoformat(),
                 "status": "offen", "win": None, "settledAt": None}
            r.update(stand)
            idx[k] = len(out)
            out.append(r)
        elif out[i].get("status") == "offen":
            # Nur solange offen: eine abgerechnete Zeile wird nie mehr angefasst.
            out[i].update(stand)
    return out


# 14.09.2026 (Lucas: „darum kommt beim Ausrechnen was anderes raus als der User kriegt, aber die
# Push die am selben Spieltag rausgeht hat doch auch ne Quote … wieso nehmen wir nicht die?").
#
# Er hat recht, und es war verdrehter als gedacht — ZWEI Verschiebungen in entgegengesetzte
# Richtungen:
#
#   Datum zu frueh: `gesehenAm` ist der Zeitpunkt, an dem der Pick ZUERST IN DEN DATEN stand —
#     bis zu 27 Tage vor Anpfiff. Verschickt wird er aber erst mit der Morning-Card seines
#     Spieltags (die nimmt nur das Tagesfenster). 15 von 44 Liga-Zeilen standen dadurch in einer
#     anderen Kalenderwoche, als sie die Follower erreicht haben.
#   Quote zu spaet: abgerechnet wurde mit dem letzten Vor-Anpfiff-Stand, im Median 2,6 Stunden
#     vor Kickoff — also SPAETER als die Nachricht, die der Leser am Morgen hatte.
#
# ⚠️ Die naheliegende Quelle ist die falsche. Das Announce-Buch (`*_pick_announce_state.json`)
# sieht aus wie ein Sendebuch, ist aber keines: sowohl der Digest als auch notify_new_picks
# markieren dort STUMM alle kommenden Picks als „bekannt", damit nichts doppelt rausgeht — auch
# Spiele in drei Wochen. Ein Zeitstempel dort heisst „gesehen", nicht „gesendet".
#
# Die echten Sendebuecher sind zwei, und beide sind exakt:
#   · `{ds}_telegram_sent.json` — „morning_card:<Tag>" → Sendezeit. DAS ist der Weg, auf dem ein
#     Card-Pick die Follower erreicht, und der Tag ergibt sich aus dem Anpfiff (gleiches Fenster
#     wie telegram_wm._in_slate).
#   · das `gesendet`-Fach im Announce-Buch — der Intraday-Nachzuegler, den notify_new_picks
#     WIRKLICH geschickt hat (seit heute mitgeschrieben; nicht rekonstruierbar, also erst ab jetzt).
#
# Ohne Eintrag in einem der beiden wird NICHT geraten: die Zeile bleibt ohne `gesendetAm` und
# zaehlt in keiner Woche mit. Ein Pick fuer den 10.10. ist am 13.09. schlicht noch nicht gesendet
# — ihn trotzdem als Push der KW37 zu buchen, war der ganze Fehler.
PUSH_ODDS_TOLERANZ_H = 6.0
SLATE_START_H = 8   # Morning-Card-Fenster: [Tag 08:00 UTC, +1 Tag 08:00 UTC)


def slate_datum(kickoff) -> str | None:
    """Der Tag, an dessen Morning-Card dieses Spiel gehoert. REIN/testbar.

    Spiegel von telegram_wm._in_slate — ein Spiel um 01:00 UTC gehoert zum VORTAG, sonst waeren
    die MLS-Spaetspiele in der Karte des falschen Tages (und die MLS-Karten gehen um 21 Uhr UTC).
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    try:
        t = _dt.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_tz.utc)
    return (t.astimezone(_tz.utc) - _td(hours=SLATE_START_H)).date().isoformat()


def _stunden_seit(ts, now):
    """Stunden zwischen `ts` und jetzt. None, wenn unlesbar — dann wird nichts behauptet."""
    from datetime import datetime as _dt, timezone as _tz
    try:
        t = _dt.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_tz.utc)
    return (now - t).total_seconds() / 3600.0


def sendezeit_nachtragen(ledger: list, karten: dict, intraday: dict, dataset: str, now=None) -> list:
    """`gesendetAm` + `pushOdds` eintragen. REIN/testbar.

    `karten`   = {"morning_card:2026-09-05": "2026-09-05T21:11:09Z", …}  (Sendebuch des Digests)
    `intraday` = {"<pickKey>|<Markt>": "<ISO>"}                          (wirklich geschickte Nachzuegler)

    Die Sendezeit steht fest und wird auch rueckwirkend nachgetragen. Die Sende-QUOTE nur,
    solange der Lauf nah genug dran ist (`PUSH_ODDS_TOLERANZ_H`) — was ein Pick im Moment der
    Karte kostete, steht nirgends nachtraeglich. Aeltere Zeilen bekommen `oddsQuelle`
    =„vorAnpfiff" und sagen damit, dass ihre Quote eine andere Frage beantwortet. Eine
    Sende-Quote zu erfinden, die niemand gemessen hat, waere schlimmer als eine ehrlich
    beschriftete zweitbeste.
    """
    now = now or _now()
    aus = []
    for r in ledger:
        r = dict(r)
        if r.get("dataset") != dataset or not r.get("push"):
            aus.append(r)
            continue
        if not r.get("gesendetAm"):
            pid = str(r.get("k") or "").split("|", 1)[-1]
            ts = (intraday or {}).get(pid)
            quelle = "intraday"
            if not ts:
                tag = slate_datum(r.get("kickoff"))
                ts = (karten or {}).get("morning_card:%s" % tag) if tag else None
                quelle = "morning_card"
            if ts:
                r["gesendetAm"] = ts
                r["sendeQuelle"] = quelle
        if not r.get("pushOdds"):
            alter = _stunden_seit(r.get("gesendetAm"), now)
            if alter is not None and 0 <= alter <= PUSH_ODDS_TOLERANZ_H \
                    and isinstance(r.get("odds"), (int, float)) and r["odds"] > 1.0:
                r["pushOdds"] = r["odds"]
                r["pushOddsAm"] = now.isoformat()
                r["oddsQuelle"] = "senden"
            elif alter is not None and alter > PUSH_ODDS_TOLERANZ_H:
                r.setdefault("oddsQuelle", "vorAnpfiff")
        aus.append(r)
    return aus


def abrechnungs_quote(r):
    """Die Quote, mit der diese Zeile abgerechnet wird. REIN/testbar.

    Vorrang hat die Sende-Quote — sie ist die, die der Leser vor sich hatte. Fehlt sie
    (Historie), faellt es auf die Vor-Anpfiff-Quote zurueck; `oddsQuelle` sagt, welche es war.
    """
    for feld in ("pushOdds", "odds"):
        o = r.get(feld)
        if isinstance(o, (int, float)) and o > 1.0:
            return float(o)
    return None


def abrechnen(ledger: list, wm: dict, dataset: str, now=None) -> list:
    """Offene Zeilen aus dem Ergebnis am Pick nachtragen. VOID zählt weder als Treffer noch
    als Fehlschlag — die Zeile wird stillgelegt, nicht als Verlust gebucht."""
    now = now or _now()
    ko = _ko_map(wm)
    res, schatten, quote = {}, {}, {}
    for pk, p in _alle_picks(wm):
        kk = f"{dataset}|{pk}|{p.get('market') or ''}"
        res[kk] = p.get("result")
        schatten[kk] = p.get("shadowResult")
        if isinstance(p.get("odds"), (int, float)):
            quote[kk] = p["odds"]
    out = []
    for r in ledger:
        r = dict(r)
        if r.get("status") == "offen" and r.get("dataset") == dataset:
            e = res.get(r["k"])
            # 🔴 14.09.2026 (Lucas: „wieso sind nur 2 Liga Picks abgerechnet von 8?").
            #
            # Die 8/2 selbst waren harmlos — sechs Anpfiffe lagen in der Zukunft, Liga pusht bis
            # zu 27 Tage voraus. Beim Nachrechnen fiel aber etwas anderes auf: 16 Zeilen hingen
            # DAUERHAFT auf „offen", obwohl ihre Spiele laengst abgepfiffen waren, vier davon
            # gepusht (2 Treffer, 2 Nieten, −0,97 Einheiten).
            #
            # Grund: die Engine hat sie NACH dem Push auf NOBET herabgestuft, und fuer NOBET
            # schreibt resolve_wm_picks bewusst nie `result`, nur `shadowResult`. Die Abrechnung
            # fragte den HEUTIGEN Datensatz — also erfuhr sie nie ein Ergebnis. Der Kanal stand
            # damit auf „100 % aus n=2", waehrend vier entschiedene Pushes ungemessen danebenlagen.
            #
            # Das verstoesst gegen den Satz, an dem alle Push-Buecher haengen: **wer pusht, misst
            # den Push.** Was rausging, ist raus; dass das Modell es spaeter anders sieht, aendert
            # nichts an der Wette, die ein Leser gespielt hat. Diese Zeile haelt den Stand von vor
            # dem Anpfiff fest (`verdict`) — genau dafuer wird er eingefroren.
            #
            # Kein zweites Regelwerk: `shadowResult` kommt aus demselben `evaluate_pick` auf
            # demselben Endstand wie `result`. War die Zeile schon BEIM PUSH ein NOBET, bleibt es
            # dabei — dann war es nie eine Wette.
            if e not in ("WIN", "LOSS", "VOID") and str(r.get("verdict") or "").upper() != "NOBET":
                _sch = schatten.get(r["k"])
                if _sch in ("WIN", "LOSS", "VOID"):
                    e = _sch
                    r["ergebnisQuelle"] = "schatten"   # nachvollziehbar, nicht stillschweigend
            if r.get("odds") is None and quote.get(r["k"]) is not None:
                r["odds"] = quote[r["k"]]          # Quote wird erst spät final
            if e in ("WIN", "LOSS"):
                r.update(status="abgerechnet", win=(e == "WIN"), settledAt=now.isoformat())
            elif e == "VOID":
                r.update(status="void", settledAt=now.isoformat())
            if not r.get("kickoff"):
                r["kickoff"] = ko.get(r["pickKey"])
        out.append(r)
    out.sort(key=lambda r: r.get("gesehenAm") or "")
    return out[-KEEP:]


def wurde_gepusht(ledger: list, dataset: str, pick_key: str, market: str):
    """Wurde dieser Pick wirklich gesendet? None = steht nicht im Buch (Alt-Pick von vor dem
    Schattenbuch) — dann muss der Aufrufer auf die alte Regel zurückfallen statt zu raten."""
    for r in (ledger or []):
        if r.get("k") == f"{dataset}|{pick_key}|{market}":
            return bool(r.get("push"))
    return None


# ── Auswertung für freigabe.py ──────────────────────────────────────────────────────────
def schubladen(ledger=None):
    """{name: {renditen, letzter}} — Renditen JE PICK zur gesetzten Quote.

    Kein CLV: die Cards führen keinen je Pick. freigabe.bewerte stuft eine Schublade ohne CLV
    bewusst nicht frei — auch die hier nicht. Das ist Absicht: der Schnitt darf sichtbar
    besser dastehen, ohne allein deshalb „freigegeben" zu heißen."""
    if ledger is None:
        ledger = []
        for pre in ("", "liga_", "mls_"):
            ledger += _load(BASE / f"{pre}pick_push_ledger.json")
    grp = {}
    for r in ledger:
        if r.get("status") != "abgerechnet" or r.get("verdict") != "ABWÄGEN":
            continue
        o = r.get("odds")
        if not isinstance(o, (int, float)) or o <= 1:
            continue
        name = "ABWÄGEN · gepusht" if r.get("push") else "ABWÄGEN · aussortiert"
        g = grp.setdefault(name, {"renditen": [], "letzter": None})
        g["renditen"].append((o - 1.0) if r.get("win") else -1.0)
        s = r.get("settledAt")
        if s and (g["letzter"] is None or s > g["letzter"]):
            g["letzter"] = s
    return grp


def main():
    ds = D.active_dataset()
    f = D.data_file()
    if not f.exists():
        print(f"○ {f} nicht da"); return
    wm = json.loads(f.read_text(encoding="utf-8"))
    path = ledger_file()
    led = _load(path)
    vorher = len(led)
    import pick_announce_state as _S
    _st = _S.load() or {}
    # _load erzwingt eine Liste (das Ledger ist eine) — das Sendebuch ist ein Objekt.
    try:
        _karten = json.loads((BASE / f"{D.prefix()}telegram_sent.json").read_text(encoding="utf-8"))
        _karten = _karten if isinstance(_karten, dict) else {}
    except Exception:
        _karten = {}
    led = abrechnen(sendezeit_nachtragen(erfassen(led, wm, ds), _karten,
                                         _st.get("gesendet") or {}, ds), wm, ds)
    path.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    offen = sum(1 for r in led if r.get("status") == "offen" and r.get("dataset") == ds)
    ab = sum(1 for r in led if r.get("status") == "abgerechnet" and r.get("dataset") == ds)
    gepusht = sum(1 for r in led if r.get("dataset") == ds and r.get("push"))
    print(f"pick_push_ledger [{ds}]: {vorher} → {len(led)} Zeilen · offen {offen} · abgerechnet {ab} "
          f"· gepusht {gepusht}/{sum(1 for r in led if r.get('dataset') == ds)}")


if __name__ == "__main__":
    main()
