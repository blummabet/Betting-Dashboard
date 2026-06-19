"""
sharp_signals/lineup_signal.py — Aufstellungs-Signal (T-1h Killer)

Konzept:
  ~1h vor Anpfiff veröffentlichen die Verbände die Startaufstellungen.
  Das ist der späteste informationsreiche Datenpunkt vor dem Spiel.

  VOLLE AUSFALL-WERTUNG (15.06.2026, Lucas): Die T-1h-Aufstellung IST die
  Grundwahrheit, wer fehlt — besser als die (für NTs leere) Injury-API. Wir werten
  daher ALLE Schlüsselspieler aus, nicht nur den Top-Scorer, und positions-bewusst:

    · Fehlender Stürmer/Mittelfeld (ATT/MID) → eigenes Team trifft WENIGER
    · Fehlender Keeper/Verteidiger (GK/DEF)  → eigenes Team kassiert MEHR

  Daraus pro Team: offensive_loss + defensive_loss (gewichtet mit importance +
  Status-Wucht: komplett fehlt > auf Bank). Markt-Richtung:
    Über  = + (def_loss beider) − (off_loss beider)   [schwache Abwehr → mehr Tore]
    Unter = invers
    Heimsieg = Auswärts-Schwäche − Heim-Schwäche;  Auswärtssieg = invers

  Datenanbindung:
    context["lineups"][match_key] = {home:{starting,subs}, away:{starting,subs}, ...}
      starting/subs-Einträge: {id, name, pos, ...} — Match per id, dann Name.
    context["squads"][team_id]["key_players"] = [{id,name,role,importance,...}]
      (fetch_wm_squads.py). Fehlt key_players → Fallback auf Legacy-Top-Scorer.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "missing_score":        2.5,    # Schlüsselspieler fehlt komplett (volle Wucht)
    "benched_score":        1.5,    # Schlüsselspieler auf Bank
    "missing_min_goals":      2,    # Legacy-Top-Scorer: erst ab N Saison-Toren wichtig
    "confidence_full":     0.80,
    "confidence_partial":  0.60,
    # Volle Ausfall-Wertung (15.06.2026): positions-bewusste Gewichte.
    # Offensiv: fehlt → eigenes Team trifft weniger. Defensiv: fehlt → kassiert mehr.
    "role_off_weight":  {"ATT": 1.0, "MID": 0.6},
    "role_def_weight":  {"GK": 1.0, "DEF": 0.8},
    "key_player_cap":       4.0,    # max Beitrag (off bzw. def) je Team
    # Rückkehrer-Boost (15.06.2026): präsenter Schlüsselspieler der zuletzt Spiele
    # verpasst hat → Team STÄRKER als die (ihn nicht enthaltende) nt_xg-Form-Baseline.
    # Spiegelbild der Ausfall-Logik, kleiner als ein Ausfall (unsicherer). Nicht-redundant
    # zur Team-Form, weil die den Rückkehrer ja gar nicht kennt.
    "return_boost":         1.2,    # Magnitude (vs missing_score 2.5)
    "return_min_importance": 0.6,   # nur echte Schlüsselspieler
    "return_min_games_missed": 1,   # muss ≥N jüngste Team-Spiele verpasst haben
    # Schon-Verstärkung (19.06.2026, Lucas): ein qualifiziert+gesichertes Team (MD3), das
    # seine Offensive rausnimmt, schont BEWUSST → der offensive_loss zählt mehr (strategisches
    # Schonen, nicht Verletzung). Greift NUR wenn das Lineup das Schonen tatsächlich zeigt.
    "coast_off_amplify":        1.4,    # Faktor auf offensive_loss des Schon-Teams
    "coast_off_amplify_home_wc": 1.15,  # Heim-WM-Host: gibt sich daheim nicht auf → kaum verstärkt
    "host_teams":              ["MEX", "USA", "CAN"],
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("lineup_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _normalize_name(s: str) -> str:
    """Normalisiert Namen für Vergleich: lowercase, kein Diakritischer Zeichen."""
    if not s:
        return ""
    s = s.lower().strip()
    repl = {
        # Vowels mit Akzenten
        "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a", "ā": "a", "å": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e", "ē": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i", "ī": "i", "ı": "i",
        "ó": "o", "ò": "o", "ô": "o", "ö": "o", "õ": "o", "ō": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u", "ū": "u",
        # Konsonanten
        "ñ": "n", "ç": "c", "ß": "ss",
        # Türkisch / slawische
        "ğ": "g", "ş": "s", "ž": "z", "š": "s", "č": "c", "ć": "c",
        "đ": "d", "ł": "l", "ń": "n", "ý": "y",
        # Apostrophe / Bindestriche raus
        "'": "", "'": "", "-": " ",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def _player_in_list(name: str, players: list) -> bool:
    """
    Prüft ob Spieler in der Liste ist — fuzzy match auf Last-Name.
    Last-Name ≥ 3 chars (z.B. "Tau", "Vaz") reicht, da Diakritika weggenommen.
    Bei Last-Name ≤ 2 chars: Vollname-Substring-Vergleich.
    """
    target = _normalize_name(name)
    if not target:
        return False
    target_last = target.split()[-1] if " " in target else target
    for p in players or []:
        pname = _normalize_name(p.get("name", ""))
        if not pname:
            continue
        # Substring-Match: target in pname (oder umgekehrt) bei langen Namen
        if len(target) >= 5 and (target in pname or pname in target):
            return True
        # Last-Name exakt-match (≥ 3 chars um falsche Treffer wie "de" zu vermeiden)
        pname_last = pname.split()[-1] if " " in pname else pname
        if target_last == pname_last and len(target_last) >= 3:
            return True
    return False


def _outcome_side_from_market(market: str) -> str:
    """
    Map Market → 'over' (Goals erwartet) | 'under' (no goals) | 'home' | 'away' | 'unknown'.

    WICHTIG: Über/Unter nur für TOR-Märkte triggern. "Über 9.5 Ecken" oder
    "Über 4.5 Karten" sind nicht goals-bezogen → unknown.
    """
    m = (market or "").lower()

    # Goals-Markets — Über/Unter nur wenn auf Tore bezogen
    is_goals = "tore" in m or "goals" in m
    if is_goals:
        if "über" in m or "over" in m:   return "over"
        if "unter" in m or "under" in m: return "under"

    # Outright
    if "heimsieg" in m or "doppelte chance — 1x" in m: return "home"
    if "auswärtssieg" in m or "auswartssieg" in m or "doppelte chance — x2" in m: return "away"
    if "dnb" in m and ("heim" in m or "home" in m):    return "home"
    if "dnb" in m and ("ausw" in m or "away" in m):    return "away"
    return "unknown"


class LineupSignal(Signal):
    """
    Aufstellungs-Signal — feuert nur wenn `lineups`-Daten im Context vorhanden.

    Context erwartet:
      lineups[match_key] = {
        "home": {"starting": [...], "subs": [...]},
        "away": {"starting": [...], "subs": [...]},
        "fetchedAt": iso8601,
      }
      squads[team_id] = {"name": ..., "goals": int, ...}  # Top-Scorer pro Team
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "lineup_signal"

    # ── Status-Erkennung ──────────────────────────────────────────────────
    @staticmethod
    def _player_status(player: dict, team_lineup: dict) -> str:
        """missing | benched | starting. ID-Match zuerst (robust), dann Name."""
        pid = player.get("id")
        starting = team_lineup.get("starting") or []
        subs     = team_lineup.get("subs") or []
        if pid is not None:
            if any(p.get("id") == pid for p in starting):
                return "starting"
            if any(p.get("id") == pid for p in subs):
                return "benched"
            # ID bekannt aber nirgends → fehlt (kein Namens-Fallback nötig)
            return "missing"
        name = player.get("name", "")
        if _player_in_list(name, starting):
            return "starting"
        if _player_in_list(name, subs):
            return "benched"
        return "missing"

    # ── Voller Pfad: alle Schlüsselspieler positions-bewusst ──────────────
    def _team_losses(self, key_players: list, team_lineup: dict, player_form: dict = None):
        """(offensive_loss, defensive_loss, details) für ein Team.
        Offensiv = fehlende ATT/MID (Team trifft weniger). Defensiv = fehlende
        GK/DEF (Team kassiert mehr). Gewichtet mit importance + Status-Wucht.

        importance wird mit dem Per-Spieler-Form-Faktor skaliert (player_form, 15.06.2026):
        ein Schlüsselspieler in schwacher Turnier-/Saison-Form wiegt weniger. Liga-tauglich,
        weil player_form über die Spieler-ID läuft (s. player_form.py)."""
        off_w = self._t["role_off_weight"]
        def_w = self._t["role_def_weight"]
        pf = player_form or {}
        off_loss = def_loss = 0.0
        details = []
        for kp in key_players or []:
            status = self._player_status(kp, team_lineup)
            pf_entry = pf.get(str(kp.get("id"))) or {}
            form = float(pf_entry.get("form_factor", 1.0) or 1.0)
            imp = float(kp.get("importance") or 0.5)
            imp_eff = imp * form
            role = (kp.get("role") or "").upper()

            if status == "starting":
                # Rückkehrer-Boost: präsent + hoher Klub-Wert + zuletzt Spiele verpasst →
                # Team stärker als die nt_xg-Form-Baseline (die ihn nicht kennt). GEWINN
                # = negativer Verlust → senkt off_loss/def_loss (kann negativ werden).
                gm = pf_entry.get("games_missed")
                if (imp >= self._t["return_min_importance"]
                        and gm is not None and gm >= self._t["return_min_games_missed"]):
                    gain = self._t["return_boost"] * imp_eff
                    if role in off_w:
                        off_loss -= gain * off_w[role]
                    if role in def_w:
                        def_loss -= gain * def_w[role]
                    details.append({"name": kp.get("name"), "role": role, "status": "returning",
                                    "games_missed": gm, "importance": round(imp_eff, 3)})
                continue

            mag = self._t["missing_score"] if status == "missing" else self._t["benched_score"]
            contrib = mag * imp_eff
            if role in off_w:
                off_loss += contrib * off_w[role]
            if role in def_w:
                def_loss += contrib * def_w[role]
            details.append({"name": kp.get("name"), "role": role, "status": status,
                            "importance": round(imp_eff, 3), "form_factor": round(form, 3)})
        cap = self._t["key_player_cap"]
        return max(-cap, min(off_loss, cap)), max(-cap, min(def_loss, cap)), details

    def _coast_amplify(self, home_id, away_id, context):
        """(faktor_heim, faktor_auswärts) für den offensive_loss. >1.0 wenn das Team in MD3
        qualifiziert+gesichert ist (bewusstes Schonen). Heim-WM-Host gedämpft. Sonst 1.0."""
        ctx = context or {}
        if ctx.get("matchday") != 3:
            return 1.0, 1.0
        standings = ctx.get("standings") or {}
        group_id = ctx.get("group_id")
        if not group_id:
            return 1.0, 1.0
        try:
            from sharp_signals.incentive_signal import _compute_qualification_state as _qs
            hq = bool(_qs(home_id, group_id, 3, standings).get("qualified"))
            aq = bool(_qs(away_id, group_id, 3, standings).get("qualified"))
        except Exception:
            return 1.0, 1.0
        hosts = set(self._t.get("host_teams") or [])
        amp = self._t["coast_off_amplify"]
        amp_wc = self._t["coast_off_amplify_home_wc"]
        fh = (amp_wc if home_id in hosts else amp) if hq else 1.0
        fa = amp if aq else 1.0
        return fh, fa

    def _evaluate_full(self, side, entry, home_id, away_id, kp_home, kp_away, player_form=None, context=None):
        off_h, def_h, det_h = self._team_losses(kp_home, entry.get("home", {}), player_form)
        off_a, def_a, det_a = self._team_losses(kp_away, entry.get("away", {}), player_form)

        # Schon-Verstärkung (19.06.2026): wenn ein qualifiziert+gesichertes Team (MD3) seine
        # Offensive tatsächlich rausnimmt, zählt dieser offensive_loss mehr (bewusstes Schonen).
        # Heim-WM-Host gedämpft (gibt sich daheim nicht auf). Greift nur bei echtem off_loss.
        cf_h, cf_a = self._coast_amplify(home_id, away_id, context)
        off_h *= cf_h
        off_a *= cf_a

        score = 0.0
        if side == "over":
            # Schwache Abwehr → mehr Tore (+); schwacher Angriff → weniger Tore (−)
            score += (def_h + def_a) - (off_h + off_a)
        elif side == "under":
            score += (off_h + off_a) - (def_h + def_a)
        elif side == "home":
            # Auswärts geschwächt → Heimsieg wahrscheinlicher
            score += (off_a + def_a) - (off_h + def_h)
        elif side == "away":
            score += (off_h + def_h) - (off_a + def_a)
        else:
            return None

        affected = ([{**d, "team": "Heim", "team_id": home_id} for d in det_h if d["status"] != "starting"]
                    + [{**d, "team": "Auswärts", "team_id": away_id} for d in det_a if d["status"] != "starting"])
        if not affected or abs(round(score, 2)) < 0.05:
            return None

        any_missing = any(a["status"] == "missing" for a in affected)
        confidence = self._t["confidence_full"] if any_missing else self._t["confidence_partial"]
        _lbl = {"missing": "fehlt", "benched": "Bank", "returning": "zurück"}
        parts = [f"{a['team']} {a['name']} ({a['role']}) {_lbl.get(a['status'], a['status'])}"
                 for a in affected]
        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence="🚨 " + " · ".join(parts),
            metadata={"side": side, "affected": affected,
                      "mode": "full", "fetchedAt": entry.get("fetchedAt")},
        )

    # ── Legacy-Fallback: nur Top-Scorer (wenn keine key_players da) ────────
    def _evaluate_top_scorer(self, side, entry, home_id, away_id, home_scorer, away_scorer):
        def _status(scorer: dict, team_lineup: dict) -> str:
            if not scorer or not scorer.get("name"):
                return "unknown"
            if (scorer.get("goals") or 0) < self._t["missing_min_goals"]:
                return "unknown"
            name = scorer["name"]
            if _player_in_list(name, team_lineup.get("starting") or []):
                return "starting"
            if _player_in_list(name, team_lineup.get("subs") or []):
                return "benched"
            return "missing"

        home_status = _status(home_scorer, entry.get("home", {}))
        away_status = _status(away_scorer, entry.get("away", {}))
        score = 0.0
        evidence_parts, affected_teams = [], []
        for team_label, team_id, status, scorer in [
            ("Heim", home_id, home_status, home_scorer),
            ("Auswärts", away_id, away_status, away_scorer),
        ]:
            if status in ("starting", "unknown"):
                continue
            magnitude = self._t["missing_score"] if status == "missing" else self._t["benched_score"]
            if side == "over":                                    score -= magnitude
            elif side == "under":                                 score += magnitude
            elif side == "home" and team_label == "Auswärts":     score += magnitude
            elif side == "away" and team_label == "Heim":         score += magnitude
            elif side == "home" and team_label == "Heim":         score -= magnitude
            elif side == "away" and team_label == "Auswärts":     score -= magnitude
            else:                                                 continue
            evidence_parts.append(f"{team_label} {scorer['name']} "
                                  f"{'fehlt' if status == 'missing' else 'Bank'}")
            affected_teams.append({"team": team_label, "team_id": team_id,
                                   "scorer": scorer.get("name"), "goals": scorer.get("goals"),
                                   "status": status})
        if not affected_teams:
            return None
        any_missing = any(t["status"] == "missing" for t in affected_teams)
        confidence = self._t["confidence_full"] if any_missing else self._t["confidence_partial"]
        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence="🚨 " + " · ".join(evidence_parts),
            metadata={"side": side, "affected": affected_teams,
                      "mode": "top_scorer", "fetchedAt": entry.get("fetchedAt")},
        )

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        mk = context.get("matchKey")
        if not mk:
            return None
        entry = (context.get("lineups") or {}).get(mk)
        if not entry:
            return None
        home_id = context.get("home_id")
        away_id = context.get("away_id")
        if not home_id or not away_id:
            return None
        side = _outcome_side_from_market(pick.get("market", ""))
        if side == "unknown":
            return None

        squads = context.get("squads") or {}
        home_sq = squads.get(home_id) or {}
        away_sq = squads.get(away_id) or {}
        kp_home = home_sq.get("key_players")
        kp_away = away_sq.get("key_players")

        # Per-Spieler-Form (player_form.py) — skaliert importance. Leer = neutral (Faktor 1.0).
        player_form = (context.get("player_form") or {})
        if isinstance(player_form, dict) and "players" in player_form:
            player_form = player_form["players"]   # akzeptiert ganzes File ODER nur das Mapping

        # Voller Pfad sobald MINDESTENS ein Team eine key_players-Liste hat;
        # sonst Legacy-Top-Scorer (Abwärtskompatibilität für alte Squad-Daten).
        if kp_home or kp_away:
            return self._evaluate_full(side, entry, home_id, away_id,
                                       kp_home or [], kp_away or [], player_form, context)
        return self._evaluate_top_scorer(side, entry, home_id, away_id, home_sq, away_sq)
