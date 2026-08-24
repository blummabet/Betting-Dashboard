#!/usr/bin/env python3
"""24.08.2026 (Lucas: „hat es auch Auswirkung auf die Push-Messages?") — nein, hatte es nicht.

Der Konflikt lebte nur im Dashboard (`_pwWhalePlays`, JS). `poly_whale_watch.build_card()` sieht genau
EINE Position; dass zeitgleich eine andere Top-20-Wallet auf der Gegenseite desselben Markts sitzt,
tauchte nirgends auf. Deshalb gingen für INOX Division v Butterfly zwei Push raus (#7 auf INOX,
#9 auf Butterfly), ohne sich zu erwähnen.

Es gab schon `_contested_market()` (12.08.) — aber nur im PUBLIC-Kanal und in DOLLAR (≥$100K je Seite).
$8,5K gegen $7K segelt da durch. Der Konflikt ist keine Größen-, sondern eine **Rang**-Frage: sitzt
eine andere bewiesene Top-Wallet dagegen, ist das Signal mehrdeutig — egal ob $7K oder $70K.

Lucas' Wahl: Trades warnen, Public unterdrücken. Folgt beiden Vorbildern im Code — der Tab flaggt und
sortiert runter, Public unterdrückt umkämpfte Märkte schon heute.
"""
import io, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
P = "poly_whale_watch.py"


def rd():
    with io.open(os.path.join(BASE, P), encoding="utf-8") as f:
        return f.read()


def wr(s):
    with io.open(os.path.join(BASE, P), "w", encoding="utf-8") as f:
        f.write(s)


def patch(marker, old, new, label):
    s = rd()
    if marker in s:
        print("  = %-48s schon drin" % label)
        return
    if s.count(old) != 1:
        print("  ! %-48s Anker %dx" % (label, s.count(old)))
        sys.exit(1)
    wr(s.replace(old, new, 1))
    print("  + %-48s gepatcht" % label)


# ── 1) Konstante ───────────────────────────────────────────────────────────
patch("CONFLICT_TOP_N",
      'CONTEST_MIN_USD       = float(os.environ.get("WHALE_CONTEST_MIN_USD")     or 100000)   # 12.08.2026 (Lucas): Public — Gross-Einstiege ab so viel auf ZWEI Seiten = umkaempft -> gar nicht posten\n',
      'CONTEST_MIN_USD       = float(os.environ.get("WHALE_CONTEST_MIN_USD")     or 100000)   # 12.08.2026 (Lucas): Public — Gross-Einstiege ab so viel auf ZWEI Seiten = umkaempft -> gar nicht posten\n'
      'CONFLICT_TOP_N        = int(os.environ.get("WHALE_CONFLICT_TOP_N")        or 20)       # 24.08.2026 (Lucas, INOX-Fall): haelt eine andere Wallet aus den Top-N die Gegenseite, ist das Signal mehrdeutig — RANG statt Dollar, deshalb greift es auch bei $7K.\n',
      "Konstante CONFLICT_TOP_N")

# ── 2) Detektor ────────────────────────────────────────────────────────────
patch("def _conflicting_top_wallet(",
      "def _contested_market(key, broad, min_usd=CONTEST_MIN_USD):\n",
      'def _conflicting_top_wallet(pos, broad, scores, top=None):\n'
      '    """Sitzt eine ANDERE Top-N-Wallet auf einer anderen Seite desselben Markts? REIN/testbar.\n'
      '\n'
      '    24.08.2026 (Lucas\' INOX-Fall): zwei bewiesene Wallets auf Gegenseiten heben sich als Signal\n'
      '    weitgehend auf — dem einen zu folgen ist dort ein Muenzwurf. `_contested_market` fing das\n'
      '    nicht: es misst DOLLAR (>=$100K je Seite) und laeuft nur im Public-Kanal. Hier zaehlt der\n'
      '    RANG, damit auch ein $7K-Gegeneinstieg einer Top-Wallet auffaellt.\n'
      '\n'
      '    Gibt die bestplatzierte Gegen-Wallet zurueck: {"rank", "side", "usd", "wallet"} oder None.\n'
      '    """\n'
      '    top = top or CONFLICT_TOP_N\n'
      '    key, side, me = pos.get("key"), pos.get("side"), str(pos.get("wallet") or "").lower()\n'
      '    if not (key and side):\n'
      '        return None\n'
      '    m = (broad or {}).get(key) if isinstance(broad, dict) else None\n'
      '    if not isinstance(m, dict):\n'
      '        return None\n'
      '    ranks = _sharp_rank_map(scores)\n'
      '    best = None\n'
      '    for w in (m.get("whales") or []):\n'
      '        if not isinstance(w, dict):\n'
      '            continue\n'
      '        w_side, w_wallet = w.get("side"), str(w.get("wallet") or "").lower()\n'
      '        if not w_side or w_side == side or not w_wallet or w_wallet == me:\n'
      '            continue\n'
      '        r = ranks.get(w_wallet)\n'
      '        if not r or r > top:\n'
      '            continue\n'
      '        if best is None or r < best["rank"]:\n'
      '            best = {"rank": r, "side": w_side, "usd": float(w.get("usd") or 0), "wallet": w_wallet}\n'
      '    return best\n'
      '\n'
      '\n'
      "def _contested_market(key, broad, min_usd=CONTEST_MIN_USD):\n",
      "_conflicting_top_wallet()")

