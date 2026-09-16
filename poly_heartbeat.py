#!/usr/bin/env python3
"""
poly_heartbeat.py — taeglicher Status-Snapshot des Auto-Traders auf den Trades-Channel.

🔴 15.09.2026 (Lucas: „die koennten wir auch reparieren, dann macht sie auch Sinn, wenn sie 1x am
Tag weiterhin kommt"). Die Karte vom 15.09. war in jeder Zahl falsch, und zwar aus EINEM Grund:

    PLACED_FILE = BASE / "wm_auto_bets_placed.json"

Sie las genau EINEN Datensatz — den der WM, die seit Juli vorbei ist. Alles, was seitdem auf
derselben Wallet passiert, war unsichtbar:

    „Letzter Trade: Frankreich vs Spanien — vor 1565.4h"   die WM, 65 Tage her
    „Heute: 0 Bets"                                        UNiTY esports lief um 06:24 desselben Tages
    „Open Exposure: $5.50 (1 Pos.)"                        drei offene Positionen auf der Wallet

Eine taegliche Karte, deren Zahlen man nicht glauben kann, ist schlimmer als keine: sie erzeugt
Vertrauen, wo keines hingehoert. Vier Fehlerklassen sind hier geschlossen:

  1. EIN Datensatz statt aller       → PO.DATENSATZ_PRAEFIXE, dieselbe Liste wie beim Risiko-Deckel
  2. Eigene Offen-Definition         → PO.ist_offen / PO.wallet_exposure (`resolved` schreibt niemand)
  3. Abgeschriebene Schwellen        → dieselbe cocobet_config wie auto_wm_poly_trigger.py
  4. Gruen, das luegt                → „AN" heisst nur, dass der Schalter an ist. Wie lange nichts
                                        passiert ist und WAS das Angebot hergibt, steht jetzt dabei.

Env: TELEGRAM_TOKEN, TELEGRAM_TRADES_CHAT_ID
Cron: .github/workflows/daily-heartbeat.yml — 06:00 UTC
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import poly_offen as PO

BASE = Path(__file__).resolve().parent

try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}


def _cfg(section: str, key: str, default):
    """Derselbe Config-Lookup wie in auto_wm_poly_trigger.py — NICHT abgeschrieben."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default


DAILY_BET_CAP           = _cfg("trade", "daily_bet_cap",             8)
DAILY_STAKE_CAP_USDC    = _cfg("trade", "daily_stake_cap_usdc",   50.0)
ADAPTIVE_DAILY_FRACTION = _cfg("trade", "adaptive_daily_fraction", 0.40)
MAX_OPEN_EXPOSURE_USDC  = _cfg("trade", "max_open_exposure_usdc", 80.0)
MIN_VOL                 = _cfg("trade", "min_vol_usdc",           1500)

# Der Shortlist-Auto-Play teilt sich die Wallet mit dem Trader und hat einen EIGENEN, weiteren
# Deckel. Beide sind echt — die Karte nennt deshalb beide, statt sich einen auszusuchen.
try:
    from shortlist_auto_bet import MAX_OFFEN as WALLET_DECKEL
except Exception:
    WALLET_DECKEL = 100.0

BALANCE_FILE     = BASE / "wm_poly_balance.json"
KILL_SWITCH_FILE = BASE / "wm_kill_switch.json"

# Ab so vielen Tagen ohne Trade sagt die Karte es ausdruecklich.
STILLE_TAGE = float(os.environ.get("HEARTBEAT_STILLE_TAGE") or 2)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TRADES_CHAT_ID = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()


