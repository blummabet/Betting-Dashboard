#!/usr/bin/env python3
"""
generate_wm_live_story.py — Master-Coordinator für WM Live-Story-Engine
=======================================================================

Workflow:
  1. Alle Angle-Module aufrufen → Liste von StoryProposals
  2. Master-Selector wählt höchsten Score (mit Dedup gegen letzte 4 Tage)
  3. Fact-Verifier prüft alle Slots der gewählten Proposal
  4. Wenn Verifier OK: HTML rendern + Vorschau an Trades-Channel
  5. Wenn nicht-skip per /skip → Card landet im outputs/-Folder für TikTok-Render
  6. State-File persistiert was heute gepostet wurde (für Dedup morgen)

Env-Variablen:
  TELEGRAM_TOKEN          — Bot-Token
  TELEGRAM_TRADES_CHAT_ID — Trades-Channel (privat)
  SKIP_TELEGRAM           — "true" → keine Telegram-Sends (Test-Modus)
  FORCE_ANGLE             — z.B. "killerStat" um nur diese Angle zu wählen
  DRY_RUN                 — "true" → Vorschläge anzeigen, nichts persistieren
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SKIP_RENDER = os.environ.get("SKIP_RENDER", "").lower() == "true"

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from wm_story_engine import (
    StoryProposal, verify_proposal, select_top,
    recent_entities, record_post, proposal_summary, load_state,
)
from tiktok_card_templates import hook_card, info_card

# Angles
# match_of_day bleibt importiert (liefert FLAG/TEAM_NAMES/_team_name an andere Angles),
# wird aber NICHT mehr als eigener Angle gewählt (16.06.2026, Lucas: „Spiel des Tages" raus).
from wm_story_angles import match_of_day, killer_stat, underdog_recap, player_spotlight, travel_alarm


# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
TRADES_CHAT_ID = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()
SKIP_TELEGRAM  = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"
FORCE_ANGLE    = (os.environ.get("FORCE_ANGLE") or "").strip()
DRY_RUN        = os.environ.get("DRY_RUN", "").lower() == "true"

OUTPUTS_DIR    = BASE / "wm_live_story_outputs"
PROPOSALS_FILE = BASE / "wm_story_proposals.json"


def _send_telegram_text(text: str) -> bool:
    if SKIP_TELEGRAM:
        print("ℹ️  SKIP_TELEGRAM=true — Text nur Konsole")
        print(text)
        return False
    if not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print(f"⚠️  Telegram NICHT möglich — fehlt: "
              f"{'TOKEN ' if not TELEGRAM_TOKEN else ''}"
              f"{'TRADES_CHAT_ID' if not TRADES_CHAT_ID else ''}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  TRADES_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Text-Fehler: {e}")
        return False


def _send_telegram_photo(png_path: Path, caption: str = "") -> bool:
    """Multipart-Upload für Story-PNG. Caption mit HTML-Parsing."""
    if SKIP_TELEGRAM:
        print(f"ℹ️  SKIP_TELEGRAM=true — PNG nicht gesendet ({png_path.name})")
        return False
    if not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print(f"⚠️  Telegram-Photo NICHT möglich — fehlt: "
              f"{'TOKEN ' if not TELEGRAM_TOKEN else ''}"
              f"{'TRADES_CHAT_ID' if not TRADES_CHAT_ID else ''}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    boundary = "----CocoBetWMStoryBoundary"
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{TRADES_CHAT_ID}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n")
    if caption:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
                 f"filename=\"{png_path.name}\"\r\nContent-Type: image/png\r\n\r\n")
    body = b""
    for p in parts:
        body += p.encode("utf-8")
    body += png_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Photo-Fehler: {e}")
        return False


def _render_html_to_png(html_content: str, out_png: Path, viewport_w: int = 360, viewport_h: int = 640) -> Path | None:
    """HTML-String → PNG via Playwright. Returns path or None bei Fehler."""
    if SKIP_RENDER:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  ⚠️  Playwright nicht installiert — kein PNG für {out_png.name}")
        return None
    tmp_html = out_png.with_suffix(".tmp.html")
    tmp_html.write_text(html_content, encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h},
                device_scale_factor=2,
            )
            page = ctx.new_page()
            page.goto(f"file://{tmp_html.absolute()}")
            page.wait_for_load_state("networkidle")
            card = page.locator(".card").first
            card.screenshot(path=str(out_png), omit_background=False)
            browser.close()
        return out_png
    except Exception as e:
        print(f"  ❌ Render-Fehler {out_png.name}: {e}")
        return None
    finally:
        try: tmp_html.unlink()
        except Exception: pass


def _append_telegram_log(p: StoryProposal, hook_sent: bool, info_sent: bool) -> None:
    """Schreibt einen Eintrag in telegram-log.json für UI-Tracking."""
    log_file = BASE / "telegram-log.json"
    try:
        log = json.loads(log_file.read_text(encoding="utf-8")) if log_file.exists() else []
    except Exception:
        log = []
    if not isinstance(log, list):
        log = []
    # Hook-Slot-Werte für Preview
    hs = p.hook_slots
    big = _slot_val(hs.get("big_number", ""))
    sub = _slot_val(hs.get("sub_title", ""))
    preview = f"🎬 {p.angle_id}: {big} · {sub}"[:200]
    log.append({
        "type":     "wm_live_story",
        "sentAt":   datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "preview":  preview,
        "chatId":   TRADES_CHAT_ID,
        "angle":    p.angle_id,
        "entity":   p.entity_key,
        "score":    round(p.score, 3),
        "theme":    p.theme,
        "hookSent": hook_sent,
        "infoSent": info_sent,
    })
    # auf 500 Einträge limitieren (rolling-window)
    log = log[-500:]
    log_file.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def _slot_val(slot) -> str:
    """Extrahiert .value aus Slot-dataclass oder dict."""
    if hasattr(slot, "value"):
        return slot.value
    if isinstance(slot, dict):
        return slot.get("value", "")
    return str(slot)


def _render_proposal_html(p: StoryProposal) -> tuple[str, str, str]:
    """Returns (hook_html, info_html, combined_preview_html)."""
    hs = p.hook_slots
    iss = p.info_slots
    hook_html = hook_card(
        theme=p.theme,
        big_number=_slot_val(hs.get("big_number", "")),
        sub_title=_slot_val(hs.get("sub_title", "")),
        hook_line_1=_slot_val(hs.get("hook_line_1", "")),
        hook_line_2=_slot_val(hs.get("hook_line_2", "")),
        mystery_question=_slot_val(hs.get("mystery_question", "")),
        highlight_fact=_slot_val(hs.get("highlight_fact", "")),
        cta="ANTWORT IM VIDEO",
        series_tag=p.series_tag or None,
    )
    info_html = info_card(
        theme=p.theme,
        flag=_slot_val(iss.get("flag", "🌍")),
        name=_slot_val(iss.get("name", "")),
        role_line=_slot_val(iss.get("role_line", "")),
        stat1_val=_slot_val(iss.get("stat1_val", "")),
        stat1_lbl=_slot_val(iss.get("stat1_lbl", "")),
        stat2_val=_slot_val(iss.get("stat2_val", "")),
        stat2_lbl=_slot_val(iss.get("stat2_lbl", "")),
        stat3_val=_slot_val(iss.get("stat3_val", "")),
        stat3_lbl=_slot_val(iss.get("stat3_lbl", "")),
        closing_line=_slot_val(iss.get("closing_line", "")),
        quote_line=_slot_val(iss.get("quote_line", "")),
        data_source=_slot_val(iss.get("data_source", "")),
        series_tag=p.series_tag or None,
    )
    combined = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>WM Live-Story Vorschau</title>
<style>
  body {{ margin:0; padding:24px; background:#0d1117; font-family:'Inter',sans-serif; }}
  .row {{ display:flex; gap:32px; flex-wrap:wrap; justify-content:center; }}
  .col {{ display:flex; flex-direction:column; gap:8px; align-items:center; }}
  .lbl {{ color:#8b949e; font-size:13px; letter-spacing:0.08em; text-transform:uppercase; }}
  .frame {{ background:#000; border-radius:18px; overflow:hidden;
            box-shadow:0 18px 60px rgba(0,0,0,0.5); }}
  iframe {{ width:360px; height:640px; border:0; display:block; }}
  .meta {{ color:#8b949e; font-size:13px; text-align:center; margin-bottom:16px; }}
  .meta strong {{ color:#fff; }}
</style></head><body>
<div class="meta">
  <strong>{p.angle_id}</strong> · Score {p.score:.2f} · entity={p.entity_key}<br>
  Reason: {p.reason}
</div>
<div class="row">
  <div class="col"><div class="lbl">1 · Hook</div>
    <div class="frame"><iframe srcdoc="{hook_html.replace('"', '&quot;')}"></iframe></div></div>
  <div class="col"><div class="lbl">2 · Info</div>
    <div class="frame"><iframe srcdoc="{info_html.replace('"', '&quot;')}"></iframe></div></div>
</div></body></html>"""
    return hook_html, info_html, combined


