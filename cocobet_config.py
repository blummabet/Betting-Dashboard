#!/usr/bin/env python3
"""
cocobet_config.py — Config-Loader für CocoBet-Magic-Numbers
=============================================================

Lädt cocobet_config.json und gibt ein Profile-spezifisches Config-Dict zurück.
Backwards-compatible: wenn config.json fehlt → DEFAULT_FALLBACK greift, kein Crash.

Usage:
    from cocobet_config import CONFIG, get_config

    edge_min = CONFIG["edge"]["bet_threshold_1x2"]    # einfacher Zugriff
    dedup_h = get_config("dedup_hours.sell_alert")    # dotted-path Zugriff

Profile-Wechsel:
    cocobet_config.json → "profiles.active": "liga_default"
    → bei nächstem Run greift Liga-Config statt WM-Config

Override per Environment:
    COCOBET_PROFILE=liga_default python ...
"""
from __future__ import annotations
import json
import os
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "cocobet_config.json"


# ── Fallback wenn config.json fehlt — minimal-konservativ ──
DEFAULT_FALLBACK = {
    "edge": {
        "min_1x2_for_pick": 5, "min_ou_for_pick": 4,
        "min_dnb_for_pick": 6, "min_dc_for_pick": 4, "min_ah_for_pick": 4,
        "bet_threshold_1x2": 8, "bet_threshold_ou": 6,
        "huge_edge_warn": 18, "max_edge_sane": 18,
        "ou_bet_max": 10, "ah_bet_max": 12,
    },
    "odds": {
        "max_for_pick": 6.5, "max_for_bet": 4.5,
        "max_for_bet_ou": 3.0, "max_for_bet_dnb": 4.0,
    },
    "underdog": {"elo_soft_threshold": 100, "elo_hard_threshold": 200},
    "trade": {
        "auto_trigger_edge_pp": 4.0, "auto_trigger_edge_elo_only": 8.0,
        "steam_lag_edge_pp": 3.0,
        "pre_tournament_edge_pp": 6.0, "pre_tournament_days": 5,
        "pre_match_close_hours": 2,
        "early_stoploss_hours": 2.0, "early_stoploss_pct": 0.15,
        "daily_bet_cap": 8, "daily_stake_cap_usdc": 50.0,
        "min_balance_buffer": 1.0, "stake_usdc_flat": 5.5,
        "min_vol_usdc": 10000, "min_days_until_game": 1,
        "min_hours_before_match": 4,
        "min_entry_price": 0.15, "max_entry_price": 0.85,
        "max_positions_per_match": 2, "max_open_exposure_usdc": 80.0,
        "adaptive_daily_fraction": 0.40,
    },
    "sell": {
        "profit_target": 0.10, "pinn_gap_pp": 1.5, "min_profit_pp": 0.03,
        "age_decay_hours": 48, "age_decay_profit_target": 0.05,
        "sharp_against_gap_pp": 7.0,
        "loss_deep_pct": 0.40, "loss_deep_hours_ahead": 12.0,
        "age_loss_hours": 36.0, "age_loss_threshold_pct": 0.10,
        "age_loss_max_hours_left": 48.0,
        "no_inplay_loss_sell": True,
    },
    "monitor": {
        "score_ok": 80, "score_watch": 60, "score_warning": 40, "score_critical": 0,
        "w_edge": 30, "w_pinn": 20, "w_clv": 15, "w_time": 5,
    },
    "steam": {
        "sell_velocity_pp_h": 0.3, "sell_edge_threshold": 1.5,
        "sell_min_entry_edge": 2.5, "high_conf_edge_min": 3.0,
        "min_edge_pp": 1.5, "signal_edge_pp": 2.0, "converged_edge_pp": 1.0,
        "trade_tier_edge_pp": 5.0,
        "max_snapshots": 50, "signal_ttl_days": 30,
    },
    "tiktok": {
        "dedup_window_days": 7,
    },
    "staking": {
        # Edge-Staking (28.06.2026, Lucas): fraktionales Kelly statt flach. assumedEdge wird aus der
        # Conviction abgeleitet (Steam-Cards haben keinen Preis-Edge → Conviction ist unser Proxy),
        # Kelly macht das odds-bewusst (Longshots → kleinerer Stake). Konservativ + hart gedeckelt.
        "bankroll": 1000.0,               # Referenz-Bankroll für die Sizing-Mathematik
        "kelly_fraction": 0.25,           # Viertel-Kelly (Varianz-schonend)
        "edge_per_conviction_pt": 0.006,  # je Conviction-Punkt über neutral: +0,6pp angenommener Edge
        "conviction_neutral": 5.0,        # ab hier aufwärts steigt der Stake
        "abwaegen_factor": 0.6,           # ABWÄGEN vorsichtiger als BET
        "min_stake": 2.0,
        "max_stake": 25.0,
    },
    "dedup_hours": {
        "sell_alert": 6, "edge_alert": 12,
        "sharp_move": 24, "position_health": 6, "spotlight_per_day": 2,
    },
    "telegram": {
        "max_log_entries": 500,
        "max_alerts_per_run": 4, "max_sharp_alerts_per_run": 6,
        "alert_edge_min_pp": 5, "alert_cumul_pp": 8, "alert_steam_pp": 10,
        "snap_window_days": 14,
        "min_bet_edge_pp": 4, "min_abw_edge_pp": 4,
    },
}


