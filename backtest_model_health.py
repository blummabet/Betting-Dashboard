#!/usr/bin/env python3
"""
backtest_model_health.py — Backtest des CocoBet Pick-Modells
=============================================================

Liest picks_history.json, rekonstruiert Edge via (sc - 1/odds)*100 und aggregiert
ROI / Brier / Win-Rate über folgende Buckets:

  • Edge-Bucket (<4pp, 4-6, 6-10, 10-15, 15+)
  • Markt-Typ (homeWin, dc1X, btts, over25, ...)
  • Konfidenz (high / medium / low)
  • Sub-Modell (Elo vs. Skellam) ← die "Lucas-Tabelle"
  • Calibration-Bins (0.05-Schritte) — Brier-Score separat pro Sub-Modell

Methodik:
  • Stake = 1 flat.
  • Win  → +(odds - 1).
  • Loss → -1.
  • Push/Void → 0 (Push bleibt im Stake-Counter, Void fliegt raus).
  • Win-Rate-CI = Wilson (eigene Implementation).
  • ROI-CI = Bootstrap (5000 Resamples, deterministisch via seed=42).
  • Brier = mean((sc - won_int)^2), Push/Void exkludiert.
  • Outlier (|edgePP| > 40) separat — nicht in Aggregaten.
  • Buckets mit n < 30 sind "untrustworthy" — Warn-Marker im MD.

Markt-Typ → Sub-Modell-Mapping:
  • Elo:     homeWin, draw, awayWin, dnb_*, dc1X, dcX2, dc12
  • Skellam: AH, Over/Under, BTTS, Corners, Cards, *_tore, *_hz_*

Run:
  python3 backtest_model_health.py
  → backtest_report.md  + backtest_results.json
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Config-Loader (Refactor-Standard 2026-06-06) — Backwards-compatible
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}


def _cfg(section: str, key: str, default):
    """Safe lookup mit Fallback-Default."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default


BASE = Path(__file__).parent
PICKS_FILE = BASE / "picks_history.json"
REPORT_MD = BASE / "backtest_report.md"
RESULTS_JSON = BASE / "backtest_results.json"

# ── Konstanten aus Config (falls vorhanden) ──
EDGE_BUCKETS = _cfg("backtest", "edge_buckets", [4.0, 6.0, 10.0, 15.0])  # cut-points
OUTLIER_EDGE_PP = _cfg("backtest", "outlier_edge_pp", 40.0)
UNTRUSTWORTHY_N = _cfg("backtest", "untrustworthy_n", 30)
BOOTSTRAP_RESAMPLES = _cfg("backtest", "bootstrap_resamples", 5000)
BOOTSTRAP_SEED = _cfg("backtest", "bootstrap_seed", 42)
CALIB_BIN_STEP = _cfg("backtest", "calib_bin_step", 0.05)


# ───────────────────────────────────────────────────────────────────
# Sub-Modell-Mapping
# ───────────────────────────────────────────────────────────────────

ELO_MARKET_KEYS = {
    "homeWin", "awayWin", "draw",
    "dc1X", "dcX2", "dc12",
    "dnb_heimteam", "dnb_auswarts", "dnb_away", "dnb_home",
}

# Heuristisch nach Präfix: alles was AH / Over-Under / BTTS / Corners / Cards /
# Halbzeit / Team-Goals ist → Skellam-Tor-Modell
SKELLAM_PREFIXES = (
    "ah_", "over", "under",
    "btts", "noBtts", "no_btts",
    "corners_", "cards",
    "ht_", "1_hz_",
    "team_goals_",
    "over_", "under_",
)


def classify_market(market_key: str) -> str:
    """Returns 'elo', 'skellam', or 'unknown' for a given marketKey."""
    if not market_key:
        return "unknown"
    if market_key in ELO_MARKET_KEYS:
        return "elo"
    # Generic-prefix DNB / DC fall-throughs (sollte schon im Set sein, safety)
    if market_key.startswith("dnb_") or market_key.startswith("dc"):
        return "elo"
    for pref in SKELLAM_PREFIXES:
        if market_key.startswith(pref):
            return "skellam"
    return "unknown"


# ───────────────────────────────────────────────────────────────────
# Statistik-Helfer (stdlib + numpy/pandas erlaubt, keine scipy)
# ───────────────────────────────────────────────────────────────────

