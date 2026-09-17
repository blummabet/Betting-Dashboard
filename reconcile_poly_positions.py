#!/usr/bin/env python3
"""
reconcile_poly_positions.py — manuelle Polymarket-Eingriffe erkennen (23.06.2026, Lucas).

Problem: Lucas verkauft eine Position direkt auf Polymarket. Unser System weiß nichts davon →
der Bet bleibt in wm_auto_bets_placed.json auf status='placed' → der 15-Min-Manage-Check alarmiert
weiter „verkaufen!", die Position hängt in Health/Offene-Positionen/Pending.

Lösung: die ECHTEN Wallet-Positionen (data-api /positions?user=<proxy>) gegen unsere Aufzeichnung
abgleichen. Hält die Wallet einen Token NICHT mehr UND das Spiel ist noch nicht fertig
(= kein Settlement, sondern echter Eingriff) → Bet als 'closed_manual' markieren, Alerts stoppen.
Echter realisierter P&L kommt aus dem Verkaufs-Trade (/trades?user=).

Reusable: nutzt der Auto-Abgleich (manage_wm_poly_positions) UND der Dashboard-„Geschlossen"-Button
(close-poly-position-Workflow). Polymarket ist geoblockt → läuft nur am Mac-Runner.
"""
from __future__ import annotations
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
# DATASET-AWARE (12.07.2026, Lucas: „MLS auf Polymarket") — MLS-Bets liegen in
# mls_auto_bets_placed.json; ein MLS-Reconcile darf nicht die WM-Bets anfassen.
import cocobet_dataset as D  # noqa: E402
AUTO_BETS_FILE = Path(str(D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json")))

POSITIONS_URL = "https://data-api.polymarket.com/positions?user={user}&sizeThreshold=0.01"
TRADES_URL    = "https://data-api.polymarket.com/trades?user={user}&limit=200"
HTTP_TIMEOUT  = 15
HELD_EPS      = 1.0   # Shares ≤ EPS = praktisch nicht mehr gehalten (Staub ignorieren)

# 🔴 14.09.2026 (Lucas: „wurde vorhin platziert … sollte dann auch im Cockpit auftauchen oder?
# und hoffentlich von alleine closen, weil die letzten 2 mmn haben nicht von allein geclosed").
#
# Sie haben nie von allein geschlossen — sie waren im Buch nie offen. Alle drei Liga-Auto-Bets
# tragen dasselbe Muster:
#
#     Ipswich–Liverpool    platziert 03:17:20.114   „verkauft" 03:17:20.587   (+0,5 s)
#     Betis–Real Madrid    platziert 13:42:58.593   „verkauft" 13:42:59.698   (+1,1 s)
#     Brentford–Chelsea    platziert 14:54:29.403   „verkauft" 14:54:30.207   (+0,8 s)
#
# Niemand klickt dreimal binnen einer Sekunde nach dem Kauf auf „verkaufen". Es war dieser
# Abgleich: er laeuft direkt nach dem Trade, fragt die Positions-API — und die hat den frischen
# Fill noch nicht indexiert. „Steht nicht in der Liste" wurde als „verkauft" gelesen.
#
# Die Folgen greifen ineinander: `soldAt` gesetzt -> das Cockpit zeigt die Position nicht mehr
# (`openBets` filtert auf `!soldAt`), `status != "placed"` -> der Auto-Sell-Manager fasst sie nie
# wieder an, `result` bleibt null -> es entsteht nie ein Ergebnis. Das Geld liegt derweil auf
# Polymarket. Eine unsichtbare, ungemessene, offene Position ist das Schlimmste von allem.
#
# Zwei Schranken, beide beweispflichtig:
#   1. Eine frische Wette wird NICHT geschlossen. „Noch nicht sichtbar" ist kein Verkauf.
#   2. Was faelschlich geschlossen wurde, wird zurueckgeholt, sobald die Wallet den Token
#      zeigt — die Wallet ist der Beleg, nicht unsere Vermutung von damals.
MIN_ALTER_MIN = float(os.environ.get("RECONCILE_MIN_ALTER_MIN") or 15)

# 🔴 16.09.2026 (Lucas: „im Cockpit wurde geschrieben, dass Chelsea gegen Brentford manuell
# geschlossen wurde. Das stimmt nicht, das ist immer noch offen. Ich greife den natuerlich
# nicht an.").
#
# Dieselbe Fehlbuchung wie am 14.09., aber die Schranke von damals konnte sie nicht fangen:
#
#     Brentford–Chelsea   gekauft 14.09. 14:54   „verkauft" 15.09. 14:45   (+24 h)
#
# 24 Stunden sind kein Indexierungs-Rennen. Die Positions-API hat den Token in DIESEM einen
# Lauf nicht geliefert — sieben Stunden spaeter stand er wieder drin: `liga_poly_balance.json`
# meldet um 22:00 Positionen im Wert von $10,12, und das sind genau die beiden offenen Tickets
# (Brentford 15,28 × 0,34 + Sevilla 18,97 × 0,27). Dieselbe API, anderer Lauf, anderes Ergebnis.
#
# Die eigentliche Fehlerklasse ist damit eine andere als beim ersten Mal: **eine ABWESENHEIT
# wurde als Beweis gelesen.** Der Token stand nicht in der Liste, ein Verkaufs-Trade liess sich
# auch nicht finden — und aus zwei Fehlanzeigen wurde eine Zustandsaenderung. Was fehlt, belegt
# nichts; eine Buchung braucht einen Beleg.
#
# Was das kostet, ist gemessen und nicht theoretisch: Seattle Sounders–Austin (MLS) wurde am
# 18.08. binnen einer Sekunde nach dem Kauf falsch geschlossen, war damit fuer den Verkaufs-
# Manager unsichtbar (der sieht nur `status == "placed"`), lief am 20.08. ins Spiel und verlor
# den vollen Einsatz. Von vier Positionen, die je in ein Spiel gelaufen sind, geht diese eine
# allein auf diese Fehlbuchung. Brentford–Chelsea stand bis heute genauso da — Anpfiff 18.09.
#
# Zwei Aenderungen, beide nach derselben Regel:
#   1. Geschlossen wird erst, wenn die Position ueber MEHRERE Laeufe fehlt (`MIN_FEHLT_MIN`).
#      Ein einzelner Lauf ist eine Momentaufnahme, kein Befund.
#   2. Zurueckgeholt wird nach BELEG statt nach Uhr: haelt die Wallet den Token und gibt es
#      keinen Verkaufs-Beleg, war die Buchung falsch — egal, wie lange sie her ist. Die alte
#      Zwei-Minuten-Regel beschrieb den Tathergang vom 14.09., nicht die Fehlerklasse.
MIN_FEHLT_MIN = float(os.environ.get("RECONCILE_MIN_FEHLT_MIN") or 60)
# 🔴 17.09.2026 (Lucas: „der Betfair-Cron sollte alle 10 min, tut er aber nicht — falls das
# irgendwo wichtig ist"). Es war hier wichtig, und schlimmer als gedacht: die Schranke oben stand
# gestern mit der Begruendung da, sie verlange „bei Laeufen alle 15 Minuten vier aufeinander-
# folgende Fehlanzeigen". Dieser Abgleich laeuft aber gar nicht im Betfair-Takt, sondern in
# `manage-liga-poly.yml` — Cron `0,30 10-21` plus ein Lauf um 08:00, also alle 30 Minuten und
# NUR zwischen 10 und 21 Uhr UTC.
#
# Damit reichten 60 Minuten tagsueber fuer zwei weitere Laeufe (gerade noch die Absicht), ueber
# Nacht aber gar nicht: ein Marker vom 21:00-Lauf ist beim 08:00-Lauf elf Stunden alt, und die
# Position waere auf EINE einzige neue Fehlanzeige hin geschlossen worden — genau das, was die
# Schranke verhindern sollte.
#
# Eine Zeitspanne ist eben kein Ersatz fuers Zaehlen, wenn die Laeufe Luecken haben. Also beides:
# die Luecke muss `MIN_FEHLT_MIN` ueberdauern UND in mindestens `MIN_FEHLT_LAEUFE` Laeufen
# beobachtet worden sein.
MIN_FEHLT_LAEUFE = int(os.environ.get("RECONCILE_MIN_FEHLT_LAEUFE") or 2)
# Und die Beobachtungen muessen eine KETTE sein, keine zwei Punkte mit einer Nacht dazwischen:
# reisst der Abstand zwischen zwei Fehlanzeigen weiter als das hier, faengt die Zaehlung von vorn
# an. 150 Minuten deckt den weitesten regulaeren Abstand dieses Workflows ab (der 08:00-Lauf steht
# allein, der naechste kommt um 10:00) und bricht die Kette ueber Nacht sicher.
MAX_KETTE_MIN = float(os.environ.get("RECONCILE_MAX_KETTE_MIN") or 150)


def _http_get(url: str):
    req = urllib.request.Request(
        url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  reconcile HTTP {url[:70]}…: {e}")
        return None


def _proxy_address() -> str | None:
    return (os.environ.get("POLY_FUNDER_ADDRESS")
            or os.environ.get("POLY_PROXY_ADDRESS") or "").strip() or None


def _rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("positions", "data", "trades", "results"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _tok(d: dict):
    return d.get("asset") or d.get("tokenId") or d.get("token_id") or d.get("token")


def _num(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def fetch_wallet_positions(proxy: str, getter=_http_get):
    """{tokenId: size} der aktuell gehaltenen Positionen, oder None bei API-Fehler.
    WICHTIG: None (Fehler) ≠ {} (gültig leer = Wallet hält nichts mehr). Der Aufrufer schließt
    nur bei einem ZUVERLÄSSIGEN Positions-Stand (None → nichts tun, sonst falsch-positiv)."""
    raw = getter(POSITIONS_URL.format(user=proxy))
    if raw is None:
        return None
    out = {}
    for row in _rows(raw):
        if not isinstance(row, dict):
            continue
        t = _tok(row)
        sz = _num(row, "size", "amount", "shares", "balance")
        if t and sz is not None:
            out[str(t)] = out.get(str(t), 0.0) + sz
    return out


def find_sell_trade(proxy: str, token_id: str, after_iso: str | None = None,
                    getter=_http_get) -> dict | None:
    """Jüngster SELL-Trade der Wallet auf token_id (nach after_iso) → {price, size, ts} oder None."""
    after_dt = None
    if after_iso:
        try:
            after_dt = datetime.fromisoformat(str(after_iso).replace("Z", "+00:00"))
        except Exception:
            after_dt = None
    best = None
    for tr in _rows(getter(TRADES_URL.format(user=proxy))):
        if not isinstance(tr, dict) or str(_tok(tr)) != str(token_id):
            continue
        side = str(tr.get("side") or tr.get("type") or "").upper()
        if not side.startswith("S"):   # nur SELL
            continue
        price = _num(tr, "price")
        size  = _num(tr, "size", "amount", "shares")
        ts = tr.get("timestamp") or tr.get("time") or tr.get("matchTime")
        ts_dt = None
        try:
            if ts is not None and (isinstance(ts, (int, float)) or str(ts).isdigit()):
                ts_dt = datetime.fromtimestamp(int(ts), timezone.utc)
            elif ts:
                ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            ts_dt = None
        if after_dt and ts_dt and ts_dt < after_dt:
            continue
        if price is None:
            continue
        cand = {"price": price, "size": size,
                "ts": ts_dt.isoformat() if ts_dt else None, "_dt": ts_dt}
        if best is None or (cand["_dt"] and best["_dt"] and cand["_dt"] > best["_dt"]):
            best = cand
    if best:
        best.pop("_dt", None)
    return best


def close_bet_manual(bet: dict, sell: dict | None, now_iso: str) -> dict:
    """Bet als manuell geschlossen markieren. P&L aus echtem Sell-Fill (shares×(sell−entry)),
    sonst None. Mutiert + gibt bet zurück."""
    bet["status"]     = "closed_manual"
    bet["soldAt"]     = now_iso
    bet["sellReason"] = "manuell auf Polymarket geschlossen"
    if sell and isinstance(sell.get("price"), (int, float)):
        sp = float(sell["price"])
        bet["sellPrice"] = round(sp, 4)
        entry  = bet.get("polyPrice")
        shares = bet.get("sharesEstimate") or sell.get("size")
        if isinstance(entry, (int, float)) and isinstance(shares, (int, float)):
            bet["pnl"] = round(shares * (sp - float(entry)), 2)
        bet["pnlSource"] = "manual_sell_trade"
    else:
        bet["sellPrice"] = None
        bet["pnl"] = None
        bet["pnlSource"] = "manual_unknown"
    return bet


def _alter_min(placed_iso, now_iso):
    """Alter einer Wette in Minuten. None, wenn unlesbar — dann wird nichts behauptet und die
    Zeile laeuft wie bisher weiter (keine stille Verhaltensaenderung fuer Altbestand)."""
    try:
        a = datetime.fromisoformat(str(placed_iso).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).total_seconds() / 60.0


def falsch_geschlossen(bet) -> bool:
    """Ist diese Schliessung UNBELEGT? REIN/testbar.

    Zwei Merkmale: als manuell geschlossen gebucht — und ohne jeden Verkaufs-Beleg (kein Preis,
    kein P&L). Mehr braucht es nicht, denn geprueft wird das nur dort, wo die Wallet den Token
    nachweislich HAELT (s. `zurueckholen`). Beides zusammen kann nur eines heissen: die Buchung
    war falsch.

    🔴 16.09.2026: hier stand zusaetzlich „binnen zwei Minuten nach dem Kauf". Das beschrieb den
    Tathergang vom 14.09. (Indexierungs-Rennen direkt nach dem Fill), nicht die Fehlerklasse.
    Brentford–Chelsea wurde 24 Stunden nach dem Kauf falsch geschlossen und fiel damit durch:
    die Wallet hielt den Token, das Buch sagte „verkauft", und niemand holte sie zurueck. Eine
    Regel, die an der Uhr haengt statt am Beleg, faengt nur den Fall, den man schon gesehen hat.
    """
    if bet.get("status") != "closed_manual":
        return False
    return bet.get("sellPrice") is None and bet.get("pnl") is None


def fehlt_lange_genug(bet: dict, now_iso: str) -> tuple:
    """Fehlt der Token lange genug fuer ein Urteil? REIN (mutiert nur den Marker am Bet).

    Gibt (darf_schliessen, text). Beim ERSTEN Fehlen wird `nichtGehaltenSeit` gesetzt und
    nichts getan; geschlossen wird erst, wenn die Luecke `MIN_FEHLT_MIN` ueberdauert hat. Der
    Marker steht am Bet und nicht in einer eigenen Datei — eine zweite Datei waere ein zweiter
    Zustand, der mit dem Buch auseinanderlaufen kann.

    Vorfall 16.09.2026: Brentford–Chelsea fehlte in EINEM Lauf um 14:45 und wurde geschlossen;
    um 22:00 meldete dieselbe API die Position wieder (Wallet-Positionen $10,12 = beide offenen
    Tickets). Bei Laeufen alle 15 Minuten haette diese Schranke vier aufeinanderfolgende
    Fehlanzeigen verlangt.
    """
    seit = bet.get("nichtGehaltenSeit")
    if not seit:
        bet["nichtGehaltenSeit"] = now_iso
        bet["nichtGehaltenLaeufe"] = 1
        bet["nichtGehaltenZuletzt"] = now_iso
        return (False, "zum ersten Mal nicht in den Positionen — ein Lauf ist kein Befund, "
                       "der naechste entscheidet")
    # Kette gerissen? Dann ist die alte Fehlanzeige keine Beobachtung von JETZT mehr.
    _lueck = _alter_min(bet.get("nichtGehaltenZuletzt") or seit, now_iso)
    if _lueck is not None and _lueck > MAX_KETTE_MIN:
        bet["nichtGehaltenSeit"] = now_iso
        bet["nichtGehaltenLaeufe"] = 1
        bet["nichtGehaltenZuletzt"] = now_iso
        return (False, "zwischen den beiden Fehlanzeigen lagen %.0f Min ohne Lauf — die Kette "
                       "faengt von vorn an" % _lueck)
    try:
        laeufe = int(bet.get("nichtGehaltenLaeufe") or 1) + 1
    except (TypeError, ValueError):
        laeufe = 2
    bet["nichtGehaltenLaeufe"] = laeufe
    bet["nichtGehaltenZuletzt"] = now_iso
    d = _alter_min(seit, now_iso)
    if d is None:
        # Unlesbarer Marker: neu setzen statt raten. Ein kaputter Zeitstempel darf keine
        # Schliessung ausloesen, aber auch nicht dauerhaft eine blockieren.
        bet["nichtGehaltenSeit"] = now_iso
        bet["nichtGehaltenLaeufe"] = 1
        bet["nichtGehaltenZuletzt"] = now_iso
        return (False, "Marker unlesbar — neu gesetzt")
    if d < MIN_FEHLT_MIN:
        return (False, "fehlt seit %.0f Min (noetig: %.0f)" % (d, MIN_FEHLT_MIN))
    if laeufe < MIN_FEHLT_LAEUFE:
        # Die Zeit allein reicht nicht: ueber Nacht laeuft dieser Abgleich elf Stunden gar nicht,
        # und dann waere „60 Minuten alt" nach EINER einzigen neuen Fehlanzeige erfuellt.
        return (False, "fehlt seit %.0f Min, aber erst in %d Lauf gesehen (noetig: %d)"
                       % (d, laeufe, MIN_FEHLT_LAEUFE))
    return (True, "")


def zurueckholen(bets: list, held: dict, now_iso: str | None = None) -> list:
    """Faelschlich geschlossene Wetten wieder oeffnen, wenn die Wallet den Token HAELT.

    Die Wallet ist der Beleg. Steht der Token mit Groesse in den echten Positionen, dann ist die
    Wette offen — egal, was ein frueherer Lauf ins Buch geschrieben hat. Ohne diesen Schritt
    bliebe der Schaden liegen: `reconcile` sieht nur `status == "placed"` und kommt an die
    fehlgebuchten Zeilen nie wieder heran.
    """
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    zurueck = []
    for bet in bets:
        if not falsch_geschlossen(bet):
            continue
        tok = str(bet.get("tokenId") or "")
        if not tok or (held or {}).get(tok, 0.0) <= HELD_EPS:
            continue
        bet["status"] = "placed"
        bet["soldAt"] = None
        bet["sellReason"] = None
        bet["sellPrice"] = None
        bet["pnl"] = None
        bet["pnlSource"] = None
        bet.pop("nichtGehaltenSeit", None)
        bet.pop("nichtGehaltenLaeufe", None)
        bet.pop("nichtGehaltenZuletzt", None)
        bet["reopenedAt"] = now_iso
        bet["reopenGrund"] = ("als manuell geschlossen gebucht, aber ohne jeden Verkaufs-Beleg "
                              "— und die Wallet haelt den Token. Die Positions-API hatte ihn in "
                              "dem Lauf nicht geliefert.")
        zurueck.append(bet)
        print(f"  ♻️  zurueckgeholt: {bet.get('home')}–{bet.get('away')} {bet.get('market')} — "
              f"die Wallet haelt den Token, die Wette lief die ganze Zeit.")
    return zurueck


def reconcile(bets: list, *, proxy: str, finished_keys: set | None = None,
              now_iso: str | None = None, getter=_http_get) -> list:
    """Gleicht 'placed'-Bets gegen die echten Wallet-Positionen ab. Token nicht mehr gehalten UND
    Spiel NICHT fertig (kein Settlement) → closed_manual + echter Sell-P&L. Gibt die Liste der
    geänderten Bets zurück. Wallet-Fetch leer/Fehler → nichts ändern (konservativ)."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    finished_keys = finished_keys or set()
    held = fetch_wallet_positions(proxy, getter=getter)
    if held is None:
        # API-Fehler (None ≠ leere Liste) → kein zuverlässiger Stand → NICHT schließen.
        print("  ⚠️  reconcile: Positions-API nicht erreichbar → übersprungen")
        return []
    changed = []
    changed += zurueckholen(bets, held, now_iso=now_iso)
    for bet in bets:
        if bet.get("status") != "placed":
            continue
        tok = str(bet.get("tokenId") or "")
        if not tok:
            continue
        if held.get(tok, 0.0) > HELD_EPS:
            # Wieder (oder immer noch) da → der Zaehler beginnt bei der naechsten Luecke von vorn.
            # Ohne dieses Loeschen summierte sich eine einzelne alte Fehlanzeige ueber Tage zu
            # einem „Befund", der nie einer war.
            bet.pop("nichtGehaltenSeit", None)
            bet.pop("nichtGehaltenLaeufe", None)
            bet.pop("nichtGehaltenZuletzt", None)
            continue   # noch gehalten → nichts tun
        # Ein Lauf ist eine Momentaufnahme. Erst wenn die Position ueber mehrere Laeufe fehlt,
        # ist das ein Befund — s. `fehlt_lange_genug` (Vorfall Brentford–Chelsea, 16.09.).
        weiter, wartetext = fehlt_lange_genug(bet, now_iso)
        if not weiter:
            print(f"  ⏳ {wartetext}: {bet.get('home')}–{bet.get('away')} {bet.get('market')}")
            continue
        alter = _alter_min(bet.get("placedAt"), now_iso)
        if alter is not None and alter < MIN_ALTER_MIN:
            # Der Fill ist juenger als die Indexierung der Positions-API. Hier zu schliessen
            # hiesse, eine gerade eroeffnete Position fuer verkauft zu erklaeren.
            print(f"  ⏳ zu frisch für ein Urteil ({alter:.1f} Min): {bet.get('home')}–"
                  f"{bet.get('away')} {bet.get('market')} — Position steht evtl. noch nicht "
                  f"in der Positions-API. Nächster Lauf entscheidet.")
            continue
        if bet.get("betKey") in finished_keys or bet.get("matchKey") in finished_keys:
            continue   # Spiel fertig → Settlement, NICHT als manueller Eingriff werten
        sell = find_sell_trade(proxy, tok, bet.get("placedAt"), getter=getter)
        close_bet_manual(bet, sell, now_iso)
        changed.append(bet)
        _pnl = bet.get("pnl")
        print(f"  🔁 manuell geschlossen erkannt: {bet.get('home')}–{bet.get('away')} "
              f"{bet.get('market')} · P&L "
              + (f"{_pnl:+.2f}€" if isinstance(_pnl, (int, float)) else "unbekannt"))
    return changed


def _load_finished_keys() -> set:
    """Match-Keys fertiger Spiele aus wm2026-data.json (Settlement ≠ manueller Eingriff)."""
    keys = set()
    try:
        wm = json.loads(Path(str(D.data_file())).read_text(encoding="utf-8"))
    except Exception:
        return keys
    for _g, gd in (wm.get("groups") or {}).items():
        for fx in (gd.get("fixtures") or []):
            st = str((fx.get("result") or {}).get("status") or "").upper()
            if st in ("FT", "AET", "PEN") and fx.get("home") and fx.get("away"):
                keys.add(f"{fx['home']}-{fx['away']}")
    return keys


def run(close_bet_key: str | None = None) -> int:
    """Auto-Abgleich (close_bet_key=None) ODER gezieltes Schließen EINES Bets (Button-Workflow)."""
    proxy = _proxy_address()
    if not proxy:
        print("❌ POLY_FUNDER_ADDRESS fehlt — reconcile übersprungen")
        return 1
    if not AUTO_BETS_FILE.exists():
        print("ℹ️  keine wm_auto_bets_placed.json — nichts zu tun")
        return 0
    data = json.loads(AUTO_BETS_FILE.read_text(encoding="utf-8"))
    bets = data.get("bets", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    if close_bet_key:
        target = [b for b in bets if b.get("betKey") == close_bet_key and b.get("status") == "placed"]
        if not target:
            print(f"ℹ️  betKey {close_bet_key} nicht offen — nichts zu tun")
            return 0
        for b in target:
            sell = find_sell_trade(proxy, str(b.get("tokenId") or ""), b.get("placedAt"))
            close_bet_manual(b, sell, now_iso)
            print(f"  ✅ Button-Schließung: {b.get('home')}–{b.get('away')} {b.get('market')}")
        changed = target
    else:
        changed = reconcile(bets, proxy=proxy, finished_keys=_load_finished_keys(), now_iso=now_iso)
    if changed:
        data["updatedAt"] = now_iso
        AUTO_BETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 {len(changed)} Bet(s) als manuell geschlossen markiert → {AUTO_BETS_FILE.name}")
    else:
        print("✅ reconcile: keine manuellen Eingriffe gefunden")
    return 0


if __name__ == "__main__":
    import sys
    _bk = None
    for a in sys.argv[1:]:
        if a.startswith("--close="):
            _bk = a.split("=", 1)[1]
    raise SystemExit(run(close_bet_key=_bk))
