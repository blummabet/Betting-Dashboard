#!/usr/bin/env python3
"""
player_form.py — Per-Spieler-Turnier-/Saison-Form als importance-Modifikator (15.06.2026)

Idee (Lucas): Die `key_players`-importance kommt aus Klub-Saison-Daten und ist statisch.
Aber wenn ein Schlüsselspieler im laufenden Wettbewerb über-/unterperformt, soll sein
Gewicht im lineup_signal nachjustiert werden. Beispiel: Stürmer startet wieder, hatte
aber wenig Tore/xG → sein Ausfall (und Beitrag) wiegt weniger.

LIGA-TAUGLICH BY DESIGN: alles läuft über die Spieler-ID, nicht über „Nationalteam".
`/fixtures/players` (Rating/Tore/Schlüsselpässe pro Spieler) ist für JEDEN Wettbewerb
identisch → derselbe Ledger + Faktor greift für WM 2026 wie für Top-5-Ligen/CL. Nur die
Fixture-Quelle wechselt per Config-Profil.

Positions-abhängig (Vorteil ggü. „nur Rating"/„nur Output"):
  · ATT/MID  → Form aus Angriffs-Output (Tore+xG-Proxy+Schlüsselpässe) UND Rating.
               Fängt den „ordentliches Rating, aber torlos"-Stürmer, den reines Rating verpasst.
  · DEF/GK   → Form aus Rating (Tore wären unfair). Rating ist bei API-Football positionsnormiert.

Faktor diszipliniert: ±15% gedeckelt, zusätzlich nach Spielanzahl GESCHRUMPFT
(1–2 Spiele → fast neutral) — kein Überreagieren auf einen schlechten Abend.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEDGER_FILE = BASE / "player_form_ledger.json"
OUT_FILE    = BASE / "player_form.json"

DEFAULTS = {
    "enabled":         True,
    "max_shift":       0.15,   # Faktor in [1-max_shift, 1+max_shift]
    "recent_n":        5,      # rollendes Fenster jüngster Spiele
    "min_games_full":  3,      # volle Wucht erst ab N Spielen, davor linear geschrumpft
    "rating_ref":      6.80,   # neutrales Referenz-Rating wenn keine Klub-Baseline
    "k_rating":        0.18,   # Rating-Delta → Form-Beitrag
    "k_output":        0.30,   # Angriffs-Output-Delta (per 90) → Form-Beitrag (nur ATT/MID)
}

_OFFENSIVE_ROLES = {"ATT", "MID"}


def load_config() -> dict:
    """Profil-Override aus cocobet_config.json (profiles.active.player_form)."""
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw.get("profiles", {}).get("active", "wm2026")
        cfg = raw.get("profiles", {}).get(active, {}).get("player_form") or {}
        return {**DEFAULTS, **cfg}
    except Exception:
        return dict(DEFAULTS)


# ── Ledger (append-only, dedup nach playerId|fixtureId) ─────────────────────
def append_records(ledger: dict, new_rows: list) -> int:
    """Fügt Match-Spieler-Zeilen hinzu, dedupt nach (playerId, fixtureId). Returns #neu."""
    recs = ledger.setdefault("records", [])
    seen = {(r.get("playerId"), r.get("fixtureId")) for r in recs}
    added = 0
    for r in new_rows:
        key = (r.get("playerId"), r.get("fixtureId"))
        if key in seen or key[0] is None or key[1] is None:
            continue
        recs.append(r)
        seen.add(key)
        added += 1
    return added


