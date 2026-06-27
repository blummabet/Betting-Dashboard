#!/usr/bin/env python3
"""
prototype_steam_picks.py — PROTOTYP für Lucas' echtes Modell (14.06.2026).

Kein Fair-Value-Modell. Trigger = PINNACLE-BEWEGUNG (Opening → jetzt). Eine Seite fällt
spürbar (z.B. 1,90 → 1,70) = Sharp Money rein → das ist der Pick, zur AKTUELLEN Quote.
Danach die Bestätigungs-Litanei:
  • Ziehen die Soft-Books nach (Move marktweit bestätigt) ODER hinken sie nach (= Value)?
  • Hinkt Polymarket nach (= ausführbarer Edge auf der gesteamten Seite)?
  • Stützen die anderen Signale die Richtung des Drops — oder widersprechen sie?

ISOLIERT: liest nur wm2026-data.json, schreibt nur den Report. Ändert NICHTS am Live-System
(keine Picks, keine Quoten, keine Trades). Nur um zu SEHEN, welche Picks der Ansatz erzeugt.

Quelle der Steam-Schwelle: dein Steam-Lag-Backtest 01.06. → Sweet Spot 3-5pp (+14% ROI).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "wm2026-data.json"
REPORT = BASE / "steam_picks_report.md"

MOVE_TRIGGER_PP = 3.0      # ab hier gilt ein Move als Steam (Backtest-Sweet-Spot 3-5pp)
SWEET_LO, SWEET_HI = 3.0, 6.0   # „beste" Zone; größere Moves oft schon durchgepreist


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def _devig2(a, b):
    ia, ib = _imp(a), _imp(b)
    if ia is None or ib is None:
        return None
    return ia / (ia + ib)


def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    od = d.get("odds") or {}
    picks = d.get("picks") or {}
    today = datetime.now(timezone.utc).date().isoformat()

    # Fixtures: Datum, Teamnamen, pick_key-Auflösung
    date_by, name_by, pk_by = {}, {}, {}
    for gkey, g in (d.get("groups") or {}).items():
        for fx in (g.get("fixtures") or []):
            mk = f"{fx['home']}-{fx['away']}"
            date_by[mk] = fx.get("date")
            name_by[mk] = (fx.get("home"), fx.get("away"))
            pk_by[mk] = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"

    # Signal-Netto pro Fixture/Seite aus bestehenden Picks (Bestätigungs-Quelle)
    def signal_support(mk, want_market_substrings):
        """Summe der weighted_scores aller Signale an Picks dieses Fixtures, deren
        pick_side zur gesteamten Seite passt. + = stützt, − = widerspricht."""
        plist = picks.get(pk_by.get(mk, ""), [])
        net, evid = 0.0, []
        for p in plist:
            m = (p.get("market") or "")
            if not any(s in m for s in want_market_substrings):
                continue
            for s in (p.get("signals") or []):
                ws = s.get("weighted_score") or 0
                net += ws
                if abs(ws) >= 0.5 and len(evid) < 3:
                    evid.append(f"{s.get('name')} {ws:+.1f}")
        return net, evid

    SIDES_1X2 = [
        ("hw", "Heimsieg", "home", ["Heimsieg", "Doppelte Chance 1X", "DNB Heim"]),
        ("aw", "Auswärtssieg", "away", ["Auswärtssieg", "Doppelte Chance X2", "DNB Ausw"]),
    ]

    cands = []
    for mk, o in od.items():
        if mk not in date_by:
            continue
        dt = date_by[mk]
        if not dt or dt < today:
            continue   # nur kommende Spiele (heute+)
        op = o.get("odds_open") or {}
        home, away = name_by[mk]

        # ── 1X2-Steam ────────────────────────────────────────────────────
        for key, lbl, side, sig_subs in SIDES_1X2:
            cur, opn = o.get(key), op.get(key)
            ci, oi = _imp(cur), _imp(opn)
            if ci is None or oi is None:
                continue
            move = (ci - oi) * 100
            if move < MOVE_TRIGGER_PP:
                continue
            team = home if side == "home" else away
            # Soft-Follow / -Lag
            soft = o.get(f"public_{key}")
            si = _imp(soft)
            soft_note = "—"
            if si is not None:
                lag = (ci - si) * 100   # + = Pini kürzer als Soft = Soft hinkt nach (Value)
                soft_note = (f"Soft @{soft:.2f} hinkt +{lag:.1f}pp (Value)" if lag > 1
                             else f"Soft @{soft:.2f} folgt (bestätigt)" if lag > -1
                             else f"Soft @{soft:.2f} kürzer (Soft führt)")
            # Poly-Lag (Ausführung)
            poly = o.get(f"poly_{key}")
            pi = _imp(poly)
            poly_note = "Poly n/a"
            if pi is not None and poly and poly > 1.0:
                plag = (ci - pi) * 100
                poly_note = (f"Poly @{poly:.2f} hinkt +{plag:.1f}pp → ausführbar"
                             if plag > 1 else f"Poly @{poly:.2f} konvergiert")
            # Signal-Support
            net, evid = signal_support(mk, sig_subs)
            sig_note = (f"Signale {net:+.1f} ({', '.join(evid)})" if evid
                        else f"Signale {net:+.1f}" if net else "Signale: keine auf der Seite")
            cands.append({
                "date": dt, "mk": mk, "team": team, "market": lbl,
                "open": opn, "cur": cur, "move": move,
                "sweet": SWEET_LO <= move <= SWEET_HI,
                "soft": soft_note, "poly": poly_note, "sig_net": net, "sig": sig_note,
            })

        # ── O/U-2.5-Steam ───────────────────────────────────────────────
        for key, opp, lbl in (("o25", "u25", "Über 2.5 Tore"), ("u25", "o25", "Unter 2.5 Tore")):
            cur, opn = o.get(key), op.get(key)
            ci, oi = _imp(cur), _imp(opn)
            if ci is None or oi is None:
                continue
            move = (ci - oi) * 100
            if move < MOVE_TRIGGER_PP:
                continue
            sig_subs = ["Über 2.5"] if key == "o25" else ["Unter 2.5"]
            net, evid = signal_support(mk, sig_subs)
            sig_note = (f"Signale {net:+.1f} ({', '.join(evid)})" if evid
                        else f"Signale {net:+.1f}" if net else "Signale: keine")
            cands.append({
                "date": dt, "mk": mk, "team": f"{home}-{away}", "market": lbl,
                "open": opn, "cur": cur, "move": move,
                "sweet": SWEET_LO <= move <= SWEET_HI,
                "soft": "—", "poly": "—", "sig_net": net, "sig": sig_note,
            })

    cands.sort(key=lambda c: (not c["sweet"], -c["move"]))

    # ── Report ──────────────────────────────────────────────────────────
    lines = []
    lines.append("# 🔥 Steam-Picks (Prototyp) — Pinnacle-Move-Following\n")
    lines.append(f"_Trigger = Pini-Quote gefallen ≥{MOVE_TRIGGER_PP:.0f}pp seit Opening. "
                 f"Kein Fair-Value-Modell. Pick = gesteamte Seite zur aktuellen Quote._\n")
    lines.append(f"_Sweet Spot {SWEET_LO:.0f}-{SWEET_HI:.0f}pp (Backtest 01.06.: +14% ROI). "
                 f"Stand: {today}. ISOLIERT — Live-System unberührt._\n")
    sweet = [c for c in cands if c["sweet"]]
    big = [c for c in cands if not c["sweet"]]
    lines.append(f"\n**{len(cands)} Steam-Trigger gesamt** · {len(sweet)} im Sweet Spot · "
                 f"{len(big)} größere Moves (Vorsicht: oft schon durchgepreist).\n")

    def block(title, rows):
        if not rows:
            return
        lines.append(f"\n## {title}\n")
        for c in rows:
            tag = "⭐ Sweet Spot" if c["sweet"] else "⚠️ großer Move"
            lines.append(f"\n### {c['date']} · {c['mk']} — **{c['team']} / {c['market']}** "
                         f"@ {c['cur']:.2f}  ({tag})")
            lines.append(f"- **Move:** {c['open']:.2f} → {c['cur']:.2f}  (+{c['move']:.1f}pp Geld auf diese Seite)")
            lines.append(f"- **Soft-Books:** {c['soft']}")
            lines.append(f"- **Polymarket:** {c['poly']}")
            lines.append(f"- **Signal-Litanei:** {c['sig']}  →  "
                         f"{'✅ stützt' if c['sig_net'] > 0.3 else '❌ widerspricht' if c['sig_net'] < -0.3 else '➖ neutral'}")

    block("Sweet Spot (3-6pp) — die Kern-Picks", sweet)
    block("Größere Moves (>6pp) — meist schon durchgepreist", big)

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ {len(cands)} Steam-Trigger · {len(sweet)} im Sweet Spot → {REPORT.name}")
    # Konsolen-Kurzfassung Sweet Spot
    print("\n— Sweet-Spot-Picks (Kern) —")
    for c in sweet[:15]:
        d_ = "✅" if c["sig_net"] > 0.3 else "❌" if c["sig_net"] < -0.3 else "➖"
        print(f"  {c['date']} {c['mk']:<9} {c['team']:<14} {c['market']:<14} "
              f"{c['open']:.2f}→{c['cur']:.2f} +{c['move']:.1f}pp  Sig{d_}")


if __name__ == "__main__":
    main()