# ── 3) Trades-Card: Warnzeile ──────────────────────────────────────────────
patch("haelt die Gegenseite",
      '    lines.append(_wallet_line(scores, pos.get("wallet")))\n'
      '    if key:\n'
      '        lines.append(\'<a href="https://polymarket.com/event/%s">→ Markt öffnen ↗</a>\' % _esc(key))\n'
      '    if extra and extra > 0:\n',
      '    # 24.08.2026 (Lucas): steht eine andere Top-Wallet dagegen, gehoert das IN die Nachricht —\n'
      '    # sonst liest sich der Push als Empfehlung, obwohl die Gegenseite genauso gut belegt ist.\n'
      '    _cf = _conflicting_top_wallet(pos, broad, scores)\n'
      '    if _cf:\n'
      '        lines.append("⚔️ <b>Rang #%d haelt die Gegenseite</b> — %s (%s)"\n'
      '                     % (_cf["rank"], _esc(_cf["side"]), _usd(_cf["usd"])))\n'
      '    lines.append(_wallet_line(scores, pos.get("wallet")))\n'
      '    if key:\n'
      '        lines.append(\'<a href="https://polymarket.com/event/%s">→ Markt öffnen ↗</a>\' % _esc(key))\n'
      '    if extra and extra > 0:\n',
      "Trades-Card: Warnzeile")

# ── 4) Public: unterdrücken ────────────────────────────────────────────────
patch("Top-Wallet haelt die Gegenseite",
      '    _pre_contest = len(pub_cand)\n'
      '    pub_cand = [c for c in pub_cand if not _contested_market(c[1].get("key"), broad)]   # 12.08.2026 (Lucas): Gegenseiten-Krieg raus — umkaempfte Spiele gar nicht posten\n'
      '    if _pre_contest != len(pub_cand):\n'
      '        print(f"  \\U0001f91d {_pre_contest - len(pub_cand)} umkaempfte(s) Spiel(e) unterdrueckt (Gross-Geld auf beiden Seiten)")\n',
      '    _pre_contest = len(pub_cand)\n'
      '    pub_cand = [c for c in pub_cand if not _contested_market(c[1].get("key"), broad)]   # 12.08.2026 (Lucas): Gegenseiten-Krieg raus — umkaempfte Spiele gar nicht posten\n'
      '    if _pre_contest != len(pub_cand):\n'
      '        print(f"  \\U0001f91d {_pre_contest - len(pub_cand)} umkaempfte(s) Spiel(e) unterdrueckt (Gross-Geld auf beiden Seiten)")\n'
      '    # 24.08.2026 (Lucas, INOX-Fall): dasselbe nach RANG statt Dollar. Zwei sich widersprechende\n'
      '    # Empfehlungen kurz nacheinander sind im oeffentlichen Kanal das Schlechteste — im Trades-\n'
      '    # Kanal steht stattdessen die Warnzeile, dort entscheidet Lucas selbst.\n'
      '    _pre_conf = len(pub_cand)\n'
      '    pub_cand = [c for c in pub_cand if not _conflicting_top_wallet(c[1], broad, scores)]\n'
      '    if _pre_conf != len(pub_cand):\n'
      '        print(f"  \\u2694\\ufe0f  {_pre_conf - len(pub_cand)} Post(s) unterdrueckt — eine andere Top-Wallet haelt die Gegenseite")\n',
      "Public: Konflikt unterdrücken")

print("\nFertig.")
