"""tests/test_stake_highroller.py — 03.09.2026

Lucas: „ich würde gerne nur im Dashboard einen Bereich mit den Spielen sehen, mit Schwellen
die wir definieren, dann rein und wir sammeln das."

Der Sammler darf drei Dinge nicht tun, und darum drehen sich diese Tests:

  1. Einen unbekannten Einsatz als 0 durchreichen. Eine Wette in einer Währung ohne
     USD-Kurs ist NICHT klein — sie ist unbekannt, und das muss sie bleiben.
  2. Einen Fehler als leere Liste ausgeben. „Cloudflare hat 403 gesagt" darf im Dashboard
     nie aussehen wie „heute keine großen Wetten".
  3. Geld doppelt zählen. Ohne Wett-ID kann nicht dedupliziert werden, also fliegt der
     Eintrag raus statt mitgezählt zu werden.

Der Netzteil (GraphQL) wird hier nicht angefasst — getestet wird, was ohne Netz entscheidbar ist.
"""
import importlib.util
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _modul(monkeypatch=None, **env):
    """Frisch laden, damit Env-Schwellen greifen."""
    import os
    alt = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    try:
        spec = importlib.util.spec_from_file_location(
            "stake_highroller_fetch_t", ROOT / "stake_highroller_fetch.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


M = _modul()


# ── Schema-Findung: raten ist verboten ───────────────────────────────────────
def test_typ_name_wickelt_non_null_und_list_ab():
    t = {"kind": "NON_NULL", "name": None,
         "ofType": {"kind": "LIST", "name": None,
                    "ofType": {"kind": "OBJECT", "name": "SportBet"}}}
    assert M._typ_name(t) == "SportBet"


def test_typ_name_bei_muell_leer_statt_absturz():
    assert M._typ_name(None) == ""
    assert M._typ_name({}) == ""


def test_waehle_feld_nimmt_sport_vor_casino():
    felder = [{"name": "highrollerCasinoBets"}, {"name": "highrollerSportBets"},
              {"name": "user"}]
    assert M._waehle_feld(felder)["name"] == "highrollerSportBets"


def test_waehle_feld_ohne_treffer_ist_none():
    assert M._waehle_feld([{"name": "user"}, {"name": "sports"}]) is None


def test_waehle_feld_nimmt_kuerzesten_wenn_kein_sport():
    felder = [{"name": "highrollerBetsExtendedList"}, {"name": "highrollerBets"}]
    assert M._waehle_feld(felder)["name"] == "highrollerBets"


# ── USD: unbekannt bleibt unbekannt ──────────────────────────────────────────
def test_stablecoin_zaehlt_eins_zu_eins():
    usd, grund = M._usd(9000.0, "usdt", {})
    assert usd == 9000.0 and grund == "stablecoin"


def test_btc_ohne_kurs_ist_none_nicht_null():
    usd, grund = M._usd(0.12, "btc", {})
    assert usd is None
    assert grund.startswith("kurs_fehlt")


def test_mitgelieferter_usd_wert_schlaegt_waehrung():
    usd, grund = M._usd(0.12, "btc", {"amountUsd": 7400.0})
    assert usd == 7400.0 and grund == "feld"


def test_kein_betrag_ist_none():
    usd, grund = M._usd(None, "usdt", {})
    assert usd is None and grund == "kein_betrag"


# ── Normalisierung über Feldnamen ────────────────────────────────────────────
ROH = {
    "id": "648139990",
    "createdAt": "2026-09-03T18:12:00.000Z",
    "amount": 9000.0,
    "currency": "usdt",
    "user": {"name": "JoseSldnkp"},
    "bet": {
        "odds": 1.53,
        "outcomes": [{
            "outcome": {"name": "VfB Stuttgart"},
            "market": {"name": "1x2"},
            "fixture": {
                "name": "VfB Stuttgart - Bayern",
                "startingAt": "2026-09-03T18:30:00.000Z",
                "tournament": {"name": "Bundesliga", "category": {"sport": {"name": "soccer"}}},
            },
        }],
    },
}


def test_normalisiere_findet_die_felder_in_der_tiefe():
    n = M.normalisiere(ROH)
    assert n["id"] == "648139990"
    assert n["einsatzUsd"] == 9000.0
    assert n["quote"] == 1.53
    assert n["user"] == "JoseSldnkp"
    assert n["ts"].startswith("2026-09-03T18:12")


def test_normalisiere_ueberlebt_fehlende_felder():
    n = M.normalisiere({"id": "x"})
    assert n["id"] == "x"
    assert n["einsatzUsd"] is None
    assert n["quote"] is None


def test_normalisiere_setzt_keinen_default_auf_null():
    n = M.normalisiere({"id": "x", "amount": 5.0, "currency": "btc"})
    assert n["betrag"] == 5.0
    assert n["einsatzUsd"] is None, "unbekannter USD-Wert darf nicht 0 werden"


# ── Ledger ───────────────────────────────────────────────────────────────────
def test_ledger_dedupliziert_ueber_id():
    a = M.ledger_mischen({}, [{"id": "1", "ts": "2026-09-03T10:00:00Z"}], "jetzt")
    b = M.ledger_mischen(a, [{"id": "1", "ts": "2026-09-03T10:00:00Z"},
                             {"id": "2", "ts": "2026-09-03T11:00:00Z"}], "jetzt")
    assert b["n"] == 2
    assert b["zugangLetzterLauf"] == 1


def test_ledger_verwirft_eintraege_ohne_id():
    a = M.ledger_mischen({}, [{"ts": "2026-09-03T10:00:00Z", "einsatzUsd": 5000}], "jetzt")
    assert a["n"] == 0
    assert a["ohneIdVerworfen"] == 1


def test_ledger_haelt_seit_datum_fest():
    a = M.ledger_mischen({}, [{"id": "1", "ts": "t"}], "ERSTER")
    b = M.ledger_mischen(a, [{"id": "2", "ts": "t"}], "SPAETER")
    assert b["seit"] == "ERSTER"
    assert b["aktualisiert"] == "SPAETER"


def test_ledger_sortiert_neueste_zuerst():
    a = M.ledger_mischen({}, [
        {"id": "1", "ts": "2026-09-01T10:00:00Z"},
        {"id": "2", "ts": "2026-09-03T10:00:00Z"},
        {"id": "3", "ts": "2026-09-02T10:00:00Z"}], "jetzt")
    assert [w["id"] for w in a["wetten"]] == ["2", "3", "1"]


def test_ledger_deckelt_bei_keep():
    m = _modul(STAKE_LEDGER_KEEP=3)
    a = m.ledger_mischen({}, [{"id": str(i), "ts": "2026-09-%02dT10:00:00Z" % (i + 1)}
                              for i in range(9)], "jetzt")
    assert a["n"] == 3
    assert a["wetten"][0]["id"] == "8", "gedeckelt wird am ALTEN Ende, nicht am neuen"


# ── Fenster ──────────────────────────────────────────────────────────────────
def test_im_fenster_ohne_zeitstempel_ist_draussen():
    ab = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert M._im_fenster({}, ab) is False
    assert M._im_fenster({"ts": "kaputt"}, ab) is False


def test_im_fenster_nimmt_naive_zeit_als_utc():
    ab = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert M._im_fenster({"ts": "2026-09-04T00:00:00"}, ab) is True


# ── Sicht: ein Fehler ist kein leerer Tag ────────────────────────────────────
def _ledger_mit(n_bekannt, n_unbekannt, jetzt):
    w = []
    for i in range(n_bekannt):
        w.append({"id": "b%d" % i, "ts": jetzt.isoformat().replace("+00:00", "Z"),
                  "einsatzUsd": 5000.0})
    for i in range(n_unbekannt):
        w.append({"id": "u%d" % i, "ts": jetzt.isoformat().replace("+00:00", "Z"),
                  "einsatzUsd": None})
    return {"seit": "2026-09-01T00:00:00Z", "n": len(w), "wetten": w}


def test_sicht_zaehlt_unbekannte_einsaetze_getrennt():
    jetzt = datetime.now(timezone.utc)
    s = M.sicht_bauen(_ledger_mit(3, 2, jetzt), jetzt, "ok", "u", "f", "")
    assert s["nFenster"] == 5
    assert s["nUeberSchwelle"] == 3
    assert s["nEinsatzUnbekannt"] == 2, "unbekannt darf nicht unter 'über Schwelle' rutschen"


def test_sicht_traegt_die_schwelle_mit():
    """Die Schwelle muss wirklich filtern — und im JSON stehen, damit die Zahl ihre Basis nennt."""
    jetzt = datetime.now(timezone.utc)
    led = _ledger_mit(1, 0, jetzt)          # eine Wette ueber $5.000

    tief = _modul(STAKE_MIN_USD=2500).sicht_bauen(led, jetzt, "ok", "u", "f", "")
    assert tief["schwelleUsd"] == 2500.0
    assert tief["nUeberSchwelle"] == 1

    hoch = _modul(STAKE_MIN_USD=10000).sicht_bauen(led, jetzt, "ok", "u", "f", "")
    assert hoch["schwelleUsd"] == 10000.0
    assert hoch["nUeberSchwelle"] == 0
    assert hoch["nFenster"] == 1, "gefiltert wird die Schwellen-Zahl, nicht das Fenster"


def test_sicht_ist_nie_belegt():
    jetzt = datetime.now(timezone.utc)
    s = M.sicht_bauen(_ledger_mit(50, 0, jetzt), jetzt, "ok", "u", "f", "")
    assert s["belegt"] is False, ("Solange kein CLV und keine Trefferquote gemessen sind, "
                                 "darf diese Fläche sich nicht als belegt ausgeben.")


def test_sicht_nennt_die_auswahl_schwaeche_im_hinweis():
    jetzt = datetime.now(timezone.utc)
    s = M.sicht_bauen(_ledger_mit(1, 0, jetzt), jetzt, "ok", "u", "f", "")
    assert "Auswahl" in s["hinweis"], "die 'Wetten verbergen'-Lücke muss im JSON stehen"


def test_sicht_alte_wetten_fallen_aus_dem_fenster():
    jetzt = datetime.now(timezone.utc)
    alt = (jetzt - timedelta(hours=200)).isoformat().replace("+00:00", "Z")
    led = {"seit": "x", "n": 1, "wetten": [{"id": "1", "ts": alt, "einsatzUsd": 9000.0}]}
    s = M.sicht_bauen(led, jetzt, "ok", "u", "f", "")
    assert s["nFenster"] == 0
    assert s["nLedger"] == 1, "aus dem Fenster heißt nicht aus dem Ledger"


@pytest.mark.parametrize("status", ["schema_unbekannt", "fehler"])
def test_fehlerstatus_bleibt_im_json_stehen(status):
    jetzt = datetime.now(timezone.utc)
    s = M.sicht_bauen({}, jetzt, status, "", "", "403 von Cloudflare")
    assert s["status"] == status
    assert "403" in s["notiz"], "der Grund muss mitfahren, sonst sieht Ausfall aus wie Ruhe"
    assert s["wetten"] == []



# ── Schema aus Fehlermeldungen lernen ────────────────────────────────────────
# 03.09.2026: Die Sonde auf dem Mac-Runner brachte HTTP 400 „GraphQL introspection is not
# allowed by Apollo Server". Der Endpunkt lebt also, nur nachschlagen darf man nicht.
# Der Sammler lernt seitdem aus den Validierungsfehlern. Diese Tests fahren das gegen einen
# nachgebauten Apollo-Server, der genau so antwortet wie graphql-js.

def test_meinten_liest_vorschlaege():
    assert M._meinten('Cannot query field "amont" on type "SportBet". Did you mean "amount"?') \
        == ["amount"]
    assert M._meinten('Did you mean "a", "b", or "c"?') == ["a", "b", "c"]


def test_meinten_ohne_vorschlag_ist_leer():
    assert M._meinten('Cannot query field "xyz" on type "Query".') == []
    assert M._meinten("") == []


def test_baue_erzeugt_gueltige_verschachtelung():
    q = M._baue("hr", {"typ": "B", "felder": {"id": None,
                                              "user": {"typ": "U", "felder": {"name": None}}}}, "limit")
    assert q == "query HR($limit: Int) { hr(limit: $limit) { id user { name } } }"


def test_baue_ohne_argument_laesst_die_klammer_weg():
    assert "(" not in M._baue("hr", {"typ": "B", "felder": {"id": None}}).split("{", 1)[1]


class FakeApollo:
    """Ein Server mit festem Schema, der antwortet wie graphql-js: erst validieren,
    ALLE Verstöße gemeinsam melden, und bei Tippfehlern einen Vorschlag mitgeben."""

    def __init__(self, schema, wurzel="highrollerSportBets", listentyp="[SportBet!]!"):
        self.schema = schema          # {typ: {feld: None|typ}}
        self.wurzel = wurzel
        self.listentyp = listentyp
        self.anfragen = 0

    # sehr einfacher Parser: reicht für die Abfragen, die _baue erzeugt
    def _pruefe(self, sel: str, typ: str, fehler: list):
        i = 0
        felder = self.schema.get(typ, {})
        while i < len(sel):
            c = sel[i]
            if c in " {}":
                i += 1
                continue
            j = i
            while j < len(sel) and sel[j] not in " {}":
                j += 1
            name = sel[i:j]
            # folgt ein Unterblock?
            k = j
            while k < len(sel) and sel[k] == " ":
                k += 1
            hat_block = k < len(sel) and sel[k] == "{"
            if name not in felder:
                nah = [f for f in felder if f[:3] == name[:3] and f != name]
                fehler.append('Cannot query field "%s" on type "%s".%s'
                              % (name, typ, (' Did you mean "%s"?' % nah[0]) if nah else ""))
                if hat_block:
                    k = self._ueberspringe(sel, k)
                i = k
                continue
            untertyp = felder[name]
            if untertyp and not hat_block:
                fehler.append('Field "%s" of type "%s" must have a selection of subfields.'
                              % (name, untertyp))
                i = j
                continue
            if untertyp and hat_block:
                ende = self._ueberspringe(sel, k)
                self._pruefe(sel[k + 1:ende - 1], untertyp, fehler)
                i = ende
                continue
            if not untertyp and hat_block:
                fehler.append('Field "%s" must not have a selection since type has no subfields.'
                              % name)
                i = self._ueberspringe(sel, k)
                continue
            i = j

    @staticmethod
    def _ueberspringe(s, start):
        tiefe = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                tiefe += 1
            elif s[i] == "}":
                tiefe -= 1
                if tiefe == 0:
                    return i + 1
        return len(s)

    def __call__(self, url, body, timeout=25):
        self.anfragen += 1
        q = body.get("query", "")
        if "__schema" in q or "__type" in q:
            return 400, {"errors": [{"message": "GraphQL introspection is not allowed "
                                                "by Apollo Server"}]}, None
        innen = q[q.index("{") + 1:q.rindex("}")]
        kopf = innen.strip().split("{", 1)[0].strip()
        name = kopf.split("(")[0].strip()
        if name != self.wurzel:
            nah = self.wurzel if name[:5] == self.wurzel[:5] else None
            return 200, {"errors": [{"message": 'Cannot query field "%s" on type "Query".%s'
                                     % (name, (' Did you mean "%s"?' % nah) if nah else "")}]}, None
        if "{" not in innen:
            return 200, {"errors": [{"message":
                'Field "%s" of type "%s" must have a selection of subfields.'
                % (self.wurzel, self.listentyp)}]}, None
        if "(" in kopf and "limit" not in kopf:
            return 200, {"errors": [{"message": 'Unknown argument "%s" on field "%s".'
                                     % (kopf.split("(")[1].split(":")[0], self.wurzel)}]}, None
        sel = innen[innen.index("{") + 1:innen.rindex("}")]
        fehler = []
        self._pruefe(sel, self.listentyp.strip("[]!"), fehler)
        if fehler:
            return 200, {"errors": [{"message": m} for m in fehler]}, None
        return 200, {"data": {self.wurzel: [{"id": "1"}]}}, None


SCHEMA = {
    "SportBet": {"id": None, "amount": None, "currency": None, "odds": None,
                 "createdAt": None, "user": "User", "outcomes": "Outcome"},
    "User": {"id": None, "name": None},
    "Outcome": {"odds": None, "outcome": "Auswahl", "fixture": "Fixture"},
    "Auswahl": {"name": None},
    "Fixture": {"name": None, "startingAt": None, "tournament": "Turnier"},
    "Turnier": {"name": None},
}


def test_feld_raten_findet_die_wurzel_ueber_vorschlaege(monkeypatch):
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    feld, typ, notiz = M._feld_raten("http://test")
    assert feld == "highrollerSportBets"
    assert typ == "[SportBet!]!"


def test_feld_raten_meldet_wenn_der_server_nichts_verraet(monkeypatch):
    stumm = FakeApollo(SCHEMA, wurzel="völligAndererName")
    monkeypatch.setattr(M, "_post", stumm)
    feld, typ, grund = M._feld_raten("http://test")
    assert feld is None
    assert "Vorschl" in grund or "verrät" in grund or "verraet" in grund


def test_schema_lernen_konvergiert_auf_eine_gueltige_abfrage(monkeypatch):
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    query, notiz = M.schema_lernen("http://test", "highrollerSportBets", "[SportBet!]!", "limit")
    assert query, notiz
    for feld in ("id", "amount", "currency", "odds", "createdAt"):
        assert feld in query, "%s fehlt in der gelernten Abfrage" % feld
    assert "user { " in query and "name" in query
    assert "outcomes { " in query


def test_schema_lernen_braucht_wenige_anfragen(monkeypatch):
    """Eine Ebene = eine Anfrage. Sonst wird aus Lernen ein Rate-Limit."""
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    M.schema_lernen("http://test", "highrollerSportBets", "[SportBet!]!", "limit")
    assert fake.anfragen <= M.LERN_RUNDEN, "%d Anfragen — zu viele" % fake.anfragen


def test_schema_lernen_erfindet_keine_felder(monkeypatch):
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    query, _ = M.schema_lernen("http://test", "highrollerSportBets", "[SportBet!]!", "limit")
    erlaubt = set()
    for felder in SCHEMA.values():
        erlaubt |= set(felder)
    for wort in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query.split("{", 1)[1]):
        if wort in ("query", "HR", "Int", "limit", "highrollerSportBets"):
            continue
        assert wort in erlaubt, "erfundenes Feld in der Abfrage: " + wort


