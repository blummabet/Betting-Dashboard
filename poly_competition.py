"""poly_competition.py — Einheitliche Ableitung des Wettbewerbs aus dem Polymarket-Slug.

18.08.2026 (Lucas): EINE Quelle der Wahrheit fuer Telegram-Push, Resolver-Buckets und Stats.
Frueher war der Wettbewerb an mehreren Stellen hart auf WM verdrahtet; jetzt aus dem Slug-Praefix
abgeleitet (fifwc-/mls-/epl-/lal-/sea-/fl1-/bun-...). Rein/testbar, keine Netz-/Datei-Zugriffe.

  key   = stabiler Bucket-Schluessel fuer Stats/CLV (nie uebersetzt)
  label = Anzeige-Name (Telegram, Cards)
  path  = Polymarket-/sports/<path>/-Segment fuer den Event-Link
"""

# Slug-Praefix -> (key, label, poly_url_path)
_BY_PREFIX: dict[str, tuple[str, str, str]] = {
    "fifwc":        ("wc",           "WM 2026",         "fifa-world-cup"),
    "mls":          ("mls",          "MLS",             "mls"),
    "epl":          ("epl",          "Premier League",  "epl"),
    "lal":          ("laliga",       "La Liga",         "laliga"),
    "sea":          ("seriea",       "Serie A",         "serie-a"),
    "fl1":          ("ligue1",       "Ligue 1",         "ligue-1"),
    "bun":          ("bundesliga",   "Bundesliga",      "bundesliga"),
    "championship": ("championship", "Championship",    "championship"),
    "eredivisie":   ("eredivisie",   "Eredivisie",      "eredivisie"),
}

# Fallback je Datensatz, wenn kein Slug vorhanden (z.B. Altbestand ohne Slug im Record)
_DATASET_LABEL: dict[str, str] = {"wm": "WM 2026", "mls": "MLS", "liga": "Top-5-Ligen"}
_DATASET_KEY:   dict[str, str] = {"wm": "wc", "mls": "mls", "liga": "liga_mix"}


def _prefix(slug: str | None) -> str:
    return (slug or "").split("-", 1)[0].lower()


def from_slug(slug: str | None) -> tuple[str, str, str] | None:
    """(key, label, path) oder None, wenn der Slug-Praefix unbekannt ist."""
    return _BY_PREFIX.get(_prefix(slug))


def key_of(slug: str | None, dataset: str | None = None) -> str:
    """Stabiler Bucket-Schluessel. Fallback: Datensatz-Key, sonst 'other'."""
    r = from_slug(slug)
    if r:
        return r[0]
    return _DATASET_KEY.get(dataset or "", "other")


def label_of(slug: str | None, dataset: str | None = None) -> str:
    """Anzeige-Label. Fallback: Datensatz-Label, sonst 'Fussball'."""
    r = from_slug(slug)
    if r:
        return r[1]
    return _DATASET_LABEL.get(dataset or "", "Fussball")


def poly_path(slug: str | None) -> str | None:
    r = from_slug(slug)
    return r[2] if r else None


def poly_url(slug: str | None) -> str | None:
    """Korrekter Polymarket-Link je Wettbewerb; unbekannt -> generischer /event/-Link."""
    if not slug:
        return None
    p = poly_path(slug)
    return (f"https://polymarket.com/sports/{p}/{slug}" if p
            else f"https://polymarket.com/event/{slug}")


def dataset_label(dataset: str | None) -> str:
    return _DATASET_LABEL.get(dataset or "", "CocoBet")
