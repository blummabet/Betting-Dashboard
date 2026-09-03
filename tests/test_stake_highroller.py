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


# ── Normalisierung am ECHTEN Feed ────────────────────────────────────────────
# 03.09.2026: dieser Datensatz ist nicht erfunden — er stammt eins zu eins aus der Antwort,
# die stake.com/_api/graphql auf die Abfrage der eigenen Highroller-Seite gibt.
ROH = {
    "__typename": "Bet", "id": "2f57628a-6127-432e-84ce-b3c374ed4246",
    "iid": "sport:648201156",
    "bet": {
        "__typename": "SportBet", "id": "2f57628a", "customBet": False,
        "createdAt": "Thu, 03 Sep 2026 19:12:06 GMT",
        "updatedAt": "Thu, 03 Sep 2026 19:12:20 GMT",
        "potentialMultiplier": 1.01, "amount": 2360, "currency": "usdc",
        "user": None,
        "outcomes": [{
            "id": "19588d59", "odds": 1.01, "status": "pending",
            "fixtureName": "Taylor Fritz - Bellucci, Mattia",
            "fixtureAbreviation": "FRI - BEL",
            "outcome": {"id": "19588d59", "name": "Taylor Fritz"},
            "market": {"id": "6a0adba7", "name": "Winner"},
            "fixture": {
                "id": "7a9c210e", "startTime": "Thu, 03 Sep 2026 18:10:00 GMT",
                "tournament": {"id": "a1897704", "name": "US Open Men Singles",
                               "slug": "us-open-men-singles",
                               "category": {"sport": {"slug": "tennis", "name": "Tennis"}}},
            },
        }],
    },
}

KOMBI = {
    "id": "9d650dff", "iid": "sport:648199979",
    "bet": {"__typename": "SportBet", "amount": 2000, "currency": "cad",
            "createdAt": "Thu, 03 Sep 2026 19:10:10 GMT",
            "potentialMultiplier": 3.976, "customBet": False, "user": None,
            "outcomes": [
                {"id": "23d7afb8", "odds": 3.55, "fixtureName": "Schoolkate - Cobolli",
                 "outcome": {"name": "Tristan Schoolkate"}, "market": {"name": "Winner"},
                 "fixture": {"id": "4bcf221a", "startTime": "Thu, 03 Sep 2026 20:00:00 GMT",
                             "tournament": {"name": "US Open", "slug": "us-open",
                                            "category": {"sport": {"slug": "tennis"}}}}},
                {"id": "3b1970ba", "odds": 1.12, "fixtureName": "Oliynykova - Eala",
                 "outcome": {"name": "Alexandra Eala"}, "market": {"name": "Winner"},
                 "fixture": {"id": "d74fea51", "startTime": "Thu, 03 Sep 2026 21:00:00 GMT",
                             "tournament": {"name": "US Open", "slug": "us-open",
                                            "category": {"sport": {"slug": "tennis"}}}}},
            ]},
}


def test_normalisiere_zieht_alles_aus_dem_echten_datensatz():
    n = M.normalisiere(ROH)
    assert n["id"] == "sport:648201156", "die iid ist die Nummer vom Wettschein"
    assert n["einsatzUsd"] == 2360.0
    assert n["waehrung"] == "usdc"
    assert n["quote"] == 1.01
    assert n["markt"] == "Winner"
    assert n["auswahl"] == "Taylor Fritz"
    assert n["liga"] == "US Open Men Singles"
    assert n["sport"] == "tennis"
    assert n["eventId"] == "7a9c210e"
    assert n["kombi"] is False


def test_rfc1123_zeitstempel_werden_zu_iso():
    """Stake liefert 'Thu, 03 Sep 2026 19:12:06 GMT', nicht ISO. Ohne diese Umrechnung
    haette das Fenster keine einzige Wette einordnen koennen — eine volle Sammlung waere
    im Dashboard als 'keine grossen Wetten' erschienen."""
    n = M.normalisiere(ROH)
    assert n["ts"] == "2026-09-03T19:12:06Z"
    assert n["anpfiff"] == "2026-09-03T18:10:00Z"
    ab = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert M._im_fenster(n, ab) is True, "und sie muss danach auch wirklich ins Fenster fallen"


def test_zeit_faellt_auf_none_statt_auf_jetzt():
    assert M._zeit("voelliger Unsinn") is None
    assert M._zeit(None) is None
    assert M._zeit("") is None


def test_zeit_nimmt_auch_iso_an():
    assert M._zeit("2026-09-03T19:12:06Z") == "2026-09-03T19:12:06Z"


def test_user_ist_immer_leer_und_das_bleibt_sichtbar():
    """Stake anonymisiert die Liste vollstaendig. Das Feld bleibt im Datensatz, damit
    niemand spaeter einen Track-Record je Konto darauf plant."""
    n = M.normalisiere(ROH)
    assert "user" in n
    assert n["user"] is None