def rows_from_fixture_players(fixture_id, api_response: list) -> list:
    """/fixtures/players-Response → flache Per-Spieler-Zeilen (wettbewerbs-agnostisch)."""
    rows = []
    for team_block in api_response or []:
        tid = (team_block.get("team") or {}).get("id")
        for p in (team_block.get("players") or []):
            player = p.get("player") or {}
            st = (p.get("statistics") or [{}])[0] or {}
            games = st.get("games") or {}
            mins = games.get("minutes") or 0
            if not mins:
                continue
            rows.append({
                "fixtureId": fixture_id,
                "playerId":  player.get("id"),
                "name":      player.get("name"),
                "teamId":    tid,
                "minutes":   mins,
                "rating":    _f(games.get("rating")),
                "goals":     (st.get("goals") or {}).get("total") or 0,
                "assists":   (st.get("goals") or {}).get("assists") or 0,
                "keyPasses": (st.get("passes") or {}).get("key") or 0,
                "ts":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
    return rows


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _per90(goals, assists, key_passes, minutes):
    if not minutes:
        return 0.0
    return (goals + 0.5 * assists + 0.10 * key_passes) * 90.0 / minutes


# ── Form-Faktor je Spieler ──────────────────────────────────────────────────
def compute_form_factor(records: list, baseline: dict, role: str, cfg: dict) -> tuple[float, dict]:
    """records = jüngste Match-Zeilen des Spielers. baseline = Klub-Saison (key_player).
    Returns (faktor, meta)."""
    role = (role or "MID").upper()
    n = len(records)
    if n == 0:
        return 1.0, {"n_games": 0, "reason": "keine Match-Daten"}

    # Rating-Delta (universell)
    ratings = [r["rating"] for r in records if r.get("rating") is not None]
    base_rating = (baseline.get("rating") if baseline.get("rating") else None) or cfg["rating_ref"]
    rating_delta = (sum(ratings) / len(ratings) - base_rating) if ratings else 0.0

    form = cfg["k_rating"] * rating_delta

    # Output-Delta NUR für Angriffs-Rollen
    if role in _OFFENSIVE_ROLES:
        tot_min = sum(r.get("minutes") or 0 for r in records)
        recent_out = _per90(
            sum(r.get("goals") or 0 for r in records),
            sum(r.get("assists") or 0 for r in records),
            sum(r.get("keyPasses") or 0 for r in records),
            tot_min,
        )
        base_out = _per90(baseline.get("goals") or 0, baseline.get("assists") or 0,
                          0, baseline.get("minutes") or 0)  # keyPasses fehlen in Baseline → 0
        form += cfg["k_output"] * (recent_out - base_out)

    # Deckeln ±max_shift, dann nach Spielanzahl schrumpfen (kleine Stichprobe → neutraler)
    factor_raw = max(1 - cfg["max_shift"], min(1 + cfg["max_shift"], 1 + form))
    shrink = min(1.0, n / max(1, cfg["min_games_full"]))
    factor = 1 + (factor_raw - 1) * shrink
    return round(factor, 3), {
        "n_games": n, "role": role,
        "rating_delta": round(rating_delta, 2),
        "shrink": round(shrink, 2),
    }


def build_form_table(ledger: dict, baselines: dict, cfg: dict | None = None,
                     squad_players: dict | None = None) -> dict:
    """Aggregiert den Ledger zu {str(playerId): {form_factor, recent_minutes, games_missed, ...}}.
    baselines = {playerId|str: {role, rating, goals, assists, minutes}} (aus squads.key_players).

    squad_players = {squadCode: [playerId,...]} (optional, aus squad_player_ids()): erlaubt
    die ROBUSTE Erkennung verpasster Spiele für den Rückkehrer-Boost (15.06.2026) — inkl.
    Spieler mit 0 Minuten (keine Ledger-Zeile). Die API-Team-ID des Kaders wird über einen
    beliebigen Mitspieler aufgelöst, der Ledger-Zeilen hat. Ohne squad_players: nur Form
    (kein games_missed) — Abwärtskompatibel."""
    cfg = cfg or load_config()
    if not cfg.get("enabled", True):
        return {}
    recent_n = cfg["recent_n"]

    by_player: dict = {}
    player_team: dict = {}          # playerId → API teamId (aus erster Ledger-Zeile)
    team_fixtures: dict = {}        # teamId → {fixtureId: ts}
    for r in ledger.get("records", []):
        pid = r.get("playerId")
        if pid is None:
            continue
        by_player.setdefault(pid, []).append(r)
        tid, fid = r.get("teamId"), r.get("fixtureId")
        if pid not in player_team and tid is not None:
            player_team[pid] = tid
        if tid is not None and fid is not None:
            team_fixtures.setdefault(tid, {}).setdefault(fid, r.get("ts") or "")

    # Team-Code → jüngste API-Fixture-IDs (für games_missed). Team-ID via Mitspieler.
    squad_recent: dict = {}         # squadCode → set(recent fixtureIds)
    for code, pids in (squad_players or {}).items():
        api_tid = next((player_team[p] for p in pids if p in player_team), None)
        if api_tid is None:
            continue
        fixes = sorted(team_fixtures.get(api_tid, {}).items(), key=lambda kv: kv[1])[-recent_n:]
        squad_recent[code] = {fid for fid, _ in fixes}
    player_squad = {p: code for code, pids in (squad_players or {}).items() for p in pids}

    def _missed_and_minutes(pid):
        code = player_squad.get(pid)
        recent_fix = squad_recent.get(code)
        if not recent_fix:
            return None, None   # Team-Recent unbekannt → nicht prüfbar
        appeared = [r for r in by_player.get(pid, []) if r.get("fixtureId") in recent_fix]
        mins = [r.get("minutes") or 0 for r in appeared]
        recent_minutes = round(sum(mins) / len(recent_fix), 1)   # Ø über die Team-Spiele
        games_missed = len(recent_fix) - len(appeared)
        return games_missed, recent_minutes

    # Alle relevanten Spieler: die mit Ledger-Zeilen + alle Kader-Spieler (auch 0-Minuten).
    all_pids = set(by_player) | {p for pids in (squad_players or {}).values() for p in pids}
    table = {}
    for pid in all_pids:
        recs = sorted(by_player.get(pid, []), key=lambda r: r.get("ts") or "")[-recent_n:]
        bl = baselines.get(str(pid)) or baselines.get(pid) or {}
        role = bl.get("role") or "MID"
        factor, meta = compute_form_factor(recs, bl, role, cfg)
        gm, rm = _missed_and_minutes(pid)
        entry = {"form_factor": factor, **meta}
        if gm is not None:
            entry["games_missed"] = gm
            entry["recent_minutes"] = rm
        table[str(pid)] = entry
    return table


def baselines_from_squads(squads: dict) -> dict:
    """squads[team].key_players → {str(playerId): {role, rating, goals, assists, minutes}}."""
    out = {}
    for tid, sq in (squads or {}).items():
        if tid == "_meta" or not isinstance(sq, dict):
            continue
        for kp in sq.get("key_players") or []:
            pid = kp.get("id")
            if pid is None:
                continue
            out[str(pid)] = {
                "role": kp.get("role"), "rating": kp.get("rating"),
                "goals": kp.get("goals"), "assists": kp.get("assists"),
                "minutes": kp.get("minutes"),
            }
    return out


def squad_player_ids(squads: dict) -> dict:
    """squads → {squadCode: [playerId,...]} für die games_missed-Auflösung in build_form_table."""
    out = {}
    for code, sq in (squads or {}).items():
        if code == "_meta" or not isinstance(sq, dict):
            continue
        ids = [kp.get("id") for kp in sq.get("key_players") or [] if kp.get("id") is not None]
        if ids:
            out[code] = ids
    return out


def main() -> int:
    """Standalone: Ledger + squads (Baselines) → player_form.json."""
    cfg = load_config()
    ledger = json.loads(LEDGER_FILE.read_text(encoding="utf-8")) if LEDGER_FILE.exists() else {"records": []}
    wm_file = BASE / "wm2026-data.json"
    squads = {}
    if wm_file.exists():
        squads = (json.loads(wm_file.read_text(encoding="utf-8")).get("squads")) or {}
    table = build_form_table(ledger, baselines_from_squads(squads), cfg,
                             squad_players=squad_player_ids(squads))
    OUT_FILE.write_text(json.dumps({
        "_meta": {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "players": len(table), "cfg": cfg},
        "players": table,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ player_form.json: {len(table)} Spieler mit Form-Faktor "
          f"(Ledger {len(ledger.get('records', []))} Match-Zeilen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