def _telegram_preview_text(p: StoryProposal, verify_report: dict) -> str:
    """Kompakter Telegram-Text mit Story-Headline + Verify-Status."""
    hs = p.hook_slots
    big = _slot_val(hs.get("big_number", ""))
    sub = _slot_val(hs.get("sub_title", ""))
    h1 = _slot_val(hs.get("hook_line_1", "")).replace("<span class=\"acc\">", "").replace("</span>", "").replace("<span class=\"yellow\">", "")
    h2 = _slot_val(hs.get("hook_line_2", "")).replace("<span class=\"acc\">", "").replace("</span>", "").replace("<span class=\"yellow\">", "")
    fact = _slot_val(hs.get("highlight_fact", ""))
    verify_ok = "✅" if verify_report["ok"] else f"❌ {len(verify_report['failures'])} fail"
    fails_text = ""
    if not verify_report["ok"]:
        fail_lines = "\n".join(f"   · {n}: {r}" for n, r in verify_report["failures"][:5])
        fails_text = f"\n<b>Verifier-Fails:</b>\n{fail_lines}"
    return (
        f"📱 <b>WM Live-Story Vorschau · {datetime.now(timezone.utc).strftime('%d.%m %H:%M')} UTC</b>\n"
        f"\n"
        f"<b>Angle:</b> {p.angle_id}\n"
        f"<b>Score:</b> {p.score:.2f}\n"
        f"<b>Verifier:</b> {verify_ok}\n"
        f"\n"
        f"<b>Hook:</b> <code>{big}</code> {sub}\n"
        f"   {h1}\n"
        f"   {h2}\n"
        f"   ⚡ {fact}\n"
        f"\n"
        f"<b>Reason:</b> {p.reason}\n"
        f"{fails_text}\n"
        f"\n"
        f"<i>Card landet automatisch im Render-Folder. Antwort mit /skip um zu stoppen.</i>"
    )


