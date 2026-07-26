"""tg_safe.py — Telegram-sichere Darstellungshelfer.
================================================================================
25.07.2026 (Lucas: „img-Bug bei MLS-Alerts"). Telegrams sendMessage im HTML-Modus
erlaubt nur ein kleines Tag-Set (b/i/u/s/a/code/pre/span/blockquote/tg-*) — KEIN
<img>. Klub-Datensätze (liga/mls) liefern das Team-„flag" aber als <img>-Logo
(fürs Dashboard gedacht). Landet so ein Tag im Alert-Text, antwortet Telegram mit
HTTP 400 „Unsupported start tag" → die Nachricht scheitert lautlos.

safe_flag() lässt echte Emoji (WM-Länderflaggen 🇪🇸) durch und ersetzt HTML-Logos
durch ein neutrales ⚽. Single Source für alle Telegram-Sender.
"""

def safe_flag(flag, fallback: str = "⚽") -> str:
    """Emoji durchlassen, HTML-Logos (<img …>) / leere Werte → fallback (⚽)."""
    if not flag or "<" in str(flag):
        return fallback
    return flag