def test_schema_lernen_gibt_bei_fremden_fehlern_auf(monkeypatch):
    def boese(url, body, timeout=25):
        return 200, {"errors": [{"message": "You must be logged in"}]}, None
    monkeypatch.setattr(M, "_post", boese)
    query, grund = M.schema_lernen("http://test", "irgendwas", "Egal", "")
    assert query is None
    assert "logged in" in grund, "der echte Grund muss durchkommen, nicht 'nicht konvergiert'"


def test_limit_arg_erkennt_das_akzeptierte_argument(monkeypatch):
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    assert M._limit_arg("http://test", "highrollerSportBets") == "limit"


def test_schema_finden_nutzt_den_lernweg_wenn_introspection_zu_ist(monkeypatch):
    fake = FakeApollo(SCHEMA)
    monkeypatch.setattr(M, "_post", fake)
    feld, query, notiz = M.schema_finden("http://test")
    assert feld == "highrollerSportBets"
    assert query and "amount" in query
    assert "gelernt" in notiz


def test_anwenden_streicht_und_klappt_gleichzeitig():
    k = {"typ": "SportBet", "felder": {"id": None, "quatsch": None, "user": None}}
    M._anwenden(k, {"SportBet": {"quatsch"}}, {"user": "User"}, set(), tiefe=3)
    assert "quatsch" not in k["felder"]
    assert k["felder"]["id"] is None
    assert k["felder"]["user"]["typ"] == "User"