# ── Lesen ──────────────────────────────────────────────────────────────────────────────────
def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def alle_wetten(base_dir, praefixe=None) -> tuple:
    """(Wetten aller Datensaetze mit `_datensatz`-Stempel, unlesbare Dateien). REIN bis aufs Lesen.

    Der Stempel ist der Punkt: ohne ihn stuende in der Karte „letzter Trade" ohne die Information,
    WELCHES System ihn gemacht hat — und genau das war am 15.09. die Frage.
    """
    raus, unlesbar = [], []
    for pfx in (praefixe or PO.DATENSATZ_PRAEFIXE):
        name = f"{pfx}auto_bets_placed.json"
        p = Path(base_dir) / name
        if not p.exists():
            continue
        d = load_json(p, False)
        if d is False or not isinstance(d, dict):
            unlesbar.append(name)
            continue
        for b in (d.get("bets") or []):
            if isinstance(b, dict):
                z = dict(b)
                z["_datensatz"] = pfx.rstrip("_")
                raus.append(z)
    return raus, unlesbar


# ── Urteile ────────────────────────────────────────────────────────────────────────────────
def alter_text(sekunden) -> str:
    """Menschliche Zeitspanne. REIN/testbar.

    „vor 1565.4h" stand wirklich so in der Karte. Niemand rechnet das im Kopf in Tage um, und
    genau deshalb ist 65 Tagen Stille niemandem aufgefallen.
    """
    try:
        s = float(sekunden)
    except (TypeError, ValueError):
        return "unbekannt"
    if s != s:            # NaN — unbekannt ist die Wahrheit, nicht „gerade eben"
        return "unbekannt"
    if s < 0:
        return "gerade eben"
    m = s / 60.0
    if m < 60:
        return "vor %d Min" % int(m)
    h = m / 60.0
    if h < 48:
        return "vor %.1f h" % h
    return "vor %d Tagen" % int(h / 24)


# Zwei Systeme auf EINER Wallet — und sie koennen unabhaengig voneinander schweigen.
FAMILIEN = {"Trader": ("wm", "liga", "mls"), "Shortlist": ("shortlist",)}


def letzter_trade(bets, datensaetze=None) -> dict | None:
    """Die zuletzt platzierte Wette. `datensaetze` schraenkt auf eine Familie ein. REIN/testbar."""
    mit_ts = [b for b in (bets or [])
              if isinstance(b, dict) and str(b.get("placedAt") or "")
              and (datensaetze is None or b.get("_datensatz") in datensaetze)]
    return max(mit_ts, key=lambda b: str(b.get("placedAt"))) if mit_ts else None


def letzte_je_familie(bets) -> dict:
    """{Familie: letzte Wette | None}. REIN/testbar.

    🔴 Warum getrennt: die Karte heisst „Auto-Trader Heartbeat", aggregiert aber zwei Systeme.
    Wuerde nur die juengste Wette ueberhaupt dastehen, verdeckte der Shortlist-Auto-Play (der
    taeglich setzt) dauerhaft, dass der Pinnacle-Trader seit 65 Tagen nichts getan hat — also
    genau die Tatsache, wegen der diese Karte ueberhaupt auffiel.
    """
    return {name: letzter_trade(bets, ds) for name, ds in FAMILIEN.items()}


def heute(bets, tag) -> tuple:
    """(Anzahl, Summe) der heute platzierten Wetten ueber alle Datensaetze. REIN/testbar."""
    n, s = 0, 0.0
    for b in (bets or []):
        if isinstance(b, dict) and str(b.get("placedAt") or "")[:10] == tag:
            n += 1
            try:
                s += float(b.get("stake") or 0)
            except (TypeError, ValueError):
                pass
    return n, round(s, 2)


# Ab diesem Alter gilt eine Preisdatei nicht mehr als laufender Datensatz, sondern als ruhend.
RUHT_AB_STUNDEN = float(os.environ.get("HEARTBEAT_RUHT_AB_H") or 48)