def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson-Score-Intervall für Binomial-Proportion.
    wins = Anzahl Erfolge (push/void NICHT mitzählen).
    n    = Anzahl Trials (push/void NICHT mitzählen).
    Returns (low, high) als Anteil 0..1. Bei n=0 → (0.0, 0.0).
    """
    if n <= 0:
        return (0.0, 0.0)
    phat = wins / n
    denom = 1.0 + (z * z) / n
    centre = (phat + (z * z) / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + (z * z) / (4 * n)) / n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def bootstrap_roi_ci(pnls: list[float], stakes: list[float],
                     resamples: int = BOOTSTRAP_RESAMPLES,
                     seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """
    Bootstrap-CI für ROI = sum(pnl) / sum(stake).
    pnls + stakes müssen paarweise zueinander gehören (selbe Reihenfolge).
    Returns (low, high) in Prozent. Bei n<2 oder sum(stakes)==0 → (nan, nan).
    """
    n = len(pnls)
    if n < 2 or sum(stakes) == 0:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    rois = []
    idx = list(range(n))
    for _ in range(resamples):
        sample_idx = [rng.choice(idx) for _ in range(n)]
        sp = sum(pnls[i] for i in sample_idx)
        ss = sum(stakes[i] for i in sample_idx)
        if ss > 0:
            rois.append(sp / ss * 100.0)
    if not rois:
        return (float("nan"), float("nan"))
    rois.sort()
    lo = rois[int(0.025 * len(rois))]
    hi = rois[int(0.975 * len(rois)) - 1] if int(0.975 * len(rois)) > 0 else rois[-1]
    return (lo, hi)


def pnl_for(result: str, odds: float) -> float:
    """Stake = 1 flat. Win → +(odds-1), Loss → -1, Push/Void → 0."""
    if result == "win":
        return odds - 1.0
    if result == "loss":
        return -1.0
    return 0.0  # push or void


def reconstruct_edge_pp(sc: float, odds: float) -> float:
    """edgePP = (sc - 1/odds) * 100. Caller must ensure odds > 0."""
    return (sc - 1.0 / odds) * 100.0


# ───────────────────────────────────────────────────────────────────
# Load & Flatten
# ───────────────────────────────────────────────────────────────────

def load_picks(path: Path = PICKS_FILE) -> list[dict]:
    """Flattenet picks_history.json zu einer flat-list von pick-dicts."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    skipped_no_sc = 0
    skipped_no_odds = 0
    for match in data:
        for p in match.get("picks", []):
            sc = p.get("sc")
            odds = p.get("odds")
            result = p.get("result")
            market_key = p.get("marketKey") or ""
            market = p.get("market") or ""
            conf = p.get("conf") or "unknown"

            if result is None:
                # Nicht-resolved Pick → skip silently
                continue

            if sc is None:
                skipped_no_sc += 1
                continue
            if odds is None or odds <= 0:
                skipped_no_odds += 1
                continue

            edge_pp = reconstruct_edge_pp(sc, odds)
            sub_model = classify_market(market_key)

            rows.append({
                "match_id": match.get("id"),
                "date": match.get("dateIso") or match.get("date"),
                "league": match.get("league"),
                "market": market,
                "marketKey": market_key,
                "conf": conf,
                "sc": float(sc),
                "odds": float(odds),
                "result": result,
                "edge_pp": edge_pp,
                "sub_model": sub_model,
                "pnl": pnl_for(result, float(odds)),
                "stake": 0.0 if result == "void" else 1.0,
            })

    if skipped_no_sc:
        print(f"  WARN: {skipped_no_sc} picks ohne sc übersprungen")
    if skipped_no_odds:
        print(f"  WARN: {skipped_no_odds} picks ohne/ungültige odds übersprungen")
    return rows


# ───────────────────────────────────────────────────────────────────
# Aggregation
# ───────────────────────────────────────────────────────────────────