def main():
    today_iso = datetime.now(timezone.utc).isoformat()
    print(f"🎬 generate_wm_live_story.py · {today_iso[:19]} UTC\n")

    # ── Per-Tag-Guard (11.06.2026) ───────────────────────────────────────────
    # MAX 1 Story pro Kalendertag — egal wie oft der Workflow triggert (Cron 06:00
    # + manuelle Dispatches + lokale Läufe). Vorher nur Entity-Dedup (letzte 4 Tage)
    # → jeder Lauf postete eine NEUE Top-Story. Folge heute: matchOfDay KOR (15:51)
    # + matchOfDay MEX (16:28) = Doppel-Spam. Geprüft wird auf einen bereits HEUTE
    # erfolgreich geposteten Eintrag (status='posted'); fehlgeschlagene Versuche
    # blocken NICHT (Retry bleibt möglich). FORCE_ANGLE/DRY_RUN umgehen den Guard.
    if not DRY_RUN and not FORCE_ANGLE:
        _today = today_iso[:10]
        _posted_today = [p for p in (load_state().get("posted") or [])
                         if str(p.get("ts", ""))[:10] == _today and p.get("status") == "posted"]
        if _posted_today:
            last = _posted_today[-1]
            print(f"⏭️  Heute bereits eine Story gepostet "
                  f"({last.get('angle_id')}/{last.get('entity_key')}) — skip (Limit 1/Tag).")
            return

    # 1. Alle Angles abfragen
    all_proposals: list[StoryProposal] = []
    angle_modules = {
        # matchOfDay (Elo-„Spiel des Tages") raus (16.06.2026, Lucas). travelAlarm rein.
        "travelAlarm":     travel_alarm,
        "killerStat":      killer_stat,
        "underdogRecap":   underdog_recap,
        "playerSpotlight": player_spotlight,
    }
    for angle_name, mod in angle_modules.items():
        if FORCE_ANGLE and FORCE_ANGLE != angle_name:
            continue
        try:
            ps = mod.generate(today_iso)
            print(f"  · {angle_name}: {len(ps)} Vorschläge")
            all_proposals.extend(ps)
        except Exception as e:
            print(f"  ❌ {angle_name} crashed: {e}")
            import traceback; traceback.print_exc()

    if not all_proposals:
        print("\n❌ Keine Story-Vorschläge — Engine hat nichts gefunden")
        return

    # 2. Ranking + Übersicht
    all_proposals.sort(key=lambda p: p.score, reverse=True)
    print(f"\n=== Alle Vorschläge ({len(all_proposals)}) sortiert ===")
    for p in all_proposals[:10]:
        print(f"  {proposal_summary(p)}")

    # 3. Master-Selector mit Dedup
    state = load_state()
    recent = recent_entities(state)
    print(f"\n=== Dedup-Pool (entities letzte 4 Tage): {len(recent)} ===")
    if recent:
        print(f"     {sorted(recent)[:8]}")

    top = select_top(all_proposals, recent_entities=recent, min_score=0.30)
    if not top:
        print("\n❌ Keine Story über Min-Score 0.30 oder alle deduped")
        return

    print(f"\n🏆 TOP-PICK: {proposal_summary(top)}")

    # 4. Fact-Verifier
    verify_report = verify_proposal(top, max_drift_pct=5.0)
    print(f"\n=== Verifier ===")
    print(f"  ok: {verify_report['ok']}  ({verify_report['checked']} Slots geprüft)")
    if not verify_report["ok"]:
        print(f"  FAILS:")
        for name, reason in verify_report["failures"]:
            print(f"    · {name}: {reason}")

    # 5. Proposal-File für Audit
    if not DRY_RUN:
        with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "today":     today_iso,
                "chosen":    top.to_dict(),
                "verifier":  verify_report,
                "all":       [p.to_dict() for p in all_proposals],
            }, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n📝 {PROPOSALS_FILE.name} geschrieben")

    # 6. HTML rendern + Combined-Preview speichern
    hook_html, info_html, combined = _render_proposal_html(top)

    OUTPUTS_DIR.mkdir(exist_ok=True)
    today_short = today_iso[:10]
    entity_safe = top.entity_key.replace(':', '-').replace('/', '-')
    base_name = f"{today_short}_{top.angle_id}_{entity_safe}"

    combined_path = OUTPUTS_DIR / f"{base_name}_preview.html"
    hook_html_path = OUTPUTS_DIR / f"{base_name}_hook.html"
    info_html_path = OUTPUTS_DIR / f"{base_name}_info.html"
    hook_png_path  = OUTPUTS_DIR / f"{base_name}_hook.png"
    info_png_path  = OUTPUTS_DIR / f"{base_name}_info.png"

    if not DRY_RUN:
        combined_path.write_text(combined, encoding="utf-8")
        hook_html_path.write_text(hook_html, encoding="utf-8")
        info_html_path.write_text(info_html, encoding="utf-8")
        print(f"📺 Vorschau-HTML: {combined_path.relative_to(BASE)}")

    # 7. PNG-Render (Hook + Info als separate Bilder)
    hook_png = _render_html_to_png(hook_html, hook_png_path) if not DRY_RUN else None
    info_png = _render_html_to_png(info_html, info_png_path) if not DRY_RUN else None
    if hook_png: print(f"📸 Hook-PNG: {hook_png.name}")
    if info_png: print(f"📸 Info-PNG: {info_png.name}")

    # 8. Telegram-Send: erst Caption-Text-Nachricht, dann beide PNGs
    # FIX 11.06.2026: NUR senden wenn der Fact-Verifier ok ist. Vorher wurde
    # trotz Verifier-FAIL gesendet (heute 2× matchOfDay mit verifier_fail an den
    # Channel) — ungeprüfte Zahlen dürfen NICHT raus. Bei Fail: kein Send, nur
    # Audit-Record (status=verifier_fail unten).
    if not DRY_RUN and not verify_report["ok"]:
        print("\n🛑 Verifier FAILED — Story wird NICHT gesendet (ungeprüfte Fakten).")
    if not DRY_RUN and verify_report["ok"]:
        # Header-Text als Einleitung (Story-Header + Verifier-Status)
        header_text = _telegram_preview_text(top, verify_report)
        _send_telegram_text(header_text)

        hook_sent = False
        info_sent = False
        # Hook-Caption mit Story-Headline
        hs = top.hook_slots
        big   = _slot_val(hs.get("big_number", ""))
        sub   = _slot_val(hs.get("sub_title", ""))
        # Strip HTML tags für caption
        import re
        plain = lambda s: re.sub(r"<[^>]+>", "", s)
        hook_caption = f"🎬 <b>WM Live-Story · Hook</b>\n<code>{big}</code> {plain(sub)}"
        info_caption = f"🎬 <b>WM Live-Story · Info</b>\n{plain(_slot_val(top.info_slots.get('name','')))}"

        if hook_png and hook_png.exists():
            hook_sent = _send_telegram_photo(hook_png, hook_caption)
            print(f"  {'✅' if hook_sent else '❌'} Hook-PNG an Telegram")
        if info_png and info_png.exists():
            info_sent = _send_telegram_photo(info_png, info_caption)
            print(f"  {'✅' if info_sent else '❌'} Info-PNG an Telegram")

        # Log-Eintrag für UI-Tracking
        _append_telegram_log(top, hook_sent, info_sent)
        print(f"📝 telegram-log.json aktualisiert")

    # 9. State persistieren
    if not DRY_RUN:
        status = "posted" if verify_report["ok"] else "verifier_fail"
        record_post(top, status=status)
        print(f"💾 State: {status}")


if __name__ == "__main__":
    main()
