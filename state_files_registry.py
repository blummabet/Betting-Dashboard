#!/usr/bin/env python3
"""
state_files_registry.py — Registry-Reader für State-Files
============================================================

Liest state_files_registry.json und gibt Workflows die Liste der zu
committenden Files. Verhindert dass jeder Workflow seine eigene git-add
Liste hat (die dann auseinanderdriften kann).

Usage in bash (im Workflow):

    FILES=$(python state_files_registry.py --bash-list fetch_wm_data)
    git add $FILES 2>/dev/null || true

Oder mit existence-check:

    while IFS= read -r f; do
      [ -e "$f" ] && git add "$f"
    done < <(python state_files_registry.py --line-list fetch_wm_data)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
REGISTRY = BASE / "state_files_registry.json"


def load_registry() -> dict:
    if not REGISTRY.exists():
        raise FileNotFoundError(f"{REGISTRY} fehlt")
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def get_files_for_category(category: str) -> list[str]:
    """Returns Datei-Liste für eine Workflow-Kategorie."""
    reg = load_registry()
    cat = (reg.get("categories") or {}).get(category)
    if not cat:
        raise ValueError(f"Unbekannte Kategorie: {category}. "
                         f"Verfügbar: {list((reg.get('categories') or {}).keys())}")
    return cat.get("files", [])


def list_categories() -> list[str]:
    reg = load_registry()
    return list((reg.get("categories") or {}).keys())


def main():
    if len(sys.argv) < 2:
        # Default: zeigt alle Kategorien
        reg = load_registry()
        print("State-Files-Registry · Kategorien:")
        for name, cat in (reg.get("categories") or {}).items():
            print(f"  · {name}: {len(cat.get('files', []))} Files "
                  f"(owner: {cat.get('owner_workflow', '?')})")
        print(f"\nUsage:")
        print(f"  python state_files_registry.py --bash-list <category>   # space-separated für git add")
        print(f"  python state_files_registry.py --line-list <category>   # one per line für Shell-Loop")
        return

    mode = sys.argv[1]
    if mode in ("--bash-list", "--line-list"):
        if len(sys.argv) < 3:
            print("ERROR: Kategorie fehlt", file=sys.stderr)
            sys.exit(1)
        files = get_files_for_category(sys.argv[2])
        if mode == "--bash-list":
            print(" ".join(files))
        else:
            for f in files:
                print(f)
    elif mode == "--categories":
        for c in list_categories():
            print(c)
    else:
        print(f"ERROR: Unbekannter Modus: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