def _load_raw() -> dict:
    """Lädt cocobet_config.json. Returns DEFAULT_FALLBACK bei Fehler."""
    if not CONFIG_FILE.exists():
        return DEFAULT_FALLBACK
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  cocobet_config.json laden fehlgeschlagen: {e} — Fallback")
        return {"profiles": {"active": "_fallback", "_fallback": DEFAULT_FALLBACK}}


def _resolve_active_profile(raw: dict) -> dict:
    """Returns die Profile-Config je aktivem Profil (mit ENV-Override)."""
    profiles = raw.get("profiles", {})
    active = os.environ.get("COCOBET_PROFILE") or profiles.get("active", "wm2026")
    profile = profiles.get(active)
    if not profile or not isinstance(profile, dict):
        # Profile nicht gefunden → Fallback
        return DEFAULT_FALLBACK
    # Sicherstellen dass alle erwarteten Sections existieren — verschmelzen mit Default
    merged = {}
    for section in DEFAULT_FALLBACK.keys():
        merged[section] = {**DEFAULT_FALLBACK[section], **profile.get(section, {})}
    return merged


# Eager-Load beim Import — Module-Level singleton
CONFIG: dict = _resolve_active_profile(_load_raw())


def get_config(path: str, default=None):
    """Dotted-Path Lookup: get_config('dedup_hours.sell_alert') → 6."""
    parts = path.split(".")
    cur = CONFIG
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def reload_config() -> dict:
    """Erzwingt Re-Load (für Tests + Profile-Wechsel zur Laufzeit)."""
    global CONFIG
    CONFIG = _resolve_active_profile(_load_raw())
    return CONFIG


if __name__ == "__main__":
    raw = _load_raw()
    active_profile = (os.environ.get("COCOBET_PROFILE")
                      or raw.get("profiles", {}).get("active", "wm2026"))
    print(f"cocobet_config.py · Active Profile: {active_profile}")
    print(f"  bet_threshold_1x2: {CONFIG['edge']['bet_threshold_1x2']}pp")
    print(f"  pre_match_close: {CONFIG['trade']['pre_match_close_hours']}h")
    print(f"  sell_alert dedup: {CONFIG['dedup_hours']['sell_alert']}h")
    print(f"  edge_alert dedup: {CONFIG['dedup_hours']['edge_alert']}h")
    print(f"  daily_bet_cap: {CONFIG['trade']['daily_bet_cap']}")