def aggregate(rows: list[dict]) -> dict:
    """
    Aggregiert pnl/wins/n auf einer flachen Pick-Liste.
    Push/Void: 0 PnL.
    Win-Rate: nur win/loss zählen (push raus).
    ROI: pnl_sum / stake_non_void.
    Brier: mean((sc-1)^2 win-fall, (sc-0)^2 loss-fall) — push/void raus.
    """
    n = len(rows)
    if n == 0:
        return {
            "n": 0, "n_wins": 0, "n_losses": 0, "n_pushes": 0, "n_voids": 0,
            "n_wl": 0,
            "roi": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
            "win_rate": float("nan"),
            "wr_low": float("nan"), "wr_high": float("nan"),
            "brier": float("nan"),
        }

    n_wins = sum(1 for r in rows if r["result"] == "win")
    n_losses = sum(1 for r in rows if r["result"] == "loss")
    n_pushes = sum(1 for r in rows if r["result"] == "push")
    n_voids = sum(1 for r in rows if r["result"] == "void")
    n_wl = n_wins + n_losses

    pnls = [r["pnl"] for r in rows if r["result"] != "void"]
    stakes = [r["stake"] for r in rows if r["result"] != "void"]
    stake_sum = sum(stakes)
    roi = (sum(pnls) / stake_sum * 100.0) if stake_sum > 0 else float("nan")

    ci_lo, ci_hi = bootstrap_roi_ci(pnls, stakes) if len(pnls) > 1 else (float("nan"), float("nan"))

    win_rate = (n_wins / n_wl) if n_wl > 0 else float("nan")
    wr_lo, wr_hi = wilson_ci(n_wins, n_wl) if n_wl > 0 else (float("nan"), float("nan"))

    # Brier — nur Picks mit win/loss-result (push/void raus)
    brier_terms = []
    for r in rows:
        if r["result"] == "win":
            brier_terms.append((r["sc"] - 1.0) ** 2)
        elif r["result"] == "loss":
            brier_terms.append((r["sc"] - 0.0) ** 2)
    brier = sum(brier_terms) / len(brier_terms) if brier_terms else float("nan")

    return {
        "n": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "n_pushes": n_pushes,
        "n_voids": n_voids,
        "n_wl": n_wl,
        "roi": roi,
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "win_rate": win_rate,
        "wr_low": wr_lo,
        "wr_high": wr_hi,
        "brier": brier,
    }


def edge_bucket_of(edge_pp: float, cuts: list[float] = None) -> str:
    """Returns bucket-label für gegebenen edge_pp. cuts = [4,6,10,15] default."""
    cuts = cuts or EDGE_BUCKETS
    if edge_pp < cuts[0]:
        return f"<{cuts[0]:.0f}pp"
    for i in range(len(cuts) - 1):
        if edge_pp < cuts[i + 1]:
            return f"{cuts[i]:.0f}-{cuts[i+1]:.0f}pp"
    return f"{cuts[-1]:.0f}+pp"


def group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return dict(out)


def calibration_bins(rows: list[dict], step: float = CALIB_BIN_STEP) -> list[dict]:
    """
    Buckets predicted prob (sc) in 0.05-Schritten.
    Returns list of {bin_low, bin_high, n, mean_sc, observed_wr, diff}.
    Nur win/loss-Picks (push/void raus).
    """
    eligible = [r for r in rows if r["result"] in ("win", "loss")]
    if not eligible:
        return []
    bins = []
    edges = []
    x = 0.0
    while x < 1.0 + 1e-9:
        edges.append(round(x, 4))
        x += step
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        bucket = [r for r in eligible
                  if (r["sc"] >= lo and (r["sc"] < hi or (i == len(edges) - 2 and r["sc"] <= hi)))]
        if not bucket:
            continue
        n = len(bucket)
        mean_sc = sum(r["sc"] for r in bucket) / n
        n_wins = sum(1 for r in bucket if r["result"] == "win")
        observed_wr = n_wins / n
        bins.append({
            "bin_low": lo,
            "bin_high": hi,
            "n": n,
            "mean_predicted_sc": mean_sc,
            "observed_win_rate": observed_wr,
            "diff": observed_wr - mean_sc,
        })
    return bins


# ───────────────────────────────────────────────────────────────────
# Reporting
# ───────────────────────────────────────────────────────────────────

def fmt_pct(x: float, signed: bool = False) -> str:
    if not isinstance(x, (int, float)) or math.isnan(x):
        return "n/a"
    return (f"{x:+.2f}%" if signed else f"{x:.2f}%")


