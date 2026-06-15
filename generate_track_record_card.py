#!/usr/bin/env python3
"""
generate_track_record_card.py — Track-Record-Card für TikTok/Telegram

Liest wm2026-data.json, rechnet KPIs (ROI, Hit-Rate, CLV, P&L),
baut HTML via tiktok_card_templates.track_record_card,
rendert PNG via Playwright/Chromium und postet (optional) nach Telegram-Trades.

Stake-Normalisierung: €10/Pick (gleich wie wm2026-tracking.js).

Trigger-Logik (optional via env):
  • Falls TRACK_RECORD_MIN_RESOLVED gesetzt: nur wenn n_resolved >= Wert posten
  • Falls track_record_state.json existiert: nur wenn seit letzter Post mind. N neue resolved

Env:
  TELEGRAM_TOKEN, TELEGRAM_TRADES_CHAT_ID — für Posting
  SKIP_TELEGRAM=true                     — nur HTML/PNG bauen, kein Send
  FORCE=true                             — Trigger-Logik ignorieren
"""

import json
import os
import sys
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
OUTPUT_DIR  = BASE / "daily-tiktok"
STATE_FILE  = BASE / "track_record_state.json"
OUTPUT_DIR.mkdir(exist_ok=True)

STAKE_EUR = 10
MIN_RESOLVED_TO_POST   = int(os.environ.get("TRACK_RECORD_MIN_RESOLVED", "5"))
MIN_NEW_SINCE_LAST     = int(os.environ.get("TRACK_RECORD_MIN_NEW", "3"))
FORCE                  = os.environ.get("FORCE", "").lower() == "true"
SKIP_TELEGRAM          = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TRADES_CHAT_ID = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_kpis(wm: dict) -> dict:
    """Berechnet KPIs aus wm2026-data.json picks."""
    all_picks = []
    for mk, plist in (wm.get("picks") or {}).items():
        for p in plist:
            parts = mk.split("-", 3)
            if len(parts) < 4:
                continue
            gkey, md, home, away = parts
            # Fixture-Datum für Sortierung der Equity-Kurve
            fxd = None
            fxt = None
            for fx in (wm.get("groups", {}).get(gkey, {}).get("fixtures") or []):
                if fx["home"] == home and fx["away"] == away:
                    fxd = fx.get("date")
                    fxt = fx.get("time", "23:59")
                    break
            all_picks.append({**p, "_date": fxd, "_time": fxt})

    total    = len(all_picks)
    bet_n    = sum(1 for p in all_picks if p.get("verdict") == "BET")
    resolved = [p for p in all_picks if p.get("result") is not None]
    won      = [p for p in resolved if p.get("result") == "won"]
    lost     = [p for p in resolved if p.get("result") == "lost"]
    push     = [p for p in resolved if p.get("result") == "push"]

    decided  = len(resolved) - len(push)
    hit_rate = round(len(won) / decided * 100) if decided > 0 else 0

    pnl_eur = sum(((p.get("odds") or 1) - 1) * STAKE_EUR for p in won) - len(lost) * STAKE_EUR
    roi_pct = (pnl_eur / (len(resolved) * STAKE_EUR) * 100) if resolved else 0.0

    clv_picks = [p for p in resolved if isinstance(p.get("clvPP"), (int, float))]
    avg_clv = sum(p["clvPP"] for p in clv_picks) / len(clv_picks) if clv_picks else None

    # Genauigkeits-Verlauf (TikTok-safe, 15.06.2026): KEINE €-Equity mehr, sondern
    # kumulativer Netto-Treffer-Verlauf (richtig +1 / falsch −1) chronologisch.
    # Zeigt denselben Trend (Form der Prognosen) ohne Geld/Glücksspiel-Signal.
    sortable = [p for p in resolved if p.get("_date")]
    sortable.sort(key=lambda p: (p["_date"], p.get("_time") or "23:59"))
    cum = 0
    equity = []
    for p in sortable:
        if p["result"] == "won":
            cum += 1
        elif p["result"] == "lost":
            cum -= 1
        equity.append(cum)

    return {
        "total":     total,
        "bet":       bet_n,
        "resolved":  len(resolved),
        "won":       len(won),
        "lost":      len(lost),
        "push":      len(push),
        "hit_rate":  hit_rate,
        "pnl_eur":   round(pnl_eur, 2),
        "roi_pct":   round(roi_pct, 1),
        "avg_clv":   round(avg_clv, 1) if avg_clv is not None else None,
        "equity":    equity,
    }