def test_anwenden_streicht_nur_auf_dem_gemeldeten_typ():
    """Der Denkfehler vom 03.09.: `amount` gibt es auf SportBet, auf User nicht.
    Ein globaler Streich nach Feldnamen hat das gueltige amount mitgerissen."""
    k = {"typ": "SportBet", "felder": {
        "amount": None,
        "user": {"typ": "User", "felder": {"amount": None, "name": None}}}}
    M._anwenden(k, {"User": {"amount"}}, {}, set(), tiefe=3)
    assert k["felder"]["amount"] is None, "amount auf SportBet muss stehen bleiben"
    assert "amount" not in k["felder"]["user"]["felder"]
    assert "name" in k["felder"]["user"]["felder"]


def test_anwenden_klappt_nicht_ueber_die_tiefe_hinaus():
    k = {"typ": "SportBet", "felder": {"user": None}}
    M._anwenden(k, {}, {"user": "User"}, set(), tiefe=1)
    assert k["felder"] == {}, "jenseits der Tiefe wird weggelassen, nicht ungueltig gebaut"


def test_anwenden_klappt_zyklen_nicht_auf():
    k = {"typ": "SportBet", "felder": {
        "user": {"typ": "User", "felder": {"name": None, "bet": None}}}}
    M._anwenden(k, {}, {"bet": "SportBet"}, set(), tiefe=4)
    assert "bet" not in k["felder"]["user"]["felder"], "SportBet -> User -> SportBet waere ein Zyklus"
    assert "name" in k["felder"]["user"]["felder"], "der Rest des Knotens bleibt"


