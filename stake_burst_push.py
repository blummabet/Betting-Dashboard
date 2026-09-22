#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stake_burst_push.py — 11.09.2026 (Lucas): Einsatz-Bursts bei Stake in den TRADES-Channel.

Der Anlass war eine Nachricht aus einer VIP-Gruppe, die Lucas geschickt hat:

    Cienciano - Montevideo City Torque · Volume: 17605.64$ · 7 bets / 4 bets in 48 sec
    Player to be carded (sure sub) - Cabello, Carlos
      $11580.35 x 3.35 · $1994 x 3.35 · $2990 x 3.35 · $1041.29 x 3.35

Lucas: „mir geht's bei Stake wirklich um die Geldeinsaetze, die dort reinfliessen."

Vier Wetten, EINE Auswahl, DIESELBE Quote, innerhalb einer Minute. Genau dieses Muster laesst
sich im Highroller-Feed erkennen — Wallets und Nutzer nicht (Stake gibt `user` fuer alle 20.000
Zeilen als null zurueck, obwohl das Feld im Schema steht; sie anonymisieren serverseitig).

── Warum gerade diese Schwellen ──────────────────────────────────────────────────────────────
Gemessen an 15.646 abgerechneten Einzelwetten (aus `abrechnung`, NICHT aus dem Feed-Status —
der zieht nicht nach und haette die Basis auf 1.524 gedrueckt):

    >=3 Wetten, 5 Min, ab $10k                     29,0 Bursts/Tag   ROI  +7,1 %   UG  +1,0 %
    >=4 Wetten, 5 Min, ab $10k                     16,5              ROI +10,2 %   UG  +3,4 %
    >=4 Wetten, 5 Min, ab $10k, GLEICHE Quote       5,8 (live)       ROI +29,0 %   UG +19,1 %
                                                    6,8 (vor)        ROI  +8,8 %   UG  +1,1 %

Der wirksame Hebel ist NICHT der Betrag — im Gegenteil: ab $50k faellt der ROI auf −12,3 %, die
Kante sitzt im Band $10-20k. Der Hebel ist die GLEICHE QUOTE: der Buchmacher hat auf das Geld
nicht reagiert. Genau das zeigt auch Lucas' Beispiel (viermal 3,35).

Lucas: „Schwellen muessen wir sicher nachstellen, weil hab Angst dass da zu viel kommt." Deshalb
zusaetzlich ein harter Deckel je Lauf. Der Deckel ist eine LAERMGRENZE, keine Rangfolge — er
nimmt die aeltesten zuerst, weil jede Sortierung nach Guete eine Behauptung waere, die wir nicht
belegen koennen. Wie viele er unterdrueckt hat, steht in der Nachricht und im Buch.

⚠️ Beide Phasen laufen mit und werden GETRENNT gestempelt. Live ist die staerkere Messung, aber
Lucas' eigenes Beispiel war vor Anpfiff — eine der beiden vorab wegzuwerfen hiesse, die Frage
schon beantwortet zu haben.

Env:
  STAKE_BURST_MIN_N      Wetten je Burst (Default 4)
  STAKE_BURST_FENSTER_S  Zeitfenster in Sekunden (Default 300)
  STAKE_BURST_MIN_USD    Mindestsumme des Bursts (Default 10000)
  STAKE_BURST_MAX        max Pushes je Lauf (Default 4)
  TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID — ohne Token = Vorschau (stdout)