def render_png(html_path: Path) -> Path | None:
    png_path = html_path.with_suffix(".png")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️  Playwright fehlt — nur HTML wird erzeugt")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 360, "height": 640},
                                     device_scale_factor=2)
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            page.locator(".card").screenshot(path=str(png_path))
            browser.close()
        return png_path
    except Exception as e:
        print(f"⚠️  Render failed: {e}")
        return None


def tg_send_photo(png: Path, caption: str = "") -> bool:
    if SKIP_TELEGRAM or not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print(f"ℹ️  Telegram-Send geskippt (SKIP_TELEGRAM / Token / ChatID)")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    # Multipart upload
    boundary = "----CocoBetBoundary"
    body_parts = []
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{TRADES_CHAT_ID}\r\n".encode())
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode())
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n".encode())
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{png.name}\"\r\nContent-Type: image/png\r\n\r\n".encode())
    body_parts.append(png.read_bytes())
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(body_parts)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode())
            return bool(j.get("ok"))
    except Exception as e:
        print(f"❌ TG-Photo failed: {e}")
        return False


def main():
    if not WM_FILE.exists():
        print("❌ wm2026-data.json fehlt"); sys.exit(1)
    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    k = compute_kpis(wm)

    print(f"📊 Track-Record:")
    print(f"   Total {k['total']}  Resolved {k['resolved']}  Won {k['won']}  Lost {k['lost']}")
    print(f"   Hit-Rate {k['hit_rate']}%  ROI {k['roi_pct']:+.1f}%  P&L €{k['pnl_eur']:+.2f}  CLV {k['avg_clv']}")

    # Trigger-Logik
    if not FORCE:
        if k["resolved"] < MIN_RESOLVED_TO_POST:
            print(f"ℹ️  {k['resolved']} resolved < {MIN_RESOLVED_TO_POST} — kein Post")
            return
        state = _load(STATE_FILE, {})
        last_resolved = state.get("lastResolved", 0)
        if k["resolved"] - last_resolved < MIN_NEW_SINCE_LAST:
            print(f"ℹ️  Nur {k['resolved'] - last_resolved} neue seit letztem Post (min {MIN_NEW_SINCE_LAST}) — kein Post")
            return

    now_local = datetime.now(timezone(timedelta(hours=2)))   # Wien-Zeit grob
    stand = f"Stand: {now_local.strftime('%d.%m.%y · %H:%M')}"

    from tiktok_card_templates import track_record_card
    html = track_record_card(
        roi_pct        = k["roi_pct"],
        hit_rate_pct   = k["hit_rate"],
        total_picks    = k["total"],
        resolved_picks = k["resolved"],
        won            = k["won"],
        lost           = k["lost"],
        push           = k["push"],
        pnl_eur        = k["pnl_eur"],
        avg_clv_pp     = k["avg_clv"],
        stake_eur      = STAKE_EUR,
        equity_curve_points = k["equity"],
        period_label   = "WM 2026 · Gruppenphase",
        stand_label    = stand,
    )

    ts = now_local.strftime("%Y%m%d_%H%M")
    html_path = OUTPUT_DIR / f"track_record_{ts}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"✅ HTML: {html_path.name}")

    png_path = render_png(html_path)
    if png_path:
        # TikTok-safe (15.06.2026): keine €/ROI/P&L — Prognose-Genauigkeit statt Geld.
        caption = (
            f"📊 <b>CocoBet Prognose-Genauigkeit</b>\n"
            f"{k['hit_rate']}% richtig · {k['resolved']}/{k['total']} Prognosen ausgewertet"
            + (f" · Ø Vorhersage-Wert {k['avg_clv']:+.1f}pp" if k['avg_clv'] is not None else "")
        )
        ok = tg_send_photo(png_path, caption)
        if ok:
            print(f"✅ Telegram gesendet")
            _save(STATE_FILE, {
                "lastPost":     datetime.now(timezone.utc).isoformat(),
                "lastResolved": k["resolved"],
                "lastROI":      k["roi_pct"],
            })


if __name__ == "__main__":
    main()
