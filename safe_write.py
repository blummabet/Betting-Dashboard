"""
safe_write.py — Zentraler Wipe-Schutz für alle Fetcher (12.07.2026, Lucas).

ANLASS: Der API-Zugang lief über Nacht ab → build_liga_data bekam 0 Fixtures und überschrieb
mls-data.json mit LEEREN groups → die Liga-Cards kippten. Ein Audit fand dieselbe Bug-Klasse in
11 weiteren Skripten. Grundregel ab jetzt:

    **Ein leeres/fehlgeschlagenes API-Ergebnis darf NIEMALS bestehende Daten überschreiben.**

Zwei Werkzeuge:
  · preserve_nonempty(old, new)  — Merge je Key: ein befüllter Alt-Wert wird NIE durch einen
    leeren Neu-Wert ersetzt; Keys die im neuen Lauf ganz fehlen, bleiben erhalten.
  · write_json_guarded(path, data, ...) — atomares Schreiben, das ABBRICHT (SystemExit=laut, im
    CI sichtbar), wenn die Datei drastisch schrumpfen würde. Lieber ein roter Workflow als still
    vernichtete Daten.

Bewusst laut statt leise: ein Wipe soll den Job rot machen, nicht committet werden.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional


def _size(v: Any) -> int:
    """Anzahl 'Inhalte' eines Werts — dict/list/str/tuple → len, None → 0, sonst 1 (Skalar)."""
    if v is None:
        return 0
    if isinstance(v, (dict, list, tuple, str, set)):
        return len(v)
    return 1


def preserve_nonempty(old: Optional[dict], new: Optional[dict]) -> tuple[dict, list]:
    """Merge zweier Dicts mit Wipe-Schutz je Key.

    · Neuer Wert leer, alter Wert befüllt  → ALTEN behalten (API lieferte nichts).
    · Key fehlt im neuen Lauf, alt vorhanden → ALTEN behalten.
    · Sonst → neuen Wert übernehmen.

    Returns (merged, kept_keys). kept_keys = die Keys, bei denen der alte Stand gerettet wurde
    (→ Caller soll das LAUT loggen: API-Key/Quota prüfen!).
    """
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    merged: dict = {}
    kept: list = []
    for k, v in new.items():
        if _size(v) == 0 and _size(old.get(k)) > 0:
            merged[k] = old[k]
            kept.append(k)
        else:
            merged[k] = v
    for k, v in old.items():
        if k not in merged:
            merged[k] = v
            kept.append(k)
    return merged, kept


def write_json_guarded(path, data, *,
                       count: Optional[Callable[[Any], int]] = None,
                       min_ratio: float = 0.5,
                       label: str = "",
                       force: bool = False) -> None:
    """Atomar schreiben — aber ABBRECHEN, wenn die Datei drastisch schrumpft.

    count:     wie 'Größe' gemessen wird (default: Anzahl Top-Level-Einträge).
    min_ratio: neuer Umfang muss ≥ min_ratio × alter Umfang sein (default 50%).
    force:     Schutz bewusst umgehen (z.B. legitimes Leeren).

    Schrumpft die Datei unter die Schwelle → SystemExit(1): der Workflow wird ROT, die alte
    Datei bleibt unangetastet. Genau das wollen wir statt eines stillen Daten-Verlusts.
    """
    p = Path(path)
    cnt = count or (lambda d: len(d) if isinstance(d, (dict, list)) else _size(d))

    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            old = None
        if old is not None:
            n_old, n_new = cnt(old), cnt(data)
            if n_old > 0 and n_new < n_old * min_ratio:
                raise SystemExit(
                    f"❌ WIPE-SCHUTZ {label or p.name}: {n_old} → {n_new} Einträge "
                    f"(< {int(min_ratio * 100)}%) — Schreiben ABGEBROCHEN, alter Stand bleibt. "
                    f"API-Key/Quota/Ausfall prüfen!"
                )

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