"""
from __future__ import annotations
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram_trades import send_trades_message

BASE = Path(__file__).resolve().parent
LEDGER_FILE = BASE / "stake_burst_ledger.json"
WETTEN_FILE = BASE / "stake_bet_ledger.json"   # 13.09.2026: die Quelle der Abrechnung
VERWORFEN_FILE = BASE / "stake_burst_verworfen.json"   # 13.09.2026: das Beinahe-Buch
VERWORFEN_KEEP = 1500
SEEN_FILE = BASE / "stake_burst_seen.json"
QUELLE_FILE = BASE / "stake_highroller.json"

MIN_N = int(os.environ.get("STAKE_BURST_MIN_N") or 4)
FENSTER_S = float(os.environ.get("STAKE_BURST_FENSTER_S") or 300)
MIN_USD = float(os.environ.get("STAKE_BURST_MIN_USD") or 10000)
MAX_PUSH = int(os.environ.get("STAKE_BURST_MAX") or 4)
# 13.09.2026 (Lucas: „aber jetzt rennen die Bursts normal als Push weiter und ich krieg die
# weiter rein"). Der Schalter trennt MESSEN von SENDEN. Vorher waren beide dasselbe: eine
# Buchzeile entstand nur, wenn `send_trades_message` erfolgreich war — den Kanal stillzulegen
# haette also auch die Messung stillgelegt, und die zwei Wochen Beobachtung waeren weg gewesen.
#
# Dieselbe Trennung wie im Pick-Schattenbuch: das Buch schreibt JEDEN erkannten Burst mit, der
# Push ist eine davon unabhaengige Entscheidung. Was nicht rausging, traegt `push: false` und
# den Grund — die Kanal-Bilanz in den Stats zaehlt weiterhin nur, was den Kanal verlassen hat.
PUSH_AN = (os.environ.get("STAKE_BURST_PUSH") or "true").strip().lower() \
    not in ("false", "0", "nein", "off", "aus")

# 🎯 Mindestquote — 12.09.2026 (Lucas: „wieso kommt da so eine odd?", zu @1,01 und @1,15).
#
# Der Push hatte KEINEN Quotenboden. Beim Poly-Band habe ich einen gebaut (1,35, aus Lucas'
# eigener Ansage) und hier nie einen gesetzt — dieselbe Luecke, dieselbe Woche.
#
# Gemessen an den 72 Bursts der letzten sechs Tage: **19 liegen unter Quote 1,10** (davon sechs
# bei 1,01). Das ist kein Signal, das ist jemand, der auf ein entschiedenes Spiel 1 % abgreift.
# Der Boden macht das Band auf BEIDEN Achsen besser — er nimmt Laerm UND hebt die Kante:
#
#     ohne Boden   72 Bursts   n=365   86,0 % Treffer   ROI +29,1 %   UG +22,3 %
#     ab 1,20      43          n=247   79,4 %           ROI +40,9 %   UG +31,0 %
#     ab 1,35      36          n=212   77,8 %           ROI +45,9 %   UG +34,3 %
#
# 1,35 ist im Projekt ohnehin der Boden (pick-engine.js, stake-radar.js, Poly-Dominanz) — eine
# vierte Zahl waere hier nur eine weitere, die man im Kopf behalten muss.
MIN_QUOTE = float(os.environ.get("STAKE_BURST_MIN_QUOTE") or 1.35)

# 🔢 Wie viele Tickets macht einen Burst? — 16.09.2026 (Lucas: „das sollte nicht beschraenkt
# sein auf sieben oder vier Wetten … vielleicht reichen da drei schnelle Einsaetze").
#
# Gemessen am Ledger 10.–16.09. (16.104 abgerechnete Einzelwetten, 5,37 Tage), EIN Burst je
# Auswahl — also genau die Einheit, die auch gepusht wird — >=$10k, Quote>=1.35, Rendite aus
# der Abrechnung der Wetten selbst, Untergrenze als 5-%-Bootstrap ueber die Bursts:
#
#     Quotenregel      n>=5              n>=4              n>=3              n>=2
#     strikt gleich    +65,8 % (UG +26,3 %)  +28,4 % (−1,0 %)  +13,6 % (−8,5 %)  +5,9 % (−6,6 %)
#     groesste Gruppe  +36,2 % (UG  +5,1 %)  +19,4 % (−3,8 %)   +9,0 % (−9,0 %)  +5,1 % (−6,5 %)
#     Quote egal       +27,0 % (UG  +5,4 %)  +14,1 % (−2,6 %)   +8,6 % (−5,8 %)  +0,6 % (−9,3 %)
#     Bursts/Tag       3,4 / 6,0 / 10,4      6,1 / 9,3 / 15,5   11,0 / 15,3 / 24,8  27,6 / 33,0 / 51,2
#
# Die Treppe ist in ALLEN DREI Quotenregeln streng monoton: je mehr Tickets, desto staerker.
# Runter auf 3 kauft das Doppelte an Menge und verliert den Beleg (Untergrenze faellt von
# −1,0 % auf −8,5 %). Bewiesen ist derzeit nur n>=5. Zwoelf Zellen, ein Muster — die einzelne
# Zelle ist Rauschen, die Monotonie ist es nicht.
#
# ⚠️ Die Rendite ist die der WALE, nicht unsere: wir steigen Minuten spaeter ein, moeglicherweise
# zu schlechteren Quoten. Fuer Stake gibt es kein CLV, also ist das die beste verfuegbare
# Naeherung — und sie taugt fuer den VERGLEICH der Schwellen, nicht als Renditeversprechen.
#
# MIN_N bleibt deshalb bei 4 (und nicht bei 3), aber der Preis dieser Schwelle wird ab jetzt
# MITGESCHRIEBEN statt geschaetzt: Cluster, die NUR an der Anzahl scheitern, gehen mit dem
# Grund `unter_min_n` ins Beinahe-Buch. Nach zwei Wochen beantwortet unser eigenes Buch die
# Frage — nicht ein Skript, das ich einmal laufen lasse.
BEOBACHTEN_AB_N = int(os.environ.get("STAKE_BURST_BEOBACHTEN_AB_N") or 3)

# ⏱️ Frische — 12.09.2026 (Lucas: „Wertlos war gestern schon. Wieso kommt das jetzt?").
#
# Der gemeldete Burst lag auf Venezia-Fiorentina, 11.09. um 20:29 — gepusht am 12.09. Der Grund:
# `stake_highroller.json` haelt ein 48-Stunden-Fenster, und die Erkennung hatte KEINE
# Altersgrenze. Sie fand Bursts irgendwo im Fenster, auch zwoelf Stunden alte.
#
# Genau dieselbe Fehlerklasse wie beim Betfair-Halbzeit-Push einen Tag vorher („die Tore alle
# schon ewig her"): die Regel prueft den Zustand, aber nicht, WANN er galt.
#
# 🔴 17.09.2026 (Lucas: „der Betfair-Cron sollte alle 10 min, tut er aber nicht — in Wahrheit
# rennt er alle 15 min"). Hier stand „der Runner laeuft alle 10 Minuten, 30 Minuten sind also
# reichlich Puffer". Gemessen an `health/betfair.json`: 17 von 19 Abstaenden exakt 15,0 Minuten.
# Der Puffer ist also nicht das Dreifache eines Laufs, sondern das Doppelte — und weil der
# Stake-Feed nur 50 Eintraege (~21 Min) im Gedaechtnis hat, kann ein Burst beim ersten Sehen
# schon 15 Minuten alt sein. 30 bleibt richtig, aber knapp: der naechste Lauf ist die letzte
# Chance, nicht die zweitletzte. Wer hier schraubt, muss den echten Takt kennen, nicht den
# im Cron behaupteten — deshalb steht die Messung jetzt dabei.
MAX_ALTER_MIN = float(os.environ.get("STAKE_BURST_MAX_ALTER_MIN") or 30)
LEDGER_KEEP = 800
SEEN_KEEP_H = 48.0


def _load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p, data) -> None:
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _usd(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "?"
    if x >= 1_000_000:
        return "$%.1fM" % (x / 1_000_000)
    if x >= 1000:
        return "$%.1fK" % (x / 1000)
    return "$%d" % round(x)


def _quote(w):
    q = w.get("beinQuote")
    if not isinstance(q, (int, float)):
        q = w.get("quote")
    return q if isinstance(q, (int, float)) and q > 1 else None


# Der Rueckfall kommt aus dem SAMMLER, nicht aus einer zweiten Liste hier. Sonst driftet er
# beim naechsten Umbau der Sperre auseinander — und genau das ist am 12.09. passiert, als
# „Cricket" dort dazukam und hier ein hartkodiertes ("US-Sport",) stehen blieb. Defensiv
# gekapselt: faellt der Import aus, bleibt der Push lauffaehig statt zu sterben.
try:
    from stake_highroller_fetch import GESPERRT as _SAMMLER_GESPERRT
    GESPERRT_FALLBACK = tuple(sorted(_SAMMLER_GESPERRT))
except Exception:                                            # pragma: no cover
    GESPERRT_FALLBACK = ("US-Sport", "Cricket")


def gesperrte_kats(quelle=None):
    """Die ausgeblendeten Sportarten — aus `stake_highroller.json`, nicht hier hartkodiert. REIN.

    12.09.2026 (Lucas: „ok das waeren dann nur bursts zu Top Ligen oder"). Beim Nachzaehlen fiel
    auf, dass der Burst-Push als EINZIGE Stake-Flaeche keine Sperrliste las. Der Sammler fuehrt
    sie (`stake_highroller_fetch.GESPERRT`, seit 03.09.: „Ganze US-Sport brauch ich aktuell mal
    nicht") und schreibt sie als `gesperrt` ins Artefakt; der Radar liest sie von dort. Also
    liest dieser Push sie auch von dort — eine zweite Liste waere genau die Drift, die im
    Poly-Band einen Tag vorher aufgeraeumt wurde.

    Gemessen betrifft es 1 von 72 Bursts. Der Aufwand lohnt trotzdem: die Konsistenz ist der
    Punkt, nicht die eine Karte.
    """
    got = (quelle or {}).get("gesperrt") if isinstance(quelle, dict) else None
    kats = [str(c) for c in got if c] if isinstance(got, list) else []
    return kats or list(GESPERRT_FALLBACK)


def bursts(wetten, min_n=None, fenster_s=None, min_usd=None, gesperrt=None,
           min_quote=None, max_alter_min=None, now=None, verworfen=None,
           beobachten_ab_n=None) -> list:
    """Alle Einsatz-Bursts im Feed. REIN (alles injizierbar).

    Ein Burst ist: `min_n` Einzelwetten auf DIESELBE Auswahl, innerhalb von `fenster_s`, zusammen
    mindestens `min_usd`, ALLE zur SELBEN Quote.

    Kombiwetten bleiben draussen — ihr Einsatz haengt an mehreren Spielen und ist keinem davon
    zurechenbar (dieselbe Regel wie im Stake-Radar seit 03.09.).

    Je Auswahl wird HOECHSTENS EIN Burst gemeldet (der erste). Sonst wuerde eine lange Serie von
    Wetten dieselbe Auswahl mehrfach ausloesen, und der Kanal saehe ein Ereignis als fuenf.
    """
    min_n = MIN_N if min_n is None else min_n
    fenster_s = FENSTER_S if fenster_s is None else fenster_s
    min_usd = MIN_USD if min_usd is None else min_usd
    gesperrt = list(GESPERRT_FALLBACK) if gesperrt is None else list(gesperrt)
    min_quote = MIN_QUOTE if min_quote is None else min_quote
    max_alter_min = MAX_ALTER_MIN if max_alter_min is None else max_alter_min
    beobachten_ab_n = BEOBACHTEN_AB_N if beobachten_ab_n is None else beobachten_ab_n
    now = now or datetime.now(timezone.utc)
    je_auswahl = {}
    je_gesperrt = {}
    for w in wetten or []:
        if not isinstance(w, dict) or w.get("kombi"):
            continue
        if w.get("kat") in gesperrt:
            # 13.09.2026: auch die gesperrten Sportarten laufen ins Beinahe-Buch — getrennt
            # gesammelt, damit spaeter beantwortbar ist, wie viel die Sperre kostet. Eine
            # Sperre, deren Preis niemand kennt, ist eine Vermutung mit Bestandsschutz.
            _a, _t = w.get("auswahlId"), _ts(w.get("ts"))
            if verworfen is not None and _a and _t is not None:
                je_gesperrt.setdefault(_a, []).append((_t, w))
            continue
        a, t, u, q = w.get("auswahlId"), _ts(w.get("ts")), w.get("einsatzUsd"), _quote(w)
        if not a or t is None or q is None:
            continue
        if not isinstance(u, (int, float)) or isinstance(u, bool) or u <= 0:
            continue
        je_auswahl.setdefault(a, []).append((t, w))
    aus = []
    for a, v in je_auswahl.items():
        v.sort(key=lambda z: z[0])
        # 🔴 16.09.2026 (Lucas: „wundert mich, dass von Tag auf Tag nicht mehrere Einsaetze
        # hintereinander sind … ich glaube, dass da irgendwo hakt"). Er hatte recht, und der
        # Fehler stand genau hier: BEI JEDEM `break` unten wurde die ganze AUSWAHL verlassen,
        # nicht nur das eine Fenster. Fiel also das erste Fenster einer Auswahl durch eine Regel
        # (uneinheitliche Quoten, Quote zu tief, Summe zu klein) oder war es schlicht zu alt,
        # dann wurden alle SPAETEREN Fenster derselben Auswahl nie mehr angesehen — obwohl ein
        # spaeteres Fenster juenger ist und andere Quoten tragen kann.
        #
        # Gemessen am Ledger vom 10.–16.09. (20.000 Wetten, 5,37 Tage), Schwellen unveraendert:
        #     heutiger Code (break):     22 Bursts   ·   Replay alle 10 Min, Alter 30: 25
        #     ohne den Fehl-break:       33 Bursts   ·   Replay: 35
        # Also rund jeder DRITTE gueltige Burst ging verloren — nicht an den Schwellen, sondern
        # an der Schleife. „Hoechstens ein Burst je Auswahl" war gewollt; „hoechstens ein
        # VERSUCH je Auswahl" war es nie.
        #
        # Das Beinahe-Buch bekommt weiterhin genau EINE Zeile je Auswahl (die des ersten
        # gescheiterten Fensters) — und nur dann, wenn die Auswahl am Ende gar keinen Burst
        # ergeben hat. Sonst stuende dieselbe Auswahl als Treffer UND als Beinahe im Buch.
        beinahe = None      # erstes Fenster ab `min_n`, das an einer Regel scheitert
        klein = None        # erstes Fenster UNTER `min_n`, das sonst sauber waere
        for i in range(len(v)):
            j = i
            while j + 1 < len(v) and (v[j + 1][0] - v[i][0]).total_seconds() <= fenster_s:
                j += 1
            if j - i + 1 < min_n:
                # Cluster unter der Anzahl-Schwelle: KEIN Push, aber eine Zeile im Beinahe-Buch,
                # wenn es sonst an nichts scheitert. Das ist der einzige Filter, dessen Preis
                # bisher nirgends stand — die Schwellen-Treppe oben musste ich dafuer aus dem
                # rollierenden Ledger rechnen, das nur fuenf Tage weit zurueckreicht.
                _n = j - i + 1
                if (klein is None and verworfen is not None and _n >= beobachten_ab_n
                        and (now - v[j][0]).total_seconds() / 60.0 <= max_alter_min):
                    _g = [z[1] for z in v[i:j + 1]]
                    _su = sum(float(x["einsatzUsd"]) for x in _g)
                    if (len({round(float(_quote(x)), 2) for x in _g}) == 1
                            and float(_quote(_g[0])) >= min_quote and _su >= min_usd):
                        klein = _beinahe(a, _g, _su, ["unter_min_n"], v[i][0], v[j][0])
                continue
            g = [z[1] for z in v[i:j + 1]]
            summe = sum(float(x["einsatzUsd"]) for x in g)
            # ⭐ ALLE Gruende sammeln statt beim ersten auszusteigen. Der Unterschied ist der
            # ganze Zweck des Beinahe-Buchs: „scheitert an GENAU EINER Regel" ist die Frage,
            # die man spaeter stellt, und die kann man nicht beantworten, wenn nur der erste
            # Grund notiert ist.
            gruende = []
            if len({round(float(_quote(x)), 2) for x in g}) != 1:
                gruende.append("quoten_uneinheitlich")
            if float(_quote(g[0])) < min_quote:
                gruende.append("quote_zu_tief")       # @1,01 ist kein Signal — s. MIN_QUOTE
            if summe < min_usd:
                gruende.append("summe_zu_klein")
            if gruende:
                # Zu alt ist KEIN Grund fuers Beinahe-Buch: das Cluster war fachlich in Ordnung,
                # wir haben es nur zu spaet gesehen. Es hier mitzuzaehlen wuerde die Frage
                # „welche Regel kostet uns kleine Ligen" mit Laufzeit-Rauschen zumuellen.
                if (beinahe is None and verworfen is not None
                        and (now - v[j][0]).total_seconds() / 60.0 <= max_alter_min):
                    beinahe = _beinahe(a, g, summe, gruende, v[i][0], v[j][0])
                continue
            if (now - v[j][0]).total_seconds() / 60.0 > max_alter_min:
                continue                  # zu alt zum Melden — s. MAX_ALTER_MIN
            aus.append({"auswahlId": a, "wetten": g, "summe": summe,
                        "sekunden": (v[j][0] - v[i][0]).total_seconds(),
                        "von": v[i][0], "bis": v[j][0]})
            beinahe = klein = None        # Treffer schlaegt Beinahe — nie beides je Auswahl
            break
        # Ein echter Beinahe-Treffer (genug Tickets, an einer Regel gescheitert) sagt mehr als
        # ein zu kleines Cluster — er bekommt den einen Platz je Auswahl.
        if verworfen is not None and (beinahe or klein) is not None:
            verworfen.append(beinahe if beinahe is not None else klein)
    if verworfen is not None:
        for a, v in je_gesperrt.items():
            v.sort(key=lambda z: z[0])
            for i in range(len(v)):
                j = i
                while j + 1 < len(v) and (v[j + 1][0] - v[i][0]).total_seconds() <= fenster_s:
                    j += 1
                if j - i + 1 < min_n:
                    continue
                g = [z[1] for z in v[i:j + 1]]
                if (now - v[j][0]).total_seconds() / 60.0 <= max_alter_min:
                    verworfen.append(_beinahe(a, g, sum(float(x["einsatzUsd"]) for x in g),
                                              ["sportart_gesperrt"], v[i][0], v[j][0]))
                break
    aus.sort(key=lambda b: b["von"])      # aelteste zuerst — der Deckel ist keine Rangfolge
    return aus


# ═══ Die zweite Gruppierung: je SPIEL statt je Auswahl ═══════════════════════════════════════
# 🔴 22.09.2026 (Lucas schickt einen Fremd-Radar-Post: „⚽️ #Uzbekistan #Pro_League, PFC Terdu –
# FK Gazalkent, Volume $15.734, Total 5 bets / 5 bets in 7 min" — „genau sowas ist halt das Geile,
# wenn man sowas findet, und wir HAETTEN es gefunden. Also macht das bitte so, dass man es findet").
#
# Wir hatten die Wetten. Sechs Fussballwetten auf genau dieses Spiel standen im Ledger, darunter
# die aus dem fremden Post ($2.000 x 1,75 auf FK Gazalkent -1,5). Gefunden hat sie niemand, weil
# `bursts()` je AUSWAHL gruppiert und dieselbe Quote verlangt — der Fremd-Radar gruppiert je SPIEL.
# Die groesste gleichgerichtete Gruppe war n=3 / $7.262 auf zwei Quoten (1,80 und 1,85). Kein
# Fehler in der bestehenden Regel: eine andere Frage, die niemand gestellt hat.
#
# ── Was den Fall interessant macht, und was nicht ────────────────────────────────────────────
# „Mehrere Wetten auf ein Spiel" allein ist kein Signal — gemessen am Ledger (16.553
# Einzelwetten, 5,80 Tage) waeren das 28 bis 55 Meldungen pro Tag, die Haelfte davon Premier
# League und Serie A. Drei Einschraenkungen, jede einzeln gemessen:
#
#   Zuschnitt (je Spiel, US-Sport/Kampfsport gesperrt)          Bursts   pro Tag
#   >=4 Wetten / 5 Min / ab $10k                                   162      27,9
#   dazu: KEINE GEGENSEITE (alle gerichteten Wetten ein Team)      144      24,8
#   dazu: alle Quoten >= 1,35                                       —         —
#   dazu: Summe >= 2x der Liga-Norm (Median x Anzahl)               —         —
#   alles zusammen, Fenster 30 Min                                  58      10,0
#
# · KEINE GEGENSEITE ist die tragende Regel. Sie unterscheidet „viel Geld auf dieses Spiel"
#   (zwei Parteien, die sich uneinig sind — das ist ein Markt, kein Signal) von „viel Geld auf
#   DIESE Mannschaft ueber mehrere Maerkte". Genau das war Lucas' Fall: drei Wetten auf
#   FK Gazalkent (1x2, 1. Halbzeit, Handicap), drei neutrale auf Over — und keine einzige auf
#   Terdu. Neutrale Wetten (Over/Under, Torzahl) zaehlen zur Summe, aber nicht als Gegenseite.
# · Das FENSTER ist 30 Minuten statt 5: die Auswahl-Regel misst einen Schwall auf EINE Auswahl,
#   hier verteilt sich dasselbe Geld ueber mehrere Maerkte und braucht laenger. Lucas' Fall
#   spannt 20 Minuten.
# · Der QUOTENBODEN (1,35) und der NORM-FAKTOR (2x) sind dieselben Zahlen, die im Haus ohnehin
#   gelten — keine zwei neuen, die man sich merken muss.
#
# ⚠️ Was dieser Zuschnitt NICHT kann: die grossen Ligen raushalten. Von den 58 sind 25 Ebene 1
# (Premier League, Serie A, Bundesliga), wo eine Burst-Summe nach Lucas' eigenem Massstab „0
# sagt". Der Norm-Faktor faengt das nicht, weil grosse Ligen auch eine grosse Norm haben, und
# die Spielklasse taugt hier nicht als Filter — Lucas' eigene Liga steht seit heute als
# „mehrdeutig" in `stake_liga_stufe` (der Slug `pro-league` traegt zwei Klassen). Deshalb steht
# die Spielklasse auf der KARTE und filtert nicht. Erst messen, dann behaupten.
#
# ⚠️ Und es gibt noch keine Rendite-Messung fuer diesen Zuschnitt. Der Auswahl-Burst hat eine
# (+45,9 %, UG +34,3 %, n=212); die gilt hier NICHT — es ist eine andere Einheit. Das Buch
# stempelt deshalb `art: "spiel"`, damit die zwei nie in einer Zahl zusammenfallen.
# ── Die Schwellen, und wie sie zustande kommen ──────────────────────────────────────────────
# Gemessen am Ledger (16.553 Einzelwetten, 5,80 Tage), je Zeile die Lautstaerke und ob Lucas'
# eigener Fall (PFC Terdu – FK Gazalkent, 5 Wetten, $15.734, 1,74x) noch durchkommt:
#
#     2,00x / ab $10k / >=4 Wetten / >=1 gerichtet     16,4 / Tag     Lucas faellt durch
#     1,50x / ab $10k / >=4 / >=1                      21,9           ✓
#     1,50x / ab $15k / >=4 / >=2                      16,2           ✓
#     1,50x / ab $12k / >=4 / >=2                      16,9           ✓  ← gewaehlt
#     1,50x / ab $12k / >=4 / >=3                      13,1           faellt durch
#     2,00x / ab $15k / >=4 / >=2                      12,4           faellt durch
#
# ⚠️ EHRLICH GESAGT: diese Schwellen sind NICHT belegt. Sie sind so gesetzt, dass der Fall, den
# Lucas gezeigt hat, mit etwas Puffer durchkommt („genau sowas ist halt das Geile, wenn man sowas
# findet … macht das bitte so, dass man es findet") und die Lautstaerke unter 20 am Tag bleibt.
# Das ist eine Auswahl nach EINEM Beispiel — genau die Klasse, vor der die Schwellen-Treppe des
# Auswahl-Bursts warnt. Deshalb: eigener Buch-Stempel (`art: "spiel"`), eigener Deckel, und in
# zwei Wochen dieselbe Schwellen-Treppe wie am 16.09. fuer die Auswahl-Bursts. Bis dahin ist das
# ein Beobachtungsband, kein Signal.
#
# MIN_GERICHTET ist die Regel, die am meisten traegt: mindestens zwei Wetten muessen eine
# MANNSCHAFT benennen. Vier neutrale Over/Under-Tickets sind ein Torlinien-Handel, keine
# Richtungswette — und ohne diese Zahl waere jeder Ueber/Unter-Schwall eine Meldung.
SPIEL_MIN_N = int(os.environ.get("STAKE_SPIEL_MIN_N") or 4)
SPIEL_MIN_GERICHTET = int(os.environ.get("STAKE_SPIEL_MIN_GERICHTET") or 2)
SPIEL_FENSTER_S = float(os.environ.get("STAKE_SPIEL_FENSTER_S") or 1800)
SPIEL_MIN_USD = float(os.environ.get("STAKE_SPIEL_MIN_USD") or 12000)
SPIEL_MIN_FAKTOR = float(os.environ.get("STAKE_SPIEL_MIN_FAKTOR") or 1.5)
SPIEL_MAX_PUSH = int(os.environ.get("STAKE_SPIEL_MAX") or 2)
SPIEL_AN = (os.environ.get("STAKE_SPIEL_PUSH") or "true").strip().lower() \
    not in ("false", "0", "nein", "off", "aus")
NORM_FILE = BASE / "stake_league_norm.json"


def _teams(event) -> list:
    """Die beiden Mannschaften aus dem Event-Namen. Leer, wenn das Format nicht passt —
    dann gibt es keine Seite und der Burst faellt durch, statt eine zu erfinden."""
    e = str(event or "")
    return [t.strip() for t in e.split(" - ", 1)] if " - " in e else []


def seite(w) -> str | None:
    """Auf welche MANNSCHAFT zeigt diese Auswahl? None heisst neutral (Over/Under, Torzahl) —
    nicht „unbekannt" und erst recht nicht „Gegenseite".

    Bewusst nur bei EINDEUTIGEM Treffer: bei „Deportivo La Coruna - Deportivo Alaves" passt
    „Deportivo" auf beide, und eine geratene Seite waere schlimmer als keine.
    """
    a = str((w or {}).get("auswahl") or "").lower()
    if not a:
        return None
    treffer = [t for t in _teams((w or {}).get("event")) if t and t.lower() in a]
    return treffer[0] if len(treffer) == 1 else None


def liga_norm(pfad=None) -> dict:
    """{Liganame: Median-Einsatz}. Fehlt die Datei oder die Liga, gibt es keinen Faktor —
    und ohne Faktor kein Push. Fehlende Information ist hier bewusst eine Sperre und kein
    harmloser Default: „wir kennen die Liga nicht" heisst nicht „der Einsatz ist normal"."""
    d = _load(pfad or NORM_FILE, {}) or {}
    aus = {}
    for name, v in (d.get("ligen") or {}).items():
        m = (v or {}).get("median")
        if isinstance(m, (int, float)) and m > 0:
            aus[str(name)] = float(m)
    return aus


def spiel_bursts(wetten, min_n=None, fenster_s=None, min_usd=None, min_faktor=None,
                 min_quote=None, max_alter_min=None, gesperrt=None, norm=None, now=None,
                 min_gerichtet=None) -> list:
    """Bursts je SPIEL, einseitig. REIN (alles injizierbar).

    Ein Spiel-Burst ist: `min_n` Einzelwetten auf DASSELBE Spiel innerhalb von `fenster_s`,
    zusammen mindestens `min_usd` UND mindestens `min_faktor` mal der Liga-Norm, alle Quoten
    ueber `min_quote`, und alle gerichteten Wetten auf DIESELBE Mannschaft.

    Je Spiel hoechstens einer (der erste) — dieselbe Regel wie bei den Auswahl-Bursts, aus
    demselben Grund: sonst sieht der Kanal ein Ereignis als fuenf.
    """
    min_n = SPIEL_MIN_N if min_n is None else min_n
    min_gerichtet = SPIEL_MIN_GERICHTET if min_gerichtet is None else min_gerichtet
    fenster_s = SPIEL_FENSTER_S if fenster_s is None else fenster_s
    min_usd = SPIEL_MIN_USD if min_usd is None else min_usd
    min_faktor = SPIEL_MIN_FAKTOR if min_faktor is None else min_faktor
    min_quote = MIN_QUOTE if min_quote is None else min_quote
    max_alter_min = MAX_ALTER_MIN if max_alter_min is None else max_alter_min
    gesperrt = list(GESPERRT_FALLBACK) if gesperrt is None else list(gesperrt)
    norm = liga_norm() if norm is None else norm
    now = now or datetime.now(timezone.utc)

    je_spiel = {}
    for w in wetten or []:
        if not isinstance(w, dict) or w.get("kombi"):
            continue
        if w.get("kat") in gesperrt:
            continue
        ev, t, u = w.get("eventId"), _ts(w.get("ts")), w.get("einsatzUsd")
        if not ev or t is None:
            continue
        if not isinstance(u, (int, float)) or isinstance(u, bool) or u <= 0:
            continue
        # 🔴 Der Quotenboden wirkt hier je ZEILE, nicht je Cluster — anders als beim
        # Auswahl-Burst, wo ohnehin alle Wetten dieselbe Quote tragen. Zuerst stand hier
        # `if min(quoten) < min_quote: verwirf das Cluster`, und genau daran fiel Lucas'
        # eigener Fall durch: fuenf Wetten zwischen 1,65 und 1,85 auf FK Gazalkent, plus eine
        # Abstauber-Wette @1,03 zwanzig Minuten spaeter. Eine einzelne 1,03 darf die fuenf
        # anderen nicht entwerten. Sie zaehlt weder zur Anzahl noch zur Summe — sie ist
        # einfach nicht Teil der Beobachtung.
        q = _quote(w)
        if q is None or q < min_quote:
            continue
        je_spiel.setdefault(ev, []).append((t, w))

    aus = []
    for ev, v in je_spiel.items():
        if len(v) < min_n:
            continue
        v.sort(key=lambda z: z[0])
        for i in range(len(v)):
            j = i
            while j + 1 < len(v) and (v[j + 1][0] - v[i][0]).total_seconds() <= fenster_s:
                j += 1
            if j - i + 1 < min_n:
                continue
            g = [z[1] for z in v[i:j + 1]]
            gerichtet = [x for x in g if seite(x)]
            seiten = {seite(x) for x in gerichtet}
            if len(seiten) != 1:          # keine gerichtete Wette, oder eine Gegenseite
                continue
            # Mindestens `min_gerichtet` Tickets muessen eine MANNSCHAFT benennen. Vier neutrale
            # Over/Under-Wetten plus eine auf die Heimelf sind ein Torlinien-Handel, keine
            # Richtungswette — und ohne diese Zahl waere jeder Ueber/Unter-Schwall eine Meldung.
            if len(gerichtet) < min_gerichtet:
                continue
            summe = sum(float(x["einsatzUsd"]) for x in g)
            if summe < min_usd:
                continue
            med = norm.get(str(g[0].get("liga") or ""))
            if not med:
                continue                  # keine Norm = kein Faktor = kein Urteil
            faktor = summe / (med * len(g))
            if faktor < min_faktor:
                continue
            if (now - v[j][0]).total_seconds() / 60.0 > max_alter_min:
                continue                  # zu alt zum Melden — dieselbe Grenze wie oben
            aus.append({"eventId": ev, "wetten": g, "summe": summe, "faktor": faktor,
                        "seite": list(seiten)[0], "nGerichtet": len(gerichtet),
                        "sekunden": (v[j][0] - v[i][0]).total_seconds(),
                        "von": v[i][0], "bis": v[j][0]})
            break
    aus.sort(key=lambda b: b["von"])      # aelteste zuerst — der Deckel ist keine Rangfolge
    return aus


def spiel_key(b) -> str:
    """Dedup ueber das SPIEL. Ein zweiter Schwall auf dasselbe Spiel ist dieselbe Beobachtung."""
    return "spiel:%s" % b.get("eventId")


def build_spiel_card(b, unterdrueckt=0) -> str:
    """Die Karte des Spiel-Bursts. Sie sagt in ihrer Kopfzeile, dass sie eine ANDERE Einheit
    misst als der Auswahl-Burst — sonst liest man die Rendite der einen auf der anderen."""
    g = b["wetten"]
    erste = g[0]
    e = lambda x: html.escape(str(x or ""), quote=False)
    maerkte = []
    for x in g:
        m = str(x.get("markt") or "")
        if m and m not in maerkte:
            maerkte.append(m)
    phase = ("live" if all(x.get("phase") == "live" for x in g)
             else "vor Anpfiff" if all(x.get("phase") == "vor" for x in g) else "gemischt")
    try:
        import stake_liga_stufe as _LS
        klasse = _LS.stufe(erste.get("ligaSlug"), erste.get("sport"))
    except Exception:
        klasse = None
    KLARTEXT = {"1": "oberste Spielklasse", "2": "zweite Spielklasse",
                "3": "dritte Klasse und tiefer", "kontinental": "kontinental",
                "pokal": "Pokal", "frauen": "Frauen", "jugend": "Jugend",
                "reserve": "Reserve", "srl": "Simulated Reality",
                "mehrdeutig": "Spielklasse nicht eindeutig", "freundschaft": "Freundschaftsspiel"}

    lines = ["▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
             "🎯 <b>STAKE-SPIEL</b> · <b>%d Wetten</b> auf <b>eine Seite</b> in <b>%s</b>"
             % (len(g), _sek_text(int(round(b["sekunden"])))),
             "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓", ""]
    lines.append("%s <i>%s</i>" % (_emoji(erste.get("kat")), e(erste.get("kat") or "Sport")))
    lines.append("<b>%s</b>" % e(erste.get("event")))
    lines.append("<i>%s%s</i>" % (e(erste.get("liga")),
                                 (" · " + KLARTEXT.get(klasse, klasse)) if klasse else ""))
    lines.append("")
    lines.append("➡️ alles auf <b>%s</b>" % e(b.get("seite")))
    lines.append("💰 <b>%s</b> über %d %s · <b>%.1fx</b> der Liga-Norm"
                 % (_usd(b["summe"]), len(maerkte), "Märkte" if len(maerkte) != 1 else "Markt",
                    b["faktor"]))
    lines.append("")
    for x in sorted(g, key=lambda y: -float(y.get("einsatzUsd") or 0))[:6]:
        t = _ts(x.get("ts"))
        lines.append("   %s  @%.2f  <i>%s</i>  <code>%s</code>"
                     % (_usd(x.get("einsatzUsd")), _quote(x), e(x.get("auswahl")),
                        t.strftime("%H:%M:%S") if t else "?"))
    lines.append("")
    lines.append("⏱️ <b>%s</b>" % phase)
    if unterdrueckt:
        lines.append("<i>+%d weitere Spiel-Bursts in diesem Lauf nicht gesendet (Deckel %d)</i>"
                     % (unterdrueckt, SPIEL_MAX_PUSH))
    lines.append("\n<i>🔬 NEU seit 22.09.2026 und noch OHNE eigene Rendite-Messung. Das ist eine "
                 "andere Einheit als der ⚡ Stake-Burst — dessen +45,9 %% gelten hier NICHT. "
                 "Zuschnitt: >=%d Wetten je Spiel (davon >=%d mit Mannschaft), %d Min, ab %s, "
                 "mindestens %.1fx der Liga-Norm, Quoten ab %.2f, keine Gegenseite. Gemessen am "
                 "Ledger sind das rund 17 Meldungen pro Tag; die Schwellen sind nach EINEM "
                 "Beispiel gesetzt und noch nicht belegt.</i>"
                 % (SPIEL_MIN_N, SPIEL_MIN_GERICHTET, int(SPIEL_FENSTER_S // 60),
                    _usd(SPIEL_MIN_USD), SPIEL_MIN_FAKTOR, MIN_QUOTE))
    return "\n".join(lines)


def spiel_buch_zeile(b, ts) -> dict:
    """Eigene Buchzeile mit `art: "spiel"`. Die zwei Arten duerfen NIE in einer Zahl
    zusammenfallen — sie messen verschiedene Einheiten, und genau daran ist am 07.09. die
    Spielklassen-Ansicht fast gescheitert."""
    g = b["wetten"]
    erste = g[0]
    return {
        "k": spiel_key(b), "art": "spiel",
        "eventId": b["eventId"], "event": erste.get("event"),
        "liga": erste.get("liga"), "ligaSlug": erste.get("ligaSlug"), "kat": erste.get("kat"),
        "seite": b.get("seite"), "nGerichtet": b.get("nGerichtet"),
        "maerkte": sorted({str(x.get("markt") or "") for x in g if x.get("markt")}),
        "summeUsd": round(float(b["summe"]), 2),
        "faktor": round(float(b["faktor"]), 2),
        "nWetten": len(g), "sekunden": round(float(b["sekunden"]), 1),
        "phase": ("live" if all(x.get("phase") == "live" for x in g)
                  else "vor" if all(x.get("phase") == "vor" for x in g) else "gemischt"),
        "betIds": [x.get("id") for x in g],
        "sentAt": ts, "status": "pending",
    }


def _beinahe(auswahl_id, g, summe, gruende, von, bis) -> dict:
    """Eine Zeile fuers Beinahe-Buch: ein Cluster, das die Regeln NICHT passiert hat.

    🔴 13.09.2026 (Lucas: „es muss auch solche Bursts auf generelle Ligen geben — ich seh da
    immer Screens aus dieser einen Gruppe, irgendwelche Panama-Ligen"). Die Frage liess sich
    nicht beantworten: der Kanal wusste nur, was er GESENDET hat. Ich habe sie an diesem Tag
    von Hand aus dem Ledger rekonstruiert (Ergebnis: es liegt nicht an den Schwellen, sondern
    daran, dass Stakes Feed erst ab ~1.000 $ je Wette ueberhaupt etwas zeigt) — und genau das
    darf beim naechsten Mal nicht wieder eine Stunde Handarbeit sein.

    Dieselbe Regel wie ueberall hier: was wir wegfiltern, muss messbar bleiben. Ein Filter, dessen
    Preis niemand kennt, laesst sich weder rechtfertigen noch widerlegen.
    """
    erste = g[0]
    return {"auswahlId": auswahl_id, "gruende": sorted(gruende),
            "liga": erste.get("liga"), "ligaSlug": erste.get("ligaSlug"),
            "kat": erste.get("kat"), "sport": erste.get("sport"),
            "event": erste.get("event"), "markt": erste.get("markt"),
            "auswahl": erste.get("auswahl"),
            "quote": _quote(erste), "quoten": sorted({round(float(_quote(x)), 2) for x in g}),
            "nWetten": len(g), "summeUsd": round(float(summe), 2),
            "sekunden": round((bis - von).total_seconds(), 1),
            "gesehenAm": von.isoformat()}


def burst_key(b) -> str:
    """Dedup-Schluessel. Die Auswahl allein reicht: ein zweiter Burst auf dieselbe Auswahl ist
    dieselbe Beobachtung, nicht eine neue."""
    return str(b.get("auswahlId"))


def prune_seen(seen, now=None, keep_h=SEEN_KEEP_H) -> dict:
    """Dedup-Stand aufraeumen. REIN. Ohne das waechst die Datei ewig, und eine Auswahl, die in
    zwei Wochen wieder auftaucht, bliebe fuer immer gesperrt."""
    now = now or datetime.now(timezone.utc)
    aus = {}
    for k, v in (seen if isinstance(seen, dict) else {}).items():
        t = _ts((v or {}).get("ts") if isinstance(v, dict) else None)
        if t is not None and (now - t).total_seconds() / 3600.0 <= keep_h:
            aus[k] = v
    return aus


def build_burst_card(b, unterdrueckt=0) -> str:
    """Die Telegram-Karte. Bewusst anders gebaut als die Poly-Dominanz-Karte: dort fuehrt der
    ANTEIL, hier die GESCHWINDIGKEIT — das ist die Eigenschaft, um die es geht."""
    g = b["wetten"]
    erste = g[0]
    q = _quote(erste)
    sek = int(round(b["sekunden"]))
    phase = ("live" if all(x.get("phase") == "live" for x in g)
             else "vor Anpfiff" if all(x.get("phase") == "vor" for x in g) else "gemischt")
    e = lambda x: html.escape(str(x or ""), quote=False)

    lines = ["▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
             "⚡ <b>STAKE-BURST</b> · <b>%d Wetten</b> in <b>%s</b>" % (len(g), _sek_text(sek)),
             "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓", ""]
    lines.append("%s <i>%s</i>" % (_emoji(erste.get("kat")), e(erste.get("kat") or "Sport")))
    lines.append("<b>%s</b>" % e(erste.get("event")))
    lines.append("<i>%s</i>" % e(erste.get("liga")))
    lines.append("")
    lines.append("🎯 %s — <b>%s</b>" % (e(erste.get("markt")), e(erste.get("auswahl"))))
    lines.append("💰 <b>%s</b> auf einer Auswahl · alle @<b>%.2f</b>" % (_usd(b["summe"]), q))
    lines.append("")
    for x in sorted(g, key=lambda y: -float(y.get("einsatzUsd") or 0))[:6]:
        t = _ts(x.get("ts"))
        lines.append("   %s  @%.2f  <code>%s</code>" % (_usd(x.get("einsatzUsd")), _quote(x),
                                                        t.strftime("%H:%M:%S") if t else "?"))
    lines.append("")
    lines.append("⏱️ <b>%s</b>" % phase)
    if unterdrueckt:
        lines.append("<i>+%d weitere Bursts in diesem Lauf nicht gesendet (Deckel %d)</i>"
                     % (unterdrueckt, MAX_PUSH))
    # Das Urteil gehoert dorthin, wo die Zahl gelesen wird — nicht in eine Fussnote im Backlog.
    lines.append("\n<i>🔬 Beobachtungsband — läuft mit, ist noch kein Beleg. Gemessen an 15.646 "
                 "abgerechneten Wetten, mit Quotenboden %.2f: <b>+45,9 %% ROI</b> "
                 "(Untergrenze +34,3 %%, n=212). Die gleiche Quote ist die Regel, nicht der "
                 "Betrag — ab $50.000 dreht es ins Minus.</i>" % MIN_QUOTE)
    return "\n".join(lines)


def _sek_text(s) -> str:
    s = int(s)
    if s < 60:
        return "%d Sek" % max(s, 1)
    return "%d:%02d Min" % (s // 60, s % 60)


_EMOJI = {"Fußball": "⚽", "Tennis": "🎾", "E-Sport": "🎮", "US-Sport": "🏈", "Cricket": "🏏",
          "Basketball": "🏀", "Tischtennis": "🏓", "Volleyball": "🏐", "Handball": "🤾",
          "Eishockey": "🏒", "Darts": "🎯", "Snooker": "🎱", "Kampfsport": "🥊"}


def _emoji(kat) -> str:
    return _EMOJI.get(str(kat or ""), "🏆")


def buch_zeile(b, ts) -> dict:
    """Eine gesendete Beobachtung als Buchzeile. Abgerechnet wird sie spaeter aus dem Ledger —
    `stake_settle.py` traegt die Ergebnisse auf den Wetten nach, die hier namentlich stehen."""
    g = b["wetten"]
    erste = g[0]
    return {
        "k": burst_key(b),
        "auswahlId": b["auswahlId"], "eventId": erste.get("eventId"),
        "event": erste.get("event"), "liga": erste.get("liga"), "kat": erste.get("kat"),
        "markt": erste.get("markt"), "auswahl": erste.get("auswahl"),
        "quote": _quote(erste),
        "summeUsd": round(float(b["summe"]), 2),
        "nWetten": len(g), "sekunden": round(float(b["sekunden"]), 1),
        # Phase getrennt stempeln: live und vor Anpfiff sind zwei verschiedene Messungen
        # (+29 % gegen +8,8 %), zusammengerechnet waere keine von beiden zu beantworten.
        "phase": ("live" if all(x.get("phase") == "live" for x in g)
                  else "vor" if all(x.get("phase") == "vor" for x in g) else "gemischt"),
        "betIds": [x.get("id") for x in g],
        "sentAt": ts, "status": "pending",
    }


# ── Abrechnung (13.09.2026, Lucas: „die Stake-Bursts haette ich auch gerne in den Stats") ──
#
# 🔴 Beim Bauen des Stats-Blocks stellte sich heraus: ALLE 15 Buchzeilen standen auf `pending`.
# Der Kopf von `buch_zeile` sagte „abgerechnet wird sie spaeter aus dem Ledger" — nur tat das
# niemand. Der Kanal pushte seit dem 11.09. und mass sich nie. Das ist die Fehlerklasse „wer
# pusht, misst den Push", diesmal in ihrer stillsten Form: nichts ist falsch, es steht nur
# nichts da.
#
# ⚠️ Und es war dringender, als es aussah. `stake_bet_ledger.json` ist ein ROLLIERENDES Fenster
# von 20.000 Wetten — gemessen am 13.09. sind das **5,3 Tage**. Eine Burst-Zeile, die in diesem
# Fenster nicht abgerechnet wird, ist danach nicht mehr abrechenbar: ihre Wetten sind aus der
# Quelle gefallen. Deshalb laeuft die Abrechnung bei JEDEM Lauf mit (alle 15 Minuten), und
# deshalb bekommt eine Zeile, deren Wetten verschwunden sind, den Status `nicht_abrechenbar`
# statt ewig `pending` — sonst waechst ein Haufen Zeilen, die aussehen, als kaeme da noch was.
STATUS_OFFEN = "pending"
STATUS_FERTIG = "abgerechnet"
STATUS_TOT = "nicht_abrechenbar"


def _rendite(zeile: dict, wetten_idx: dict):
    """(rendite, grund) fuer eine Burst-Zeile. Rendite je Einsatz-Dollar, `None` = noch nicht.

    ⭐ Nur wenn ALLE Wetten des Bursts einen Endstand tragen. Teilweise abzurechnen waere
    verzerrt: die frueh fertigen Beine sind nicht dieselbe Menge wie der ganze Burst, und die
    Zeile wuerde beim naechsten Lauf eine andere Zahl zeigen als beim letzten.

    ⭐ Gewichtet nach GELD (Summe pnl / Summe Einsatz), nicht je Wette gemittelt: ein Burst ist
    EINE Position, die auf mehrere Tickets verteilt wurde. Genau das ist ja das Muster, das ihn
    zum Burst macht.
    """
    ids = zeile.get("betIds") or []
    if not ids:
        return None, "keine Wett-IDs in der Zeile"
    da = [wetten_idx.get(i) for i in ids]
    if any(x is None for x in da):
        return None, "mindestens eine Wette ist aus dem rollierenden Stake-Ledger gefallen"
    abr = [(x.get("abrechnung") or {}) for x in da]
    if not all(y.get("endstand") for y in abr):
        return None, "laeuft noch"
    einsatz = sum(float(y.get("einsatzUsdGeprueft") or 0) for y in abr)
    if einsatz <= 0:
        return None, "kein geprueefter Einsatz"
    pnl = sum(float(y.get("pnlUsd") or 0) for y in abr)
    return pnl / einsatz, None


def abrechnen(zeilen: list, wetten: list, now=None) -> tuple[list, int, int]:
    """Offene Buchzeilen abrechnen. Gibt (Zeilen, neu abgerechnet, aufgegeben) zurueck. REIN."""
    now = now or datetime.now(timezone.utc)
    idx = {w.get("id"): w for w in (wetten or []) if isinstance(w, dict) and w.get("id")}
    # Ab wann ist eine Zeile verloren? Sobald ihre Wetten fehlen UND die Quelle nicht mehr so
    # weit zurueckreicht. Die zweite Bedingung ist wichtig: ein leeres oder halb geladenes
    # Stake-Ledger darf nicht reihenweise Zeilen fuer tot erklaeren.
    quelle_ab = min((str(w.get("ts") or "") for w in (wetten or []) if w.get("ts")), default=None)
    fertig = tot = 0
    for z in zeilen:
        if not isinstance(z, dict) or z.get("status") != STATUS_OFFEN:
            continue
        r, grund = _rendite(z, idx)
        if r is not None:
            z["status"] = STATUS_FERTIG
            z["rendite"] = round(r, 4)
            z["win"] = r > 0
            z["settledAt"] = now.isoformat()
            fertig += 1
        elif quelle_ab and str(z.get("sentAt") or "") < quelle_ab:
            z["status"] = STATUS_TOT
            z["grund"] = grund
            z["settledAt"] = now.isoformat()
            tot += 1
    return zeilen, fertig, tot


def verworfen_mischen(alt: dict, neu: list, now) -> dict:
    """Beinahe-Buch fortschreiben. Ein Cluster zaehlt EINMAL (Schluessel = Auswahl). REIN.

    Ohne den Dedup zaehlte dasselbe Cluster bei jedem Lauf neu mit, solange es im Fenster liegt
    — nach einer Stunde stuende „sechsmal an der Quote gescheitert" da, wo es einmal war. Genau
    diese Sorte Zaehlfehler macht eine Statistik unbrauchbar, ohne dass etwas kaputt aussieht.
    """
    zeilen = list((alt or {}).get("zeilen") or [])
    bekannt = {str(z.get("auswahlId")) for z in zeilen if isinstance(z, dict)}
    for z in neu or []:
        if str(z.get("auswahlId")) not in bekannt:
            zeilen.append(z)
            bekannt.add(str(z.get("auswahlId")))
    zeilen = zeilen[-VERWORFEN_KEEP:]
    zaehler, je_liga, allein = {}, {}, {}
    for z in zeilen:
        g = z.get("gruende") or []
        for x in g:
            zaehler[x] = zaehler.get(x, 0) + 1
        # ⭐ Die eigentliche Frage: an welcher EINEN Regel scheitert ein sonst gueltiges Cluster?
        # Eine Zeile mit drei Gruenden sagt nichts darueber, welche Regel man lockern muesste.
        if len(g) == 1:
            allein[g[0]] = allein.get(g[0], 0) + 1
        L = z.get("liga") or "?"
        je_liga[L] = je_liga.get(L, 0) + 1
    tage = sorted(str(z.get("gesehenAm") or "")[:10] for z in zeilen if z.get("gesehenAm"))
    return {"generatedAt": now.isoformat(), "n": len(zeilen),
            "von": tage[0] if tage else None, "bis": tage[-1] if tage else None,
            "zaehler": zaehler, "nurDieserGrund": allein,
            "jeLiga": dict(sorted(je_liga.items(), key=lambda kv: -kv[1])[:40]),
            "zeilen": zeilen}


def _verworfen_buchen(beinahe: list, now) -> None:
    buch = verworfen_mischen(_load(VERWORFEN_FILE, {}), beinahe, now)
    try:
        _save(VERWORFEN_FILE, buch)
    except Exception as e:
        print("Beinahe-Buch-Schreibfehler:", e)
        return
    a = buch.get("nurDieserGrund") or {}
    print("   🔍 Beinahe-Buch: +%d neu · %d gesamt seit %s · scheitert an GENAU EINER Regel: %s"
          % (len(beinahe), buch["n"], buch.get("von") or "—",
             ", ".join("%s %d" % (k, v) for k, v in sorted(a.items(), key=lambda kv: -kv[1]))
             or "—"))


def zu_senden(neu, push_an=None, max_push=None) -> list:
    """Welche der neuen Bursts gehen raus? REIN — damit „Push aus" pruefbar ist.

    Stand vorher als Ausdruck mitten in `main` und war damit nur am Quelltext zu pruefen. Eine
    Mutation, die den Schalter ignoriert, waere gruen durchgelaufen — genau deshalb hier.
    """
    push_an = PUSH_AN if push_an is None else push_an
    max_push = MAX_PUSH if max_push is None else max_push
    return list(neu or [])[:max_push] if push_an else []


def main() -> int:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    quelle = _load(QUELLE_FILE, {})
    wetten = (quelle or {}).get("wetten") or []
    if not wetten:
        print("Stake-Burst: keine Wetten in stake_highroller.json — nichts zu tun.")
        return 0

    seen = prune_seen(_load(SEEN_FILE, {}), now)
    _gesperrt = gesperrte_kats(quelle)
    beinahe = []
    alle = bursts(wetten, gesperrt=_gesperrt, now=now, verworfen=beinahe)
    neu = [b for b in alle if burst_key(b) not in seen]
    print("⚡ Stake-Burst: %d frische(r) Burst(s), %d davon neu (>=%d Wetten, %ds, ab %s, "
          "Quote ab %.2f, max %.0f Min alt, gleiche Quote; ausgeblendet: %s)"
          % (len(alle), len(neu), MIN_N, int(FENSTER_S), _usd(MIN_USD), MIN_QUOTE,
             MAX_ALTER_MIN, ", ".join(_gesperrt) or "—"))

    senden = zu_senden(neu)
    unterdrueckt = max(len(neu) - len(senden), 0)
    led = _load(LEDGER_FILE, [])
    if not isinstance(led, list):
        led = []
    schon = {e.get("k") for e in led if isinstance(e, dict)}
    gesendet = 0
    for i, b in enumerate(senden):
        text = build_burst_card(b, unterdrueckt if i == len(senden) - 1 else 0)
        if not send_trades_message(text):
            continue
        gesendet += 1
        seen[burst_key(b)] = {"ts": now_iso, "summe": round(float(b["summe"]), 2)}
    # ⭐ JEDER erkannte Burst kommt ins Buch — auch der, der am Deckel haengengeblieben ist, und
    # auch jeder, wenn der Push ganz aus ist. Vorher stand hier `led.append` INNERHALB der
    # Sende-Schleife: alles ueber dem Deckel wurde gezaehlt, aber nie gemessen, und ein
    # stillgelegter Kanal haette gar nichts mehr gesammelt.
    neu_gebucht = 0
    for b in neu:
        k = burst_key(b)
        if k in schon:
            continue
        z = buch_zeile(b, now_iso)
        z["push"] = k in seen          # nur ein erfolgreicher Send steht in `seen`
        if not z["push"]:
            z["pushGrund"] = ("Push abgeschaltet (STAKE_BURST_PUSH)" if not PUSH_AN
                              else "Deckel des Laufs erreicht" if k not in {burst_key(x) for x in senden}
                              else "Senden fehlgeschlagen")
        led.append(z)
        schon.add(k)
        neu_gebucht += 1

    # ── Die zweite Gruppierung: je SPIEL (22.09.2026, Lucas) ────────────────────────────────
    # Eigener Deckel, eigener Dedup-Schluessel, eigene Buchart. Was hier gesendet wird, ist eine
    # ANDERE Beobachtung als oben — die beiden teilen nur die Sperrliste und den Kanal.
    sp_alle = spiel_bursts(wetten, gesperrt=_gesperrt, now=now)
    sp_neu = [b for b in sp_alle if spiel_key(b) not in seen]
    sp_senden = sp_neu[:SPIEL_MAX_PUSH] if (SPIEL_AN and PUSH_AN) else []
    sp_unterdrueckt = max(len(sp_neu) - len(sp_senden), 0)
    print("🎯 Stake-Spiel: %d frische(r) Spiel-Burst(s), %d davon neu (>=%d Wetten je Spiel, "
          "davon >=%d mit Mannschaft, %d Min, ab %s, >=%.1fx Liga-Norm, Quote ab %.2f, "
          "keine Gegenseite)"
          % (len(sp_alle), len(sp_neu), SPIEL_MIN_N, SPIEL_MIN_GERICHTET,
             int(SPIEL_FENSTER_S // 60), _usd(SPIEL_MIN_USD), SPIEL_MIN_FAKTOR, MIN_QUOTE))
    sp_gesendet = 0
    for i, b in enumerate(sp_senden):
        text = build_spiel_card(b, sp_unterdrueckt if i == len(sp_senden) - 1 else 0)
        if not send_trades_message(text):
            continue
        sp_gesendet += 1
        seen[spiel_key(b)] = {"ts": now_iso, "summe": round(float(b["summe"]), 2)}
    # Auch hier: JEDER erkannte kommt ins Buch, auch der ungesendete. Sonst kennt das Protokoll
    # nur die Ueberlebenden — die Fehlerklasse, die hier am 13.09. schon einmal repariert wurde.
    for b in sp_neu:
        k = spiel_key(b)
        if k in schon:
            continue
        z = spiel_buch_zeile(b, now_iso)
        z["push"] = k in seen
        if not z["push"]:
            z["pushGrund"] = ("Push abgeschaltet" if not (PUSH_AN and SPIEL_AN)
                              else "Deckel des Laufs erreicht" if k not in {spiel_key(x) for x in sp_senden}
                              else "Senden fehlgeschlagen")
        led.append(z)
        schon.add(k)
        neu_gebucht += 1

    _save(SEEN_FILE, seen)
    _verworfen_buchen(beinahe, now)
    # Bei JEDEM Lauf abrechnen — das Fenster der Quelle ist nur ~5 Tage breit (s. oben).
    led, _fertig, _tot = abrechnen(led, _load(WETTEN_FILE, {}).get("wetten") or [], now)
    _offen = sum(1 for e in led if isinstance(e, dict) and e.get("status") == STATUS_OFFEN)
    print("   📒 Buch: +%d abgerechnet · %d offen%s"
          % (_fertig, _offen, (" · %d aufgegeben (Wetten aus dem Ledger gefallen)" % _tot) if _tot else ""))
    try:
        _save(LEDGER_FILE, led[-LEDGER_KEEP:])
    except Exception as e:
        print("Stake-Burst-Ledger-Schreibfehler:", e)
    print("   %d Auswahl-Burst(s) + %d Spiel-Burst(s) gesendet, %d/%d unterdrueckt "
          "(Deckel %d/%d)%s · %d neu im Buch."
          % (gesendet, sp_gesendet, unterdrueckt, sp_unterdrueckt, MAX_PUSH, SPIEL_MAX_PUSH,
             "" if PUSH_AN else " — PUSH IST AUS, es wird nur gemessen", neu_gebucht))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
