#!/usr/bin/env python3
"""
sharp_z_vorwaerts.py — 25.09.2026. Vorwaertsmessung: traegt das Band zwischen z=1,282 und z=1,645?

Anlass: der z-Sweep vom 01.09.2026 (s. Kopf von `sharp_gate.py`, Block „Der Regler"). Auf EINEM
Wochenfenster lieferte z=1,282 die bessere Vorwaerts-Leistung als das heutige 1,645 — aber vier
z-Werte auf einem Fenster: der Beste ist teilweise Zufall. Belegt war nur, dass 1,645 NICHT besser
ist. Diese Datei beantwortet die Frage vorwaerts, statt sie ein zweites Mal rueckwaerts zu rechnen.

── Was eingefroren wird (einmal, nie ueberschrieben) ─────────────────────────────────────────
Am Tag der Anmeldung werden alle Wallets aus `poly_wallet_track.json` klassifiziert:

    streng   is_sharp bei z=1,645                  (das heutige Gate)
    band     is_sharp bei z=1,282, NICHT bei 1,645  (das, was eine Lockerung dazunimmt)
    basis    alle uebrigen                          (Vergleich, dynamisch)

Die Adresslisten stehen danach fest. Eine Wallet, die spaeter auf- oder absteigt, bleibt in ihrer
Kohorte — sonst misst man, wer SPAETER gut aussah, und das ist wieder Rueckschau.

── Was gemessen wird ─────────────────────────────────────────────────────────────────────────
Nur Tage STRIKT NACH dem Anmeldetag, aus dem Tages-Gedaechtnis `tage`
({tag: [n, clvSum, wins, quad, gewinn, einsatz, nGeld]}). Der Anmeldetag selbst zaehlt nicht —
er kann Aufloesungen von vor der Klassifikation enthalten. `tageNachtrag` zaehlt NIE: das ist
rekonstruierte Vergangenheit.

⚠️ `WALLET_TAGE_KEEP` = 60 Tage. Laeuft die Messung laenger, fallen die ersten Tage aus dem
Gedaechtnis und die Zahl SCHRUMPFT. `tageAbgeschnitten` sagt das, statt es zu verschweigen.

── Entscheidung, vorher festgelegt ──────────────────────────────────────────────────────────
Gezaehlt wird in Aufloesungen MIT Geld (`nGeld`), weil der Profit entscheidet, nicht der CLV
(Lucas, 22.09.: „Wichtiger ist der Profit"). Bei `ZIEL_N` Band-Aufloesungen:

    z=1,282 wird fuer das Whale-/Conviction-Gate uebernommen, wenn BEIDES gilt:
      · Band-ROI  >  Basis-ROI
      · Band-ROI  >= Streng-ROI − 5 Prozentpunkte
    sonst bleibt 1,645. Der Public-Push bleibt in jedem Fall bei 1,645.

Die Signatur friert Zuschnitt UND Kriterium ein. Aendert sich eins davon, meldet die Datei
`ungueltig` — eine Grenze, die man verschiebt, bis die Zahl passt, ist kein Vorwaertstest.

Rein bis auf `main()`. Netzfrei.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import sharp_gate as SG

BASE = Path(__file__).resolve().parent
TRACK_FILE = "poly_wallet_track.json"
OUT_FILE = "sharp_z_vorwaerts.json"

Z_STRENG = 1.645
Z_LOCKER = 1.282
ZIEL_N = 150
TAGE_KEEP = int(os.environ.get("WALLET_TAGE_KEEP") or 60)
KRITERIUM = ("bei nGeld(band)>=%d: z=1.282 uebernehmen wenn roi(band)>roi(basis) "
             "und roi(band)>=roi(streng)-0.05; Public bleibt 1.645" % ZIEL_N)
SIGNATUR = ("streng=is_sharp(z=%.3f) | band=is_sharp(z=%.3f) und nicht streng | basis=Rest | "
            "min_n=%d | Tage>angemeldet aus tage[], ohne tageNachtrag | %s"
            % (Z_STRENG, Z_LOCKER, SG.SHARP_MIN_N, KRITERIUM))


def _now():
    return datetime.now(timezone.utc)


# ── Anmeldung ─────────────────────────────────────────────────────────────────────────────
def kohorten(scores) -> dict:
    """{streng: [...], band: [...]} — sortierte Adresslisten. REIN."""
    streng, band = [], []
    for adr, s in (scores or {}).items():
        if not isinstance(s, dict):
            continue
        if SG.is_sharp(s, z=Z_STRENG):
            streng.append(adr)
        elif SG.is_sharp(s, z=Z_LOCKER):
            band.append(adr)
    return {"streng": sorted(streng), "band": sorted(band)}


def anmelden(reg, scores, now=None) -> dict:
    """Friert Kohorten + Signatur ein, falls noch nicht geschehen. Nie ueberschreiben. REIN."""
    reg = dict(reg or {})
    if isinstance(reg.get("anmeldung"), dict):
        return reg
    k = kohorten(scores)
    reg["anmeldung"] = {
        "angemeldet": (now or _now()).isoformat(),
        "signatur": SIGNATUR,
        "zielN": ZIEL_N,
        "kriterium": KRITERIUM,
        "kohorten": k,
        "nWallets": {"streng": len(k["streng"]), "band": len(k["band"]),
                     "gesamt": len(scores or {})},
    }
    return reg


# ── Messung ───────────────────────────────────────────────────────────────────────────────
def _leer():
    return {"wallets": 0, "aktiv": 0, "n": 0, "wins": 0, "clvSum": 0.0,
            "gewinn": 0.0, "einsatz": 0.0, "nGeld": 0}


def _addiere(acc, score, ab_tag):
    """Summiert die Tage STRIKT nach `ab_tag` einer Wallet in `acc`. REIN."""
    acc["wallets"] += 1
    t = (score or {}).get("tage") if isinstance(score, dict) else None
    if not isinstance(t, dict):
        return
    beigetragen = False
    for tag, v in t.items():
        if str(tag) <= ab_tag or not isinstance(v, (list, tuple)) or len(v) < 4:
            continue
        try:
            acc["n"] += int(v[0]); acc["clvSum"] += float(v[1]); acc["wins"] += int(v[2])
            if len(v) >= 6:
                acc["gewinn"] += float(v[4]); acc["einsatz"] += float(v[5])
                acc["nGeld"] += int(v[6]) if len(v) >= 7 else 0
        except (TypeError, ValueError):
            continue
        beigetragen = True
    if beigetragen:
        acc["aktiv"] += 1


def _kennzahlen(acc) -> dict:
    n, e = acc["n"], acc["einsatz"]
    return {
        "wallets": acc["wallets"], "aktiv": acc["aktiv"],
        "n": n, "nGeld": acc["nGeld"],
        "treffer": round(acc["wins"] / n, 4) if n else None,
        "trefferUg": round(SG.wilson_lb(acc["wins"], n, 1.645), 4) if n else None,
        "clv": round(acc["clvSum"] / n, 2) if n else None,
        "gewinn": round(acc["gewinn"], 2), "einsatz": round(e, 2),
        "roi": round(acc["gewinn"] / e, 4) if e > 0 else None,
    }


def urteil(stand) -> dict:
    """Das vorher festgelegte Kriterium, angewandt. Vor ZIEL_N: kein Urteil. REIN."""
    b, s, x = stand.get("band") or {}, stand.get("streng") or {}, stand.get("basis") or {}
    if (b.get("nGeld") or 0) < ZIEL_N:
        return {"status": "sammelt", "text": "%d von %d Band-Aufloesungen mit Geld"
                % (b.get("nGeld") or 0, ZIEL_N)}
    rb, rs, rx = b.get("roi"), s.get("roi"), x.get("roi")
    if rb is None or rs is None or rx is None:
        return {"status": "unklar", "text": "Ziel erreicht, aber ein ROI fehlt — kein Urteil"}
    ok = rb > rx and rb >= rs - 0.05
    return {"status": "locker" if ok else "streng",
            "text": ("z=1,282 uebernehmen (Band %+.1f %% · Streng %+.1f %% · Basis %+.1f %%)"
                     if ok else
                     "bei 1,645 bleiben (Band %+.1f %% · Streng %+.1f %% · Basis %+.1f %%)")
            % (rb * 100, rs * 100, rx * 100)}


def messen(reg, scores, heute=None) -> dict:
    """Stand je Kohorte seit der Anmeldung. REIN."""
    a = (reg or {}).get("anmeldung")
    if not isinstance(a, dict):
        return {"status": "nicht angemeldet"}
    if a.get("signatur") != SIGNATUR:
        return {"status": "ungueltig",
                "text": "Zuschnitt oder Kriterium seit der Anmeldung geaendert — misst nichts mehr"}
    ab_tag = str(a.get("angemeldet") or "")[:10]
    k = a.get("kohorten") or {}
    streng, band = set(k.get("streng") or []), set(k.get("band") or [])
    acc = {"streng": _leer(), "band": _leer(), "basis": _leer()}
    for adr, s in (scores or {}).items():
        ziel = "streng" if adr in streng else "band" if adr in band else "basis"
        _addiere(acc[ziel], s, ab_tag)
    stand = {kk: _kennzahlen(v) for kk, v in acc.items()}
    try:
        tage = (date.fromisoformat(str(heute or _now().date())) - date.fromisoformat(ab_tag)).days
    except ValueError:
        tage = None
    stand["tageSeitAnmeldung"] = tage
    stand["tageAbgeschnitten"] = bool(tage is not None and tage >= TAGE_KEEP)
    stand["urteil"] = urteil(stand)
    stand["status"] = stand["urteil"]["status"]
    return stand


def main() -> int:
    print("=== sharp_z_vorwaerts.py ===")
    try:
        track = json.loads((BASE / TRACK_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("  🛑 %s nicht lesbar — nichts angemeldet, nichts gemessen." % TRACK_FILE)
        return 0
    scores = track.get("scores") if isinstance(track, dict) else None
    if not isinstance(scores, dict) or not scores:
        print("  🛑 keine Wallet-Scores — nichts angemeldet, nichts gemessen.")
        return 0
    try:
        reg = json.loads((BASE / OUT_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        reg = {}
    except (OSError, ValueError):
        # Eine kaputte Datei NICHT durch eine neue Anmeldung ersetzen — dann waere der Zeitstempel weg.
        print("  🛑 %s unlesbar — Anmeldung wird NICHT neu geschrieben." % OUT_FILE)
        return 0
    neu = "anmeldung" not in reg
    reg = anmelden(reg, scores)
    reg["stand"] = messen(reg, scores)
    reg["generatedAt"] = _now().isoformat()
    from safe_write import write_json_atomic
    write_json_atomic(BASE / OUT_FILE, reg, indent=1)
    a = reg["anmeldung"]
    if neu:
        print("  📌 angemeldet: %d streng · %d band" % (a["nWallets"]["streng"], a["nWallets"]["band"]))
    st = reg["stand"]
    print("  %s" % (st.get("urteil") or {}).get("text", st.get("status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