def fmt_int(x) -> str:
    return f"{int(x)}" if isinstance(x, (int, float)) and not math.isnan(x) else "n/a"


def fmt_float(x: float, digits: int = 3) -> str:
    if not isinstance(x, (int, float)) or math.isnan(x):
        return "n/a"
    return f"{x:.{digits}f}"


def warn_marker(n: int) -> str:
    return " ⚠️" if n < UNTRUSTWORTHY_N else ""


def render_bucket_table(name_col: str, items: list[tuple[str, dict]]) -> list[str]:
    """Generic markdown-table-renderer. items = [(label, agg_dict), ...]."""
    lines = [
        f"| {name_col} | n | ROI | 95% CI | Win-Rate | WR-CI | Brier |",
        "|---|---:|---:|---|---:|---|---:|",
    ]
    for label, a in items:
        n = a["n"]
        ci = (f"[{fmt_pct(a['ci_low'], True)}, {fmt_pct(a['ci_high'], True)}]"
              if not math.isnan(a["ci_low"]) else "n/a")
        wr = f"{a['win_rate']*100:.1f}%" if not math.isnan(a["win_rate"]) else "n/a"
        wr_ci = (f"[{a['wr_low']*100:.1f}%, {a['wr_high']*100:.1f}%]"
                 if not math.isnan(a["wr_low"]) else "n/a")
        lines.append(
            f"| {label}{warn_marker(n)} | {n} | {fmt_pct(a['roi'], True)} "
            f"| {ci} | {wr} | {wr_ci} | {fmt_float(a['brier'], 4)} |"
        )
    return lines


