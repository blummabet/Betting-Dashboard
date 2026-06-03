#!/usr/bin/env python3
"""
bizarre_quote_picker.py — Wählt täglich ein Bizarre-Quote-Target + baut Card-Config.

Quelle: bizarre_quote_targets.json
Dedup:   bizarre_quote_sent.json (welche IDs schon verwendet)
Vergleiche: bizarre_comparisons.pick_for_quote()

Liefert hook_config + info_config (drop-in für hook_card / bizarre_info_card).
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from bizarre_comparisons import pick_for_quote

BASE             = Path(__file__).parent
TARGETS_FILE     = BASE / "bizarre_quote_targets.json"
SENT_FILE        = BASE / "bizarre_quote_sent.json"


def load_targets() -> list[dict]:
    if not TARGETS_FILE.exists(): return []
    try:
        d = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
        return d.get("targets", [])
    except Exception:
        return []


def load_sent() -> dict:
    if not SENT_FILE.exists():
        return {"history": []}
    try:
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"history": []}


def save_sent(state: dict) -> None:
    SENT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_target(seed: int | None = None) -> dict | None:
    """
    Wählt das nächste Target.
    Priorisierung:
      1. Noch nicht verwendet (id nicht in sent_ids)
      2. Bevorzugt extreme/high-tier (höhere Quoten)
      3. Random aus den verbleibenden 5 höchsten
    """
    targets = load_targets()
    if not targets: return None
    sent = load_sent()
    used_ids = {h.get("id") for h in sent.get("history", [])}

    fresh = [t for t in targets if t.get("id") not in used_ids and t.get("type") != "alias"]
    if not fresh:
        # Alle verwendet — reset (zyklisch)
        fresh = [t for t in targets if t.get("type") != "alias"]

    # Sortiere nach Quote desc → Top-Kandidaten
    fresh.sort(key=lambda t: -t.get("quote", 0))
    pool = fresh[:5]
    if seed is not None: random.seed(seed)
    return random.choice(pool)


def mark_used(target_id: str, date_str: str) -> None:
    sent = load_sent()
    sent.setdefault("history", []).append({"date": date_str, "id": target_id})
    # Trim auf 90 Tage
    if len(sent["history"]) > 200:
        sent["history"] = sent["history"][-200:]
    save_sent(sent)


def _fmt_pct(p: float) -> str:
    """Format chance_pct als deutsch '0,029 %'"""
    if p < 0.01:
        return f"{p:.3f} %".replace(".", ",")
    if p < 0.1:
        return f"{p:.3f} %".replace(".", ",")
    if p < 1:
        return f"{p:.2f} %".replace(".", ",")
    return f"{p:.1f} %".replace(".", ",")


def _fmt_quote(q: int | float) -> str:
    """Format 3501 → '1 : 3.501'"""
    return f"1 : {int(q):,}".replace(",", ".")


def build_card_config(target: dict) -> dict:
    """
    Generiert hook + info config dict für hook_card() / bizarre_info_card().
    """
    name       = target.get("name", "?")
    flag       = target.get("flag", "🏳")
    quote      = target.get("quote", 0)
    chance_pct = target.get("chance_pct", 0)
    chance_str = _fmt_pct(chance_pct)
    quote_str  = _fmt_quote(quote)

    # Vergleiche dynamisch wählen
    comps = pick_for_quote(chance_pct, n=6, seed=None)
    # Convert tuples → (emoji, text, prob) — droppe value
    comparisons = [(c[0], c[1], c[2]) for c in comps]

    # Punchline für Hook + Closing
    if comparisons:
        # Wähle den "krassesten" Vergleich der noch wahrscheinlicher ist als unsere Quote
        # für den Highlight-Fakt: nimm den am unteren Ende der Liste (am ähnlichsten)
        last = comps[-1]
        ratio = last[3] / chance_pct if chance_pct > 0 else 0
        if ratio >= 100:
            ratio_str = f"{int(ratio)}× wahrscheinlicher"
        elif ratio >= 10:
            ratio_str = f"{int(ratio)}× wahrscheinlicher"
        else:
            ratio_str = f"{ratio:.1f}× wahrscheinlicher"
        highlight_fact = f"{last[1]} ist {ratio_str}"
    else:
        highlight_fact = "Sogar 5 Richtige im Lotto sind wahrscheinlicher"

    # Closing-Line: pointiert
    if comparisons:
        cl = comparisons[-1]
        closing_line = (
            f'<strong>{name} {chance_str}</strong> — selbst der Vergleich '
            f'<strong>"{cl[1]}"</strong> ist deutlich wahrscheinlicher als der Pokal-Triumph.'
        )
    else:
        closing_line = f'<strong>{name} {chance_str}</strong> — mathematisch praktisch unmöglich.'

    # Variable Quote-Lines pro Card
    quote_options = [
        f'{name} wäre der <span class="acc">größte Schock</span> der WM-Geschichte. 🤯',
        f'Mathematik sagt: <span class="acc">nein.</span> 🧮',
        f'Bookies haben sich <span class="acc">nicht verrechnet.</span> 📉',
        f'<span class="acc">Träumen erlaubt</span> — Statistik weiß es besser. 🏝',
        f'Bizarre WM-Wahrheit, frisch <span class="acc">aus dem Markt.</span> 🎲',
    ]
    quote_line = random.choice(quote_options)

    hook_config = {
        "theme":            "bizarre",
        "big_number":       chance_str.replace(" %", "<span style='font-size:42px'>%</span>"),
        "sub_title":        f"{name} wird Weltmeister",
        "hook_line_1":      '<span class="acc">Diese 6 Dinge</span>',
        "hook_line_2":      'passieren <span class="yellow">vorher.</span>',
        "mystery_question": "Welcher Vergleich knallt am meisten?",
        "highlight_fact":   highlight_fact,
        "cta":              "DETAILS IM VIDEO",
    }

    info_config = {
        "theme":        "bizarre",
        "flag":         flag,
        "team_name":    name,
        "quote_str":    quote_str,
        "chance_pct":   chance_str,
        "comparisons":  comparisons,
        "closing_line": closing_line,
        "quote_line":   quote_line,
    }

    return {"hook": hook_config, "info": info_config, "target": target}


# ── Daily Pick (used by generate_daily_tiktok.py) ─────────────────────────────

def get_daily_bizarre_card(today_iso: str) -> dict | None:
    """
    Liefert die Card-Config für heute. Bevorzugt das gleiche Target wenn schon heute
    in sent_history (idempotent bei mehrfachem Aufruf am selben Tag).
    """
    sent = load_sent()
    todays = [h for h in sent.get("history", []) if h.get("date") == today_iso]
    if todays:
        # Schon heute jemand verwendet — selben wieder bauen
        target_id = todays[-1]["id"]
        targets = load_targets()
        target = next((t for t in targets if t.get("id") == target_id), None)
        if target:
            cfg = build_card_config(target)
            return cfg
    # Frisches Target
    target = pick_target(seed=hash(today_iso) % (2**32))
    if not target: return None
    cfg = build_card_config(target)
    mark_used(target["id"], today_iso)
    return cfg


if __name__ == "__main__":
    # Smoketest
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cfg = get_daily_bizarre_card(date_arg)
    if not cfg:
        print("Kein Target gefunden")
        sys.exit(1)
    target = cfg["target"]
    print(f"=== Daily Bizarre Card für {date_arg} ===")
    print(f"  Target:      {target['name']} ({target['id']}) {target['flag']}")
    print(f"  Quote:       {cfg['info']['quote_str']}")
    print(f"  Chance:      {cfg['info']['chance_pct']}")
    print(f"  Highlight:   {cfg['hook']['highlight_fact']}")
    print()
    print("  Vergleiche:")
    for emoji, text, prob in cfg["info"]["comparisons"]:
        print(f"    {emoji}  {text:<55}  {prob}")
    print()
    print(f"  Closing:     {cfg['info']['closing_line']}")
    print(f"  Quote-Line:  {cfg['info']['quote_line']}")
