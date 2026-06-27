#!/usr/bin/env python3
"""
generate_bilanz_card.py — Spieltag-Bilanz-Card (Ergebnis-Promo) erzeugen.

Baut aus aufgelösten Card-Picks (wm2026-data.json) eine HTML-Bilanz-Card im
CocoBet-Stil (tiktok_card_templates.bilanz_card) — Trefferquote + Spiele mit
Flagge, Endstand und ✅/❌/↩️ pro Pick. Wiederverwendbar pro Spieltag.

Render zu PNG: wie die anderen Cards via Playwright
  (generate_daily_tiktok.render_to_png) — SF Pro + Farb-Emoji-Flaggen.

Run:
  python3 generate_bilanz_card.py                 # alle beendeten Spiele
  python3 generate_bilanz_card.py --matchday 1    # nur MD1
  python3 generate_bilanz_card.py --png           # zusätzlich PNG rendern
Output: <today>_bilanz.html (+ .png) im aktuellen Verzeichnis.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from tiktok_card_templates import bilanz_card
from resolve_wm_picks import evaluate_pick

FINISHED = {"FT", "AET", "PEN"}

# 3-Letter-Code → Flaggen-Emoji (WM-2026-Teilnehmer + gängige Quali-Teams)
FLAG = {
 "ARG":"🇦🇷","AUS":"🇦🇺","AUT":"🇦🇹","BEL":"🇧🇪","BIH":"🇧🇦","BRA":"🇧🇷","CAN":"🇨🇦",
 "CIV":"🇨🇮","COD":"🇨🇩","COL":"🇨🇴","CPV":"🇨🇻","CRO":"🇭🇷","CUW":"🇨🇼","CZE":"🇨🇿",
 "DZA":"🇩🇿","ECU":"🇪🇨","EGY":"🇪🇬","ENG":"🏴","ESP":"🇪🇸","FRA":"🇫🇷","GER":"🇩🇪",
 "GHA":"🇬🇭","HTI":"🇭🇹","IRN":"🇮🇷","IRQ":"🇮🇶","JOR":"🇯🇴","JPN":"🇯🇵","KOR":"🇰🇷",
 "MAR":"🇲🇦","MEX":"🇲🇽","NED":"🇳🇱","NOR":"🇳🇴","NZL":"🇳🇿","PAN":"🇵🇦","POR":"🇵🇹",
 "PRY":"🇵🇾","QAT":"🇶🇦","SAU":"🇸🇦","SCO":"🏴","SEN":"🇸🇳","SUI":"🇨🇭","SWE":"🇸🇪",
 "TUN":"🇹🇳","TUR":"🇹🇷","URU":"🇺🇾","USA":"🇺🇸","UZB":"🇺🇿","ZAF":"🇿🇦",
}


def build_games(wm: dict, matchday: int | None = None) -> tuple[list, int, int, int]:
    """Liefert (games, wins, losses, push) aus beendeten Spielen mit Picks."""
    games, W, L, P = [], 0, 0, 0
    fixtures = []
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            fixtures.append(fx)
    fixtures.sort(key=lambda f: (f.get("matchday", 0), f.get("kickoff", "")))
    picks = wm.get("picks") or {}
    for fx in fixtures:
        if matchday is not None and fx.get("matchday") != matchday:
            continue
        res = fx.get("result") or {}
        if res.get("status") not in FINISHED or res.get("home_score") is None:
            continue
        hs, as_ = res["home_score"], res["away_score"]
        h, a = fx["home"], fx["away"]
        mk = f"{[k for k,v in (wm.get('groups') or {}).items() if fx in v.get('fixtures',[])][0]}-{fx['matchday']}-{h}-{a}"
        marks = []
        for p in picks.get(mk, []):
            if p.get("voidReason") or p.get("trackingExcluded"):
                continue
            out = evaluate_pick(p.get("market", ""), hs, as_)
            if out == "WIN": marks.append("W"); W += 1
            elif out == "LOSS": marks.append("L"); L += 1
            elif out == "VOID": marks.append("P"); P += 1
        if not marks:
            continue
        games.append({"home_flag": FLAG.get(h, "🏳️"), "home": h, "score": f"{hs}:{as_}",
                      "away": a, "away_flag": FLAG.get(a, "🏳️"), "marks": marks})
    return games, W, L, P


def main() -> int:
    args = sys.argv[1:]
    md = None
    if "--matchday" in args:
        md = int(args[args.index("--matchday") + 1])
    wm = json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
    games, W, L, P = build_games(wm, md)
    if not games:
        print("⚠️  Keine beendeten Spiele mit aufgelösten Picks gefunden.")
        return 1
    dec = W + L
    pct = f"{round(100*W/dec)}%" if dec else "—"
    rl = []
    rl.append(f"<b>{W} Siege</b>")
    if L: rl.append(f"{L} daneben")
    if P: rl.append(f"{P} Cashback")
    record_line = " · ".join(rl)
    series = f"SPIELTAG {md}" if md else "BILANZ"
    html = bilanz_card(pct, record_line, games, series_tag=series,
                       sub_detail=f"{W} von {dec}")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = BASE / f"{today}_bilanz.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out.name} — {pct} ({W}W/{L}L/{P}P) · {len(games)} Spiele")
    if "--png" in args:
        try:
            from generate_daily_tiktok import render_to_png
            png = render_to_png(out)
            print(f"   → {png.name if png else 'PNG-Render fehlgeschlagen'}")
        except Exception as e:
            print(f"   ⚠️  PNG-Render nicht möglich: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