def build_report(rows_all: list[dict]) -> tuple[str, dict]:
    """Returns (markdown_string, results_json_dict)."""
    # Outlier-Split
    inliers = [r for r in rows_all if abs(r["edge_pp"]) <= OUTLIER_EDGE_PP]
    outliers = [r for r in rows_all if abs(r["edge_pp"]) > OUTLIER_EDGE_PP]

    # Void-Filter wird IN aggregate gehandhabt — n_resolved = ohne void
    n_total = len(inliers)
    n_resolved = sum(1 for r in inliers if r["result"] != "void")
    headline = aggregate(inliers)

    # ── Buckets ──
    # Edge-Buckets sortiert nach cut-Order
    bucket_order = ([f"<{EDGE_BUCKETS[0]:.0f}pp"]
                    + [f"{EDGE_BUCKETS[i]:.0f}-{EDGE_BUCKETS[i+1]:.0f}pp"
                       for i in range(len(EDGE_BUCKETS) - 1)]
                    + [f"{EDGE_BUCKETS[-1]:.0f}+pp"])

    by_edge_raw = defaultdict(list)
    for r in inliers:
        by_edge_raw[edge_bucket_of(r["edge_pp"])].append(r)
    by_edge = {b: aggregate(by_edge_raw.get(b, [])) for b in bucket_order}

    by_market_raw = group_by(inliers, "marketKey")
    by_market = {k: aggregate(v) for k, v in by_market_raw.items()}
    by_market_sorted = sorted(by_market.items(),
                              key=lambda kv: (kv[1]["roi"] if not math.isnan(kv[1]["roi"]) else -999),
                              reverse=True)

    by_conf_raw = group_by(inliers, "conf")
    by_conf = {k: aggregate(v) for k, v in by_conf_raw.items()}

    by_submodel_raw = group_by(inliers, "sub_model")
    by_submodel = {k: aggregate(v) for k, v in by_submodel_raw.items()}

    # Cross-Tab Edge x Sub-Modell
    cross_tab = {}
    for sm in ("elo", "skellam", "unknown"):
        cross_tab[sm] = {}
        sm_rows = by_submodel_raw.get(sm, [])
        sm_by_edge = defaultdict(list)
        for r in sm_rows:
            sm_by_edge[edge_bucket_of(r["edge_pp"])].append(r)
        for b in bucket_order:
            cross_tab[sm][b] = aggregate(sm_by_edge.get(b, []))

    # Calibration
    calib_elo = calibration_bins([r for r in inliers if r["sub_model"] == "elo"])
    calib_skel = calibration_bins([r for r in inliers if r["sub_model"] == "skellam"])

    # ───── MD-Render ─────
    md = []
    md.append("# CocoBet Pick-Modell — Backtest Report\n")
    md.append(f"_Source: `picks_history.json`  ·  Buckets: <{EDGE_BUCKETS[0]:.0f}pp, "
              f"4-6, 6-10, 10-15, 15+  ·  Outlier-Cutoff: |edge| > {OUTLIER_EDGE_PP:.0f}pp_\n")

    # 1. Headline
    md.append("## 1. Headline\n")
    md.append(f"- **n_total (inlier-Picks):** {n_total}")
    md.append(f"- **n_resolved (non-void):** {n_resolved}")
    md.append(f"- **n_outliers (|edge|>{OUTLIER_EDGE_PP:.0f}pp):** {len(outliers)} _(separat ausgewiesen, nicht in Aggregat)_")
    md.append(f"- **Gesamt-ROI:** {fmt_pct(headline['roi'], True)}")
    if not math.isnan(headline["ci_low"]):
        md.append(f"- **ROI 95% CI (bootstrap, {BOOTSTRAP_RESAMPLES} resamples):** "
                  f"[{fmt_pct(headline['ci_low'], True)}, {fmt_pct(headline['ci_high'], True)}]")
    if not math.isnan(headline["win_rate"]):
        md.append(f"- **Win-Rate (win/(win+loss)):** {headline['win_rate']*100:.2f}% "
                  f"_(Wilson 95% CI: [{headline['wr_low']*100:.1f}%, {headline['wr_high']*100:.1f}%])_")
    md.append(f"- **Brier-Score:** {fmt_float(headline['brier'], 4)} _(lower = better, 0.25 = random coin-flip baseline)_")
    md.append(f"- Wins: {headline['n_wins']}  ·  Losses: {headline['n_losses']}  ·  "
              f"Pushes: {headline['n_pushes']}  ·  Voids: {headline['n_voids']}\n")

    # 2. Edge-Bucket
    md.append("## 2. ROI × Edge-Bucket\n")
    md.append(f"_Edge-Reconstruction: `edgePP = (sc - 1/odds) × 100`. "
              f"Buckets mit n<{UNTRUSTWORTHY_N} sind mit ⚠️ markiert (untrustworthy)._\n")
    md.extend(render_bucket_table("Edge-Bucket",
                                  [(b, by_edge[b]) for b in bucket_order]))
    md.append("")

    # 3. Markt-Typ
    md.append("## 3. ROI × Markt-Typ\n")
    md.append(f"_Sortiert nach ROI. Buckets mit n<{UNTRUSTWORTHY_N}: ⚠️._\n")
    md.extend(render_bucket_table("marketKey", by_market_sorted))
    md.append("")

    # 4. Konfidenz
    md.append("## 4. ROI × Konfidenz\n")
    conf_order = [c for c in ["high", "medium", "low"] if c in by_conf]
    md.extend(render_bucket_table("conf",
                                  [(c, by_conf[c]) for c in conf_order]))
    md.append("")

    # 5. Sub-Modell (Lucas-Tabelle)
    md.append("## 5. ROI × Sub-Modell (Elo vs. Skellam)\n")
    md.append("_Mapping:_")
    md.append("- **Elo:** 1X2 (homeWin/draw/awayWin), DNB, DC (1X/12/X2)")
    md.append("- **Skellam:** AH, Over/Under, BTTS, Corners, Cards, Halbzeit, Team-Goals")
    md.append("- **unknown:** marketKey nicht klassifizierbar (sollte 0 sein bei sauberen Daten)\n")
    sm_order = [s for s in ["elo", "skellam", "unknown"] if s in by_submodel]
    md.extend(render_bucket_table("Sub-Modell",
                                  [(s, by_submodel[s]) for s in sm_order]))
    md.append("")

    # 5b. Cross-Tab
    md.append("### 5b. Cross-Tab: Edge-Bucket × Sub-Modell\n")
    for sm in sm_order:
        md.append(f"\n**{sm.upper()}**\n")
        md.extend(render_bucket_table("Edge-Bucket",
                                      [(b, cross_tab[sm][b]) for b in bucket_order]))
        md.append("")

    # 6. Calibration
    md.append("## 6. Calibration\n")
    md.append(f"_Buckets in {CALIB_BIN_STEP:.2f}-Schritten. "
              f"`diff = observed_wr - mean_predicted_sc`. "
              f"Werte nahe 0 = gut kalibriert. Negativ = Modell überschätzt._\n")

    def render_calib(name: str, bins: list[dict], brier: float) -> list[str]:
        lns = [f"\n### {name} (Brier = {fmt_float(brier, 4)})\n"]
        if not bins:
            lns.append("_keine Daten_")
            return lns
        lns.append("| Bin | n | mean_predicted_sc | observed_wr | diff |")
        lns.append("|---|---:|---:|---:|---:|")
        for b in bins:
            warn = warn_marker(b["n"])
            lns.append(
                f"| {b['bin_low']:.2f}-{b['bin_high']:.2f}{warn} | {b['n']} "
                f"| {b['mean_predicted_sc']:.3f} | {b['observed_win_rate']:.3f} "
                f"| {b['diff']:+.3f} |"
            )
        return lns

    md.extend(render_calib("Elo", calib_elo, by_submodel.get("elo", {}).get("brier", float("nan"))))
    md.extend(render_calib("Skellam", calib_skel, by_submodel.get("skellam", {}).get("brier", float("nan"))))

    # 7. Outliers
    md.append("\n## 7. Outliers (|edge| > {:.0f}pp)\n".format(OUTLIER_EDGE_PP))
    if outliers:
        out_agg = aggregate(outliers)
        md.append(f"- n: {out_agg['n']}, ROI: {fmt_pct(out_agg['roi'], True)}, "
                  f"Win-Rate: {(out_agg['win_rate']*100 if not math.isnan(out_agg['win_rate']) else float('nan')):.1f}%")
        md.append("- **Nicht in Aggregaten oberer Tabellen enthalten.** Diese Picks haben "
                  "extreme rekonstruierte Edges — typisch Pre-Refactor-Logik oder schlechte sc/odds-Paare.\n")
    else:
        md.append("- keine\n")

    md_str = "\n".join(md) + "\n"

    # ───── JSON ─────
    results = {
        "headline": headline,
        "by_edge_bucket": by_edge,
        "by_market": dict(by_market),
        "by_conf": by_conf,
        "by_sub_model": by_submodel,
        "cross_tab_edge_x_submodel": cross_tab,
        "calibration_elo": calib_elo,
        "calibration_skellam": calib_skel,
        "outliers": aggregate(outliers) if outliers else {"n": 0},
        "meta": {
            "n_total_inlier": n_total,
            "n_resolved_inlier": n_resolved,
            "n_outlier": len(outliers),
            "edge_buckets": EDGE_BUCKETS,
            "outlier_edge_pp": OUTLIER_EDGE_PP,
            "untrustworthy_n": UNTRUSTWORTHY_N,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        },
    }
    return md_str, results