def _stand_alter_h(prices, jetzt):
    """Alter der Preisdatei in Stunden. None = unlesbarer Zeitstempel. REIN."""
    ts = (prices or {}).get("generatedAt") if isinstance(prices, dict) else None
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        # Die WM-Datei traegt ein anderes Format ("19.07.2026 20:41 UTC") — kein Grund zu werfen.
        try:
            t = datetime.strptime(str(ts).replace(" UTC", ""), "%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (jetzt - t).total_seconds() / 3600.0


def angebot(prices, jetzt=None) -> dict:
    """Was ein Datensatz ueberhaupt hergibt. REIN/testbar.

    Kein Urteil ueber Kante — nur das Angebot. Ein Trader, der nichts findet, weil es nichts zu
    finden gibt, ist etwas anderes als einer, der kaputt ist; die Karte konnte das bisher nicht
    unterscheiden und zeigte in beiden Faellen ein gruenes ACTIVE.
    """
    fx = (prices or {}).get("allFixtures") or [] if isinstance(prices, dict) else []
    fx = [f for f in fx if isinstance(f, dict)]
    mit_pinn = [f for f in fx if f.get("hasPinnacle")]
    genug = [f for f in mit_pinn if (f.get("vol") or 0) >= MIN_VOL]
    return {"fixtures": len(fx), "mitPinnacle": len(mit_pinn), "genugVolumen": len(genug),
            "alterH": _stand_alter_h(prices, jetzt or datetime.now(timezone.utc))}


def stille_zeile(letzte_iso, jetzt, tage=STILLE_TAGE) -> str:
    """Sagt AUSDRUECKLICH, wenn lange nichts passiert ist. REIN/testbar. '' = alles frisch."""
    if not letzte_iso:
        return "seit jeher kein Trade platziert"
    try:
        t = datetime.fromisoformat(str(letzte_iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    d = (jetzt - t).total_seconds() / 86400.0
    return "seit %d Tagen kein Trade" % int(d) if d >= tage else ""


def angebots_zeilen(je_datensatz) -> list:
    """Das Angebot je Datensatz, ruhende getrennt. REIN/testbar.

    🔴 Warum je Datensatz und nicht „der aktive": `cocobet_dataset.active_dataset()` liest die
    Umgebungsvariable COCOBET_DATASET, und die Heartbeat-Workflow setzte sie nie — Default „wm".
    Die Karte las also die Preisdatei einer im Juli beendeten WM (1 Fixture, Stand 19.07.), waehrend
    liga (57) und mls (16) taeglich frisch danebenlagen. Eine Flaeche, die von einer Variablen
    abhaengt, an die jemand denken muss, geht genau dann falsch, wenn niemand hinsieht. Also
    haengt sie an keiner mehr: gelesen wird, was da ist.
    """
    laufend, ruhend = [], []
    for name, a in sorted((je_datensatz or {}).items()):
        if not a or not a.get("fixtures"):
            continue
        alt = a.get("alterH")
        spiel = "Spiel" if a["fixtures"] == 1 else "Spiele"
        if alt is not None and alt >= RUHT_AB_STUNDEN:
            ruhend.append("%s (%s)" % (name, alter_text(alt * 3600)))
            continue
        stand = "Stand unbekannt" if alt is None else alter_text(alt * 3600)
        laufend.append("%-5s %3d %s · %d mit Pinnacle · %d ueber $%d  <i>(%s)</i>"
                       % (name, a["fixtures"], spiel, a["mitPinnacle"], a["genugVolumen"],
                          int(MIN_VOL), stand))
    if not laufend:
        laufend.append("kein laufender Datensatz mit Preisen — Angebot unbekannt")
    if ruhend:
        laufend.append("<i>ruht: %s</i>" % ", ".join(ruhend))
    return laufend


def durchgerutscht(bets, jetzt) -> tuple:
    """Die zwei Zustaende, in denen eine Position still zum Totalrisiko wird. REIN/testbar.

    🔴 16.09.2026 (Lucas: „wichtig ist nur, dass wir schauen, dass der automatische Close
    funktioniert und das Spiel nicht startet, weil dann waere es ja im Worst Case Totalverlust").

    Der Pre-Match-Close funktioniert — fuenfmal gemessen gefeuert, jeweils 0,5–1,1 h vor
    Anpfiff. Genau deshalb faellt auf, WANN er nicht feuert: er sieht nur `status == "placed"`.

      1. `ins_spiel` — offen, und der Anpfiff ist vorbei. Das ist der Schaden selbst.
      2. `unbelegt_zu` — als manuell geschlossen gebucht, aber ohne jeden Verkaufs-Beleg. Das
         ist die Vorstufe: eine solche Zeile ist fuer den Verkaufs-Manager unsichtbar und faellt
         aus jeder Offen-Statistik (`poly_offen.TERMINAL_STATUS` kennt `closed_manual`).

    Gemessen, warum beides hier steht: Seattle Sounders–Austin wurde am 18.08. binnen einer
    Sekunde nach dem Kauf so fehlgebucht, lief am 20.08. ins Spiel und verlor den vollen
    Einsatz — die einzige der vier je ins Spiel gelaufenen Positionen, die nicht auf den
    (laengst reparierten) Anpfiff-Zeitfehler vom 19.08. zurueckgeht. `reconcile_poly_positions`
    holt solche Zeilen seit dem 16.09. automatisch zurueck; diese Karte sagt trotzdem Bescheid,
    denn ein Selbstheilungs-Mechanismus, der still arbeitet, ist einer, den niemand prueft.
    """
    ins_spiel, unbelegt_zu = [], []
    for b in (bets or []):
        if not isinstance(b, dict):
            continue
        st = str(b.get("status") or "").lower()
        ko = b.get("kickoff") or b.get("matchDate")
        t = None
        try:
            if ko:
                t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            t = None
        if st == "placed" and t is not None and t < jetzt:
            ins_spiel.append(b)
        elif (st == "closed_manual" and b.get("sellPrice") is None
              and b.get("pnl") is None):
            unbelegt_zu.append(b)
    return ins_spiel, unbelegt_zu


def _kurz(b) -> str:
    return "%s–%s %s" % (b.get("home", "?"), b.get("away", "?"), b.get("market", ""))


def bericht(*, jetzt, schalter_an, kill_grund, balance, exp, bets, unlesbar, a) -> str:
    """Die ganze Karte. REIN/testbar — keine Datei, kein Netz."""
    tag = jetzt.strftime("%Y-%m-%d")
    adaptiv = min(DAILY_STAKE_CAP_USDC, balance * ADAPTIVE_DAILY_FRACTION)
    n_heute, stake_heute = heute(bets, tag)
    je_fam = letzte_je_familie(bets)
    # Der Kopf gehoert dem Trader — die Karte ist SEIN Heartbeat.
    _t = je_fam.get("Trader")
    stille = stille_zeile(_t.get("placedAt") if _t else None, jetzt)
    if stille:
        stille = "Trader: " + stille

    kopf = "🟢 AN" if schalter_an else "🛑 PAUSIERT"
    if stille:
        kopf += " · " + stille

    z = ["🤖 <b>CocoBet · Auto-Trader Heartbeat</b>",
         "<i>%s UTC</i>" % jetzt.strftime("%d.%m.%Y %H:%M"),
         "",
         "<b>Schalter:</b> %s" % kopf]
    if not schalter_an and kill_grund:
        z.append("  <i>Grund: %s</i>" % kill_grund)

    z += ["",
          "💼 <b>Bankroll</b>",
          "  Balance:        $%7.2f" % balance,
          "  Offen:          $%7.2f (%d Pos.)" % (exp["offen"], exp["n"]),
          "  Deckel:         $%.0f Trader · $%.0f Wallet" % (MAX_OPEN_EXPOSURE_USDC, WALLET_DECKEL)]
    # Je Datensatz aufschluesseln, sobald mehr als einer Geld bindet — sonst sieht die Summe aus
    # wie die eines Systems, und genau diese Verwechslung war der ganze Fehler.
    if len(exp.get("je") or {}) > 1:
        for datei, (s, c) in sorted(exp["je"].items()):
            z.append("     · %-28s $%6.2f (%d)" % (datei.replace("_auto_bets_placed.json", ""), s, c))

    z += ["",
          "📅 <b>Heute</b>",
          "  Bets:           %d / %d" % (n_heute, DAILY_BET_CAP),
          "  Stake:          $%7.2f / $%.2f" % (stake_heute, adaptiv),
          "",
          "⚡ <b>Letzter Trade</b>"]
    for name in FAMILIEN:
        lt = je_fam.get(name)
        if not lt:
            z.append("  %-10s noch keiner" % (name + ":"))
            continue
        titel = (lt.get("match") or "%s vs %s" % (lt.get("home", "?"), lt.get("away", "?")))
        try:
            t = datetime.fromisoformat(str(lt["placedAt"]).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            wann = alter_text((jetzt - t).total_seconds())
        except (TypeError, ValueError, KeyError):
            wann = "unbekannt"
        z.append("  %-10s %s — %s <i>(%s)</i>"
                 % (name + ":", titel, wann, lt.get("_datensatz") or "?"))

    z += ["", "🎯 <b>Angebot</b>"] + ["  " + x for x in angebots_zeilen(a)]

    warn = []
    if unlesbar:
        # Eine kaputte Datei heisst NICHT „keine offenen Positionen" — dann sind die Zahlen
        # oben unvollstaendig, und das muss dastehen.
        warn.append("⚠️ Nicht lesbar: %s — die Zahlen oben sind unvollstaendig"
                    % ", ".join(unlesbar))
    if exp.get("unlesbar"):
        warn.append("⚠️ Wett-Datei(en) unlesbar: %s" % ", ".join(exp["unlesbar"]))
    if adaptiv < 11:
        warn.append("⚠️ Adaptiver Deckel nur $%.2f — Balance aufladen" % adaptiv)
    if exp["offen"] >= WALLET_DECKEL * 0.9:
        warn.append("⚠️ Wallet-Deckel fast voll ($%.0f/$%.0f)" % (exp["offen"], WALLET_DECKEL))
    if balance < 10:
        warn.append("🚨 Balance kritisch niedrig: $%.2f" % balance)
    _rein, _zu = durchgerutscht(bets, jetzt)
    for b in _rein[:4]:
        warn.append("🚨 Ins Spiel gelaufen, nicht verkauft: %s — der Pre-Match-Close hat diese "
                    "Position nie gesehen" % _kurz(b))
    for b in _zu[:4]:
        warn.append("⚠️ Als geschlossen gebucht, aber ohne Verkaufs-Beleg: %s — fuer den "
                    "Verkaufs-Manager unsichtbar; der naechste Abgleich holt sie zurueck, "
                    "falls die Wallet den Token haelt" % _kurz(b))
    if warn:
        z += ["", "<b>Hinweise</b>"] + ["  " + w for w in warn]

    z += ["", "<i>Dashboard: blummabet.github.io/Betting-Dashboard/season-finish-v2.html</i>"]
    return "\n".join(z)


PREIS_DATENSAETZE = ("wm", "liga", "mls")


def alle_angebote(base_dir, jetzt) -> dict:
    """{Datensatz: angebot()} ueber alle Handels-Datensaetze. Haengt an keiner Umgebungsvariable."""
    raus = {}
    for name in PREIS_DATENSAETZE:
        d = load_json(Path(base_dir) / ("%s_poly_prices.json" % name), None)
        if isinstance(d, dict):
            raus[name] = angebot(d, jetzt)
    return raus


def main() -> int:
    jetzt = datetime.now(timezone.utc)
    bets, unlesbar = alle_wetten(str(BASE))
    kill = load_json(KILL_SWITCH_FILE, {"enabled": True}) or {"enabled": True}
    bal = load_json(BALANCE_FILE, {}) or {}
    msg = bericht(
        jetzt=jetzt,
        schalter_an=bool(kill.get("enabled", True)),
        kill_grund=kill.get("reason", ""),
        balance=float(bal.get("usdc") or 0),
        exp=PO.wallet_exposure(str(BASE)),
        bets=bets,
        unlesbar=unlesbar,
        a=alle_angebote(str(BASE), jetzt),
    )
    print(msg)
    if not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print("\n(Telegram skip — Token/Chat-ID fehlt)")
        return 0
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN
    data = json.dumps({"chat_id": TRADES_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("\n%s" % ("✓ gesendet" if json.loads(r.read()).get("ok") else "✗ Telegram-Fehler"))
    except Exception as e:
        print("\n✗ Telegram-Fehler: %s" % e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
