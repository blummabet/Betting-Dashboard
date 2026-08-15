# -*- coding: utf-8 -*-
"""15.08.2026 (Lucas): toleranter Team-/Match-Abgleich fuer den Betfair-Geld-Snapshot auf den Karten.

Betfair schreibt Namen anders als die Karten-Fixtures:
  "Atlanta Utd"          vs "Atlanta United FC"
  "Deportivo"            vs "Deportivo La Coruna"
  "Orlando City"         vs "Orlando City SC"
  "Inter Miami CF"       vs "Inter Miami"
Der exakte event_key (nur a-z0-9, sortiert) verfehlt das -> das Betfair-Signal fiel still weg, obwohl
Geld am Spiel lag (~€30k+ ueber ein Wochenende, u.a. Deportivo-Elche €15.499).

Diese Helfer:
  * expandieren die einzige kritische Abkuerzung (utd -> united),
  * werfen reine Vereins-Suffixe (fc/sc/cf) raus,
  * matchen per Token-TEILMENGE, wobei BEIDE Teams passen muessen -> praktisch keine Fehltreffer.

BEWUSST getrennt von poly_cross_sport.event_key gehalten: das Poly-Radar-Matching bleibt unveraendert.
Absichtlich MINIMAL (nur fc/sc/cf + utd) -> keine Stadt-Kollisionen (z.B. AC/Inter Milan bleiben
unterscheidbar, weil weder 'ac' noch 'inter' entfernt wird). REIN/testbar."""
import re

# reine Vereins-/Rechtsform-Tokens ohne Unterscheidungswert -> raus. BEWUSST knapp gehalten.
_STOP = {"fc", "sc", "cf"}
# Abkuerzung -> Langform (sonst matcht "utd" nie auf "united"). Nur die eine, eindeutige.
_ABBR = {"utd": "united"}


def _tokens(name):
    """Name -> Liste bedeutungstragender Tokens (klein, Abk. expandiert, Vereins-Suffixe raus)."""
    raw = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower())
    out = []
    for tok in raw.split():
        tok = _ABBR.get(tok, tok)
        if tok in _STOP:
            continue
        out.append(tok)
    return out


def team_key(name):
    """Kanonischer Ein-Team-Schluessel: sortierte, deduplizierte, bedeutungstragende Tokens."""
    return "".join(sorted(set(_tokens(name))))


def teams_match(a, b):
    """Zwei Team-Namen dasselbe Team? Token-Mengen gleich ODER eine echte, nicht-leere Teilmenge der
    anderen ("Deportivo" ⊆ "Deportivo La Coruna", "Orlando City" ⊆ "Orlando City SC"). Leer -> nie."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return False
    return ta == tb or ta <= tb or tb <= ta


def match_key(h, a):
    """Reihenfolge-unabhaengiger, kanonischer Spiel-Schluessel aus zwei Teamnamen."""
    return "-".join(sorted([team_key(h), team_key(a)]))


def find_match(index_list, h, a):
    """Betfair-Spiel zu (h, a) finden. `index_list`: [(home_name, away_name, payload), ...].
    Erst exakter kanonischer Key, dann Teilmengen-Fallback (BEIDE Teams muessen passen, in beliebiger
    Heim/Auswaerts-Zuordnung -> praktisch fehltrefferfrei). Gibt payload oder None."""
    if not index_list:
        return None
    hk = match_key(h, a)
    for bh, ba, payload in index_list:
        if match_key(bh, ba) == hk:
            return payload
    for bh, ba, payload in index_list:
        if (teams_match(h, bh) and teams_match(a, ba)) or (teams_match(h, ba) and teams_match(a, bh)):
            return payload
    return None