def test_kombi_wird_als_solche_erkannt():
    n = M.normalisiere(KOMBI)
    assert n["kombi"] is True
    assert n["nBeine"] == 2
    assert n["einsatzUsd"] is None, "cad hat keinen Kurs im Feed — unbekannt, nicht null"
    assert n["quote"] == 3.976
    assert n["beinQuote"] == 3.55, "die Quote des ersten Beins bleibt getrennt von der Gesamtquote"


def test_normalisiere_ueberlebt_fehlende_felder():
    n = M.normalisiere({"id": "x"})
    assert n["id"] == "x"
    assert n["einsatzUsd"] is None
    assert n["quote"] is None
    assert n["kombi"] is False


def test_normalisiere_setzt_keinen_default_auf_null():
    n = M.normalisiere({"id": "x", "bet": {"amount": 5.0, "currency": "btc"}})
    assert n["betrag"] == 5.0
    assert n["einsatzUsd"] is None, "unbekannter USD-Wert darf nicht 0 werden"


def test_normalisiere_faellt_auf_die_tiefensuche_zurueck():
    """Baut Stake um, soll wenigstens der Betrag noch ankommen statt still zu fehlen."""
    n = M.normalisiere({"id": "x", "irgendwo": {"tief": {"amount": 4200, "currency": "usdt"}}})
    assert n["einsatzUsd"] == 4200.0


def test_die_verifizierte_abfrage_holt_die_felder_die_wir_auswerten():
    q = M.QUERY_BEKANNT
    for feld in ("iid", "amount", "currency", "potentialMultiplier", "createdAt",
                 "customBet", "outcomes", "outcome", "market", "fixtureName",
                 "startTime", "tournament", "sport"):
        assert feld in q, "%s fehlt in der verifizierten Abfrage" % feld
    assert M.FELD_BEKANNT == "highrollerSportBets"


def test_limit_ist_hart_gedeckelt():
    """Am 03.09. gemessen: limit=50 liefert 50 Eintraege, limit=51 liefert KOMMENTARLOS 0.
    Kein Fehler, keine Warnung — im Dashboard sieht das aus wie ein ruhiger Tag."""
    assert M.MAX_LIMIT == 50
    m = _modul(STAKE_LIMIT=500)
    assert min(m.ABRUF_LIMIT, m.MAX_LIMIT) == 50, "eine zu hohe Env darf den Feed nicht abwuergen"


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
    assert "Schreibweisen" in grund and "schlaegt nichts vor" in grund, grund


def test_post_liest_den_json_body_auch_bei_http_400(monkeypatch):
    """03.09.2026 — der Fehler, der den Lernweg lahmlegte: GraphQL antwortet auf
    Validierungsfehler mit HTTP 400 UND einem gueltigen errors-Body. Genau der ist die
    Auskunft. Ein Statuscode ist kein Grund, den Inhalt nicht zu lesen."""
    import io, urllib.error

    def wirft(req, timeout=25):
        raise urllib.error.HTTPError(
            "u", 400, "Bad Request", {},
            io.BytesIO(b'{"errors":[{"message":"Cannot query field \\"x\\" on type \\"Query\\"."}]}'))

    monkeypatch.setattr(M.urllib.request, "urlopen", wirft)
    st, d, err = M._post("http://test", {"query": "{ x }"})
    assert st == 400
    assert err is None, "ein lesbarer errors-Body ist kein Transportfehler"
    assert d["errors"][0]["message"].startswith("Cannot query field")


def test_post_meldet_echten_transportfehler_weiter(monkeypatch):
    import io, urllib.error

    def wirft(req, timeout=25):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {},
                                     io.BytesIO(b"<html>Just a moment...</html>"))

    monkeypatch.setattr(M.urllib.request, "urlopen", wirft)
    st, d, err = M._post("http://test", {"query": "{ x }"})
    assert st == 403 and d is None
    assert "403" in err, "eine Cloudflare-Seite ist kein Schema — der Fehler muss sichtbar bleiben"


def test_feld_raten_gibt_bei_lauter_transportfehlern_frueh_auf(monkeypatch):
    """Ein 403 auf jede Schreibweise ist ein toter Endpunkt, kein Schema-Rätsel —
    da lohnt es nicht, alle Kandidaten durchzuprobieren."""
    rufe = []

    def tot(url, body, timeout=25):
        rufe.append(body)
        return 403, None, "HTTP 403 Just a moment..."

    monkeypatch.setattr(M, "_post", tot)
    feld, _t, grund = M._feld_raten("http://test")
    assert feld is None
    assert "antwortet nicht" in grund
    assert len(rufe) < len(M.QUERY_SAAT), "nicht die ganze Liste gegen eine Wand fahren"


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