def test_anwenden_wirft_einen_leer_geraeumten_knoten_weg():
    """Ein Objektfeld ohne ein einziges gueltiges Unterfeld ist keine gueltige Selektion."""
    k = {"typ": "SportBet", "felder": {"user": {"typ": "User", "felder": {"bet": None}}}}
    M._anwenden(k, {}, {"bet": "SportBet"}, set(), tiefe=4)
    assert k["felder"] == {}


def test_anwenden_klappt_einen_falsch_geoeffneten_block_wieder_ein():
    k = {"typ": "SportBet", "felder": {"name": {"typ": "X", "felder": {"a": None}}}}
    M._anwenden(k, {}, {}, {"name"}, tiefe=3)
    assert k["felder"]["name"] is None

# ── Der Quelltext darf keine unbelegte Bewertung enthalten ───────────────────
def test_quelltext_bewertet_nicht():
    txt = (ROOT / "stake_highroller_fetch.py").read_text(encoding="utf-8")
    code = "\n".join(z for z in txt.splitlines() if not z.strip().startswith("#"))
    # Der Docstring darf die Begriffe erklären; im CODE haben sie nichts zu suchen.
    code = code.split('"""')[-1]
    for wort in ("strong", "Strong", "medium", "weak", "verdacht", "fixed"):
        assert wort not in code, (
            "'%s' im Code: eine Bewertung ohne gemessene Trefferquote gehört hier nicht rein" % wort)
