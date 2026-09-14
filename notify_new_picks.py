#!/usr/bin/env python3
"""notify_new_picks.py — Intraday-„Neuer Pick"-Telegram-Noti (03.07.2026, Lucas).

Der Morgen-Digest postet die Slate einmal. Späte Steam-Picks, die danach reinkommen
(z.B. Ghana am Nachmittag), erreichten keinen Follower mehr. Dieses Skript läuft bei jedem
Daten-Refresh und meldet KOMPAKT nur die Picks, die seit dem heutigen Digest neu dazukamen —
in den Public-Channel, TikTok-/Compliance-safe (keine Quoten/€).

Zusammenspiel mit dem Digest (siehe [[pick_announce_state]]):
  • Digest markiert beim Senden die ganze Slate + setzt lastDigestDate=heute.
  • Vor dem heutigen Digest: dieses Skript setzt STUMM die Basis (kein Send) → der Digest
    bleibt Erst-Ankündiger, kein Doppel-Post der Tages-Slate.
  • Nach dem Digest: nur echte Nachzügler werden gemeldet.

Dataset-aware (WM/MLS/Liga). Env:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID   — Public-Channel (wie der Digest)
  SKIP_TELEGRAM=true                 — nur Vorschau, kein Send
  FORCE_SEND=true                    — Digest-Gate ignorieren (Test/manuell)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
import pick_announce_state as S
from tg_safe import safe_flag

BASE    = Path(__file__).parent
WM_FILE = D.data_file()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SKIP_TELEGRAM  = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"
FORCE_SEND     = os.environ.get("FORCE_SEND", "").lower() == "true"

# Wie viele neue Picks einzeln zeigen, bevor „… und N weitere" (gegen Wall-of-Text).
MAX_LIST = 6

_LEAGUE_LABEL = {"wm": "WM 2026", "mls": "MLS", "liga": "Top-Liga"}


def tg_send(text: str) -> bool:
    if SKIP_TELEGRAM or not (TELEGRAM_TOKEN and CHAT_ID):
        print("ℹ️  Telegram-Send geskippt (SKIP_TELEGRAM / Token / ChatID) — Vorschau:")
        print(text)
        return not (TELEGRAM_TOKEN and CHAT_ID) is False  # Vorschau gilt als OK
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text,
                       "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Send fehlgeschlagen: {e}")
        return False


def _conv_word(u: dict) -> str:
    """Kurzes, quotenloses Konfidenz-Wort (TikTok-safe)."""
    cs = u.get("convictionScore")
    if u.get("verdict") == "BET":
        return "🟢 Klarer Pick" if isinstance(cs, int) and cs >= 8 else "🟢 Pick"
    return "🟡 Auf dem Zettel"   # ABWÄGEN


_WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _kickoff_wien(u: dict, jetzt=None) -> str:
    """Anpfiff in Wiener Zeit — mit Datum, sobald es NICHT heute ist. REIN/testbar.

    🔴 14.09.2026 (Lucas: „aber sorry die Spiele sind doch nicht heute"). In einer Nachricht
    standen „Inter – Udinese · 20:45" (heute) und „AS Roma – Inter · 18:00" — das zweite Spiel
    ist am 19.09., also fuenf Tage spaeter. Eine nackte Uhrzeit unter der Ueberschrift „Neuer
    Pick" liest sich als heute Abend. Im PUBLIC-Channel.
    """
    ko = u.get("kickoff")
    if not ko:
        return ""
    try:
        from datetime import timedelta
        dt = datetime.fromisoformat(str(ko).replace("Z", "+00:00")) + timedelta(hours=2)
        heute = ((jetzt or datetime.now(timezone.utc)) + timedelta(hours=2)).date()
    except Exception:
        return ""
    if dt.date() == heute:
        return " · " + dt.strftime("%H:%M")
    return " · %s %s" % (_WOCHENTAG[dt.weekday()], dt.strftime("%d.%m. %H:%M"))


def heutiger_slate(units, jetzt=None) -> list:
    """Nur die Picks, deren Spiel ins HEUTIGE Kartenfenster faellt. REIN/testbar.

    Der Sinn dieser Noti steht in ihrer eigenen Beschreibung: Nachzuegler fuer HEUTE, die der
    Morgen-Digest nicht mehr erwischt hat. Genommen wurde bisher alles Kommende — auch Spiele in
    zwei Wochen. Die kommen an ihrem Spieltag ohnehin ueber die Morning-Card; die Noti hat sie
    also ein zweites Mal angekuendigt, mit einer Uhrzeit ohne Datum.

    Fenster wie bei der Morning-Card: [Tag 08:00 UTC, +1 Tag 08:00) — ein Spiel um 00:30 gehoert
    zum Abend davor (vgl. pick_push_ledger.slate_datum, dieselbe Rechnung).
    """
    import pick_push_ledger as _PPL
    jetzt = jetzt or datetime.now(timezone.utc)
    heute = _PPL.slate_datum(jetzt.isoformat())
    aus = []
    for u in (units or []):
        tag = _PPL.slate_datum(u.get("kickoff"))
        if tag and tag == heute:
            aus.append(u)
    return aus


def build_message(new_units: list) -> str:
    league = _LEAGUE_LABEL.get(D.active_dataset(), "")
    n = len(new_units)
    head = "🆕 <b>Neuer Pick</b>" if n == 1 else f"🆕 <b>{n} neue Picks</b>"
    if league:
        head += f" · {league}"
    lines = [head, ""]
    for u in new_units[:MAX_LIST]:
        rl = f" <i>({u['roundLabel']})</i>" if u.get("roundLabel") else ""
        lines.append(
            # 🔴 10.09.2026 — DERSELBE BUG, GEGEN DEN ES SEIT DEM 25.07. `tg_safe` GIBT.
            # `homeFlag` ist bei den Klub-Datensaetzen kein Emoji, sondern ein komplettes
            # <img src="https://media.api-sports.io/…">-Tag (fuers Dashboard gedacht). Telegram
            # erlaubt im HTML-Modus kein <img> und antwortet mit HTTP 400 „Unsupported start
            # tag" — die Nachricht scheitert LAUTLOS. `telegram_wm`, `detect_wm_sharp_moves` und
            # `telegram_streak_watch` benutzen `safe_flag` seitdem; dieser Sender nie.
            # Folge: der Cards-Public-Push hat fuer liga/mls vermutlich noch nie zugestellt —
            # nur fuer die WM mit echten Laenderflaggen, und die ist seit dem 19.07. vorbei.
            f"{safe_flag(u['homeFlag'])} <b>{u['homeName']} – {u['awayName']}</b>{rl}{_kickoff_wien(u)}"
        )
        lines.append(f"   {_conv_word(u)} · {u['market']}")
    if n > MAX_LIST:
        lines.append(f"\n… und {n - MAX_LIST} weitere im Dashboard")
    lines.append("\n<i>Kam nach dem Morgen-Update rein.</i>")
    return "\n".join(lines)


def main() -> None:
    if not WM_FILE.exists():
        print(f"❌ {WM_FILE} nicht gefunden"); sys.exit(0)
    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    state = S.load()
    units = list(S.iter_pick_units(wm, now))
    by_id = {u["id"]: u for u in units}
    current_ids = set(by_id)

    digest_ran_today = (state.get("lastDigestDate") == today)

    # Vor dem heutigen Digest (oder allererster Lauf): stumm Basis setzen, NICHT senden.
    if not (digest_ran_today or FORCE_SEND):
        S.mark(state, current_ids, now.isoformat())
        state["seeded"] = True
        S.save(state)
        print(f"○ Digest heute noch nicht gelaufen ({state.get('lastDigestDate')}) — "
              f"Basis gesetzt ({len(current_ids)} Picks), kein Send.")
        return

    new_ids = [i for i in current_ids if not S.is_announced(state, i)]
    if not new_ids:
        print(f"○ Keine neuen Picks seit dem Digest ({len(current_ids)} bekannt).")
        return

    # Neue zuerst nach Anpfiff sortieren (früheste zuerst)
    alle_neu = sorted((by_id[i] for i in new_ids), key=lambda u: u.get("kickoff") or "~")
    new_units = heutiger_slate(alle_neu, now)
    spaeter = len(alle_neu) - len(new_units)

    # ⭐ Die spaeteren werden trotzdem als bekannt VERMERKT — sonst gelten sie bei jedem Lauf
    # wieder als neu und die Noti wuerde sie stuendlich anbieten. Gesendet sind sie nicht, also
    # auch nicht `gesendet=True`: das Push-Buch darf sie nicht als Push buchen. Ihre Ankuendigung
    # uebernimmt die Morning-Card an ihrem Spieltag — genau wie bisher.
    if spaeter:
        print(f"○ {spaeter} Pick(s) für spätere Spieltage — nicht gesendet (die Morning-Card "
              f"kündigt sie an ihrem Tag an), nur als bekannt vermerkt.")
        S.mark(state, [u["id"] for u in alle_neu if u not in new_units], now.isoformat())
        S.save(state)

    if not new_units:
        print("○ Kein Nachzügler für heute — nichts zu senden.")
        return

    msg = build_message(new_units)
    ok = tg_send(msg)
    print(f"{'✅' if ok else '❌'} Neuer-Pick-Noti: {len(new_units)} Pick(s)")
    if ok:
        # 14.09.2026: `gesendet=True` — DIESE Zeilen sind wirklich rausgegangen (anders als die
        # stumme Basis oben). Das Push-Buch bucht sie dadurch in die richtige Woche.
        S.mark(state, [u["id"] for u in new_units], now.isoformat(), gesendet=True)
        S.save(state)


if __name__ == "__main__":
    main()