# ───────────────────────────────────────────────────────────────────
# Entrypoint
# ───────────────────────────────────────────────────────────────────

def main(argv: list[str] = None) -> int:
    argv = argv or sys.argv[1:]
    if not PICKS_FILE.exists():
        print(f"  ERROR: {PICKS_FILE} nicht gefunden", file=sys.stderr)
        return 2

    print(f"backtest_model_health · loading {PICKS_FILE.name} ...")
    rows = load_picks(PICKS_FILE)
    print(f"  {len(rows)} resolved picks geladen")

    md, results = build_report(rows)

    REPORT_MD.write_text(md, encoding="utf-8")
    RESULTS_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str),
                            encoding="utf-8")

    # Headline-Echo
    h = results["headline"]
    print()
    print("=" * 60)
    print(f"  Headline · n_total={h['n']}  n_wl={h['n_wl']}")
    print(f"  ROI: {fmt_pct(h['roi'], True)}  "
          f"95% CI: [{fmt_pct(h['ci_low'], True)}, {fmt_pct(h['ci_high'], True)}]")
    if not math.isnan(h['win_rate']):
        print(f"  Win-Rate: {h['win_rate']*100:.2f}%  "
              f"Brier: {fmt_float(h['brier'], 4)}")
    print("=" * 60)
    print(f"  → {REPORT_MD.name}")
    print(f"  → {RESULTS_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
