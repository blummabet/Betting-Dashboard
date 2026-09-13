"""tests/test_stake_liga_stufe.py — 07.09.2026

Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein 2-3. Liga Team / Ist
zumindest jemand der mehr dran glaubt mmn."

Was hier schiefgehen kann, ist nicht die Rechnung, sondern die ZUORDNUNG:

 · Eine Liga, die nicht in der Tabelle steht, darf nicht wie eine oberste Spielklasse
   aussehen. Fehlende Information ist keine Erlaubnis — dieselbe Klasse, die im Repo schon
   mehrfach zugeschlagen hat.
 · Der Slug ist nicht sportartenrein: `bundesliga` gibt es im Feed als Fussball UND als
   Handball, `premier-league-srl` als Fussball und Cricket. Eine Handball-Wette darf keine
   Fussball-Spielklasse bekommen.
 · Der Referenzeinsatz muss sagen, WOHER er kommt. „3x der Norm" heisst etwas anderes, wenn
   die Norm aus 600 Wetten derselben Liga stammt, als wenn sie der Median der ganzen Ebene ist.
 · Ebene 1 und Ebene 2/3 laufen gegenlaeufig (gemessen 07.09.: -2,1 % -> -13,9 % gegen
   +7,5 % -> +46,7 %). Wer beide in eine Schublade wirft, mittelt genau den Unterschied weg —
   die Dilutions-Klasse aus CAPABILITIES §7. Deshalb ein Test, der die Trennung festhaelt.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stake_liga_stufe as LS


def w(slug="championship", usd=10000.0, sport="soccer", liga=None, quote=2.0, pnl=None,
      event="A - B", kombi=False):
    d = {"ligaSlug": slug, "sport": sport, "liga": liga if liga is not None else slug,
         "einsatzUsd": usd, "quote": quote, "kombi": kombi, "event": event,
         "eventId": event, "markt": "Match Result", "auswahl": "A", "id": event + slug}
    if pnl is not None:
        d["abrechnung"] = {"pnlUsd": pnl, "beine": [{"status": "won" if pnl > 0 else "lost"}]}
    return d


# ── Zuordnung ────────────────────────────────────────────────────────────────
def test_ebenen_sitzen_richtig():
    assert LS.stufe("premier-league") == "1"
    assert LS.stufe("championship") == "2"        # zweite Klasse, obwohl grosser Markt
    assert LS.stufe("league-two") == "3"
    assert LS.randliga("championship") and LS.randliga("league-two")
    assert not LS.randliga("premier-league")


def test_unbekannte_liga_ist_none_und_nicht_ebene_1():
    """Der eigentliche Fehlerfall: eine neue Liga taucht auf und zaehlt still als Spitzenliga."""
    assert LS.stufe("liga-die-es-noch-nicht-gibt") is None
    assert LS.randliga("liga-die-es-noch-nicht-gibt") is False


def test_slug_ist_nicht_sportartenrein():
    """`bundesliga` ist im Feed Fussball UND Handball — die Handball-Zeile bekommt nichts."""
    assert LS.stufe("bundesliga", "soccer") == "1"
    assert LS.stufe("bundesliga", "handball") is None
    assert LS.stufe("premier-league-srl", "cricket") is None


def test_wettbewerbe_bekommen_eine_marke_statt_einer_zahl():
    assert LS.stufe("uefa-champions-league") == "kontinental"
    assert LS.stufe("fa-cup") == "pokal"
    assert LS.stufe("u20-womens-world-cup") == "jugend"
    assert LS.stufe("laliga-srl") == "srl"
    assert LS.stufe("women-bundesliga") == "frauen"
    # und keines davon zaehlt als Randliga, auch wenn es klein ist
    assert not LS.randliga("fa-cup")


def test_reservemannschaften_sind_keine_spielklasse():
    """07.09.2026 — am Tag nach dem Bau stand „Primera Division Reserve, Clausura" als
    einzige Liga ohne Ebene da. Zweite Mannschaften sind keine Spielklasse; sie bekommen eine
    Marke, und zwar per MUSTER, damit die naechste nicht wieder von Hand nachkommen muss."""
    assert LS.stufe("primera-division-reserve-clausura") == "reserve"
    assert LS.stufe("bundesliga-reserve") == "reserve"
    assert not LS.randliga("primera-division-reserve-clausura")


def test_srl_faellt_nicht_als_echte_liga_durch():
    """Simulated Reality League sind simulierte Spiele. Sie duerfen nicht als Ebene 1 gelten,
    nur weil der Slug wie die echte Liga anfaengt."""
    for s in ("premier-league-srl", "laliga-srl", "serie-a-srl", "bundesliga-srl", "ligue-1-srl"):
        assert LS.stufe(s) == "srl", s


# ── Referenz ─────────────────────────────────────────────────────────────────
def test_referenz_nennt_ihre_basis():
    # Genug Zeilen je Ebene, damit BEIDE Ebenen einen Median haben — die Ebene-Norm
    # entsteht je Ebene, nicht global (der globale Median waere Tennis).
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("league-two", 2000.0) for _ in range(20)])
    ebmed = LS.ebene_median(wetten)
    norm = {"Championship": {"basis": "gelernt", "median": 1000.0}}
    # eigene Liga-Norm vorhanden -> Basis "liga"
    f, basis = LS.faktor(w("championship", 5000.0, liga="Championship"), norm, ebmed)
    assert basis == "liga" and f == 5.0
    # keine Liga-Norm -> Median der EBENE, und das steht auch dran
    f2, basis2 = LS.faktor(w("league-two", 4000.0, liga="League Two"), {}, ebmed)
    assert basis2 == "ebene" and f2 == 2.0


def test_ohne_jede_basis_gibt_es_keinen_faktor():
    """Kein Rueckfall auf einen globalen Median: der wird von Tennis und E-Sport getragen."""
    f, basis = LS.faktor(w("league-two", 4000.0), {}, {})
    assert f is None and basis == "unbekannt"


def test_ebene_median_ignoriert_kombis_und_fremde_sportarten():
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("championship", 999999.0, kombi=True)]
              + [w("bundesliga", 999999.0, sport="handball")])
    assert LS.ebene_median(wetten)["2"] == 2000.0


def test_ebene_median_erst_ab_min_n():
    assert LS.ebene_median([w("championship", 2000.0) for _ in range(LS.EBENE_MIN_N - 1)]) == {}


# ── Auswahl und Kreuztabelle ─────────────────────────────────────────────────
def test_kandidaten_nur_ebene_2_und_tiefer():
    basis = ([w("championship", 2000.0, liga="Championship") for _ in range(20)]
             + [w("league-two", 2000.0, liga="League Two") for _ in range(20)]
             + [w("premier-league", 2000.0, liga="Premier League") for _ in range(20)])
    wetten = basis + [w("premier-league", 500000.0, liga="Premier League", event="gross oben"),
                      w("league-two", 20000.0, liga="League Two", event="gross unten")]
    got = {k["event"] for k in LS.kandidaten(wetten, {})}
    assert "gross unten" in got
    assert "gross oben" not in got, "Ebene 1 gehoert in die andere Schublade, nicht hierher"


def test_kandidaten_zeigen_auch_die_verlierer():
    """Ohne Ausgangsfilter — sonst waere die Liste ihre eigene Erfolgsmeldung."""
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("championship", 30000.0, pnl=-30000.0, event="daneben")])
    assert any(k["event"] == "daneben" for k in LS.kandidaten(wetten, {}))


def test_kreuz_trennt_die_gegenlaeufigen_ebenen():
    """Der Grund fuer zwei Schubladen: gemischt heben sich die Reihen auf."""
    wetten = []
    for i in range(20):
        wetten.append(w("premier-league", 2000.0, liga="Premier League"))
        wetten.append(w("championship", 2000.0, liga="Championship"))
    # oben gross und schlecht, unten gross und gut
    for i in range(6):
        wetten.append(w("premier-league", 20000.0, liga="Premier League", pnl=-20000.0,
                        event="oben%d" % i))
        wetten.append(w("championship", 20000.0, liga="Championship", pnl=+20000.0,
                        event="unten%d" % i))
    k = LS.kreuz(wetten, {})
    assert k["1"][">6x"]["roi"] < 0
    assert k["2"][">6x"]["roi"] > 0


def test_beide_richtungen_koennen_ein_urteil_tragen():
    """Folgen belegt die Untergrenze ueber null, dagegenhalten die OBERgrenze unter null.

    Mit der Untergrenze allein waere eine Reihe, die stabil verliert, auf ewig „kein Urteil" —
    obwohl sie genau die Aussage traegt, um die es hier geht.
    """
    # Genug kleine Zeilen, damit der Median NICHT von den grossen mitgezogen wird — sonst
    # faellt jeder grosse Einsatz in die unterste Spalte und der Test misst etwas anderes.
    wetten = [w("premier-league", 2000.0, liga="Premier League") for _ in range(200)]
    # 40 grosse Einsaetze oben, alle daneben: die Obergrenze muss unter null landen
    wetten += [w("premier-league", 20000.0, liga="Premier League", pnl=-20000.0,
                 quote=2.0, event="oben%d" % i) for i in range(40)]
    z = LS.kreuz(wetten, {})["1"][">6x"]
    assert z["flachOg"] is not None and z["flachOg"] < 0
    assert z["belegtGegen"] is True and z["belegt"] is False


def test_kreuz_gibt_unter_30_keine_untergrenze():
    """Ein Punktschaetzer ist kein Beleg — der harte Boden gilt auch hier."""
    wetten = [w("championship", 2000.0, liga="Championship") for _ in range(20)]
    wetten += [w("championship", 20000.0, liga="Championship", pnl=+20000.0, event="x%d" % i)
               for i in range(5)]
    z = LS.kreuz(wetten, {})["2"][">6x"]
    assert z["n"] == 5 and z["flachUg"] is None and z["flachOg"] is None
    assert z["belegt"] is False and z["belegtGegen"] is False


# ── Was der Slug selbst sagt (07.09.2026) ────────────────────────────────────
def test_ordnungszahl_im_slug_wird_gelesen():
    """„2nd-division-league" und „super-league-2" waren der zweite Nachtrag in zwei Tagen.
    Beide Male stand die Antwort im Namen — eine handgepflegte Liste, die das nicht liest,
    schweigt genau fuer die Ligen, die neu sind."""
    assert LS.stufe("2nd-division-league") == "2"
    assert LS.stufe("3rd-liga") == "3"
    assert LS.stufe("super-league-2") == "2"


def test_der_anhang_zaehlt_nur_hoch_wenn_der_rumpf_bekannt_ist():
    """Sonst wird aus einer Gruppennummer still eine zweite Liga."""
    assert LS.stufe("irgendwas-2") is None
    assert LS.stufe("super-league") == "1", "der Rumpf bleibt, was er war"


def test_die_regel_raet_nicht_bei_allem_anderen():
    assert LS.stufe("gibt-es-nicht") is None
    assert LS.stufe("2nd-division-league", sport="handball") is None


def test_tabelle_schlaegt_regel():
    """Die Tabelle ist Wissen, die Regel nur eine Lesehilfe — nie andersherum."""
    assert LS.stufe("la-liga-2") == "2" and "la-liga-2" in LS.EBENE


# ── Kandidatenauswahl: zwei Achsen, eine Auswahl ─────────────────────────────
def test_kandidaten_kommen_ueber_faktor_ODER_betrag_herein():
    """Eine nach Faktor abgeschnittene Liste laesst sich nicht ehrlich nach Betrag sortieren:
    der groesste Betrag des Tages kann bei Faktor 3,1 liegen und waere nie in der Auswahl."""
    norm = {"L": {"median": 1000.0, "basis": "gelernt", "n": 50}}
    # 40 Zeilen mit hohem Faktor, aber kleinem Betrag — sie fuellen den Faktor-Deckel.
    viele = [w("championship", 4000.0 + i, liga="L", event="hoch%d" % i) for i in range(40)]
    # Eine mit dem groessten Betrag und dem KLEINSTEN Faktor der Auswahl.
    dickes = w("championship", 3100.0, liga="L", event="dick")
    dickes["einsatzUsd"] = 3100.0
    k = LS.kandidaten(viele + [dickes], norm)
    ids = {x["id"]: x for x in k}
    assert "hoch39championship" in ids, "die Faktor-Achse fehlt"
    # Und nun mit einem echten Brocken: er muss ueber die Betrags-Achse hereinkommen.
    brocken = w("championship", 500000.0, liga="L", event="brocken")
    k2 = {x["id"]: x for x in LS.kandidaten(viele + [brocken], norm)}
    assert "brockenchampionship" in k2, "der groesste Betrag fehlt in der Auswahl"
    assert "betrag" in k2["brockenchampionship"]["warumDrin"]


def test_jede_zeile_sagt_warum_sie_drin_ist():
    norm = {"L": {"median": 1000.0, "basis": "gelernt", "n": 50}}
    k = LS.kandidaten([w("championship", 9000.0, liga="L", event="a")], norm)
    assert k and set(k[0]["warumDrin"]) <= {"faktor", "betrag"}
    assert k[0]["warumDrin"], "ohne Grund ist die Zeile beim anderen Blick ein Raetsel"


def test_block_meldet_ligen_ohne_ebene():
    wetten = [w("gibt-es-nicht", 2000.0) for _ in range(3)]
    b = LS.block(wetten, {})
    assert b["nOhneEbene"] == 1 and "gibt-es-nicht" in b["ohneEbene"]


def test_alle_ligen_im_echten_ledger_haben_eine_ebene():
    """Der Wachhund gegen stilles Veralten: taucht eine neue Fussball-Liga auf, faellt sie
    hier auf, und nicht erst in einer Tabelle, in der sie nicht vorkommt."""
    import json
    p = ROOT / "stake_bet_ledger.json"
    if not p.exists():
        import pytest
        pytest.skip("kein Ledger im Arbeitsverzeichnis")
    rows = (json.load(open(p, encoding="utf-8")) or {}).get("wetten") or []
    fehlt = sorted({r.get("ligaSlug") for r in rows
                    if r.get("sport") == "soccer" and r.get("ligaSlug")
                    and LS.stufe(r.get("ligaSlug"), r.get("sport")) is None})
    assert not fehlt, ("Fussball-Ligen ohne Ebene in stake_liga_stufe.py: %s"
                       % ", ".join(fehlt[:20]))


# ── 08.09.2026: der CI-Wachhund hat zugeschlagen ────────────────────────────
# `test_alle_ligen_im_echten_ledger_haben_eine_ebene` fiel mit zwei Slugs:
# „veikkausliiga" und „uefa-youth-league". Genau dafuer gibt es ihn — aber ein Guard, der
# feuert und danach nur von Hand geflickt wird, feuert beim naechsten Wettbewerb wieder.
def test_finnische_spitze_ist_ebene_1():
    # Ykkonen (2) und Kolmonen (3) standen seit dem ersten Tag in der Tabelle — die oberste
    # Klasse desselben Landes fehlte. Eine Tabelle mit einem Loch in der Mitte faellt nicht auf.
    assert LS.stufe("veikkausliiga") == "1"
    assert LS.stufe("ykkonen") == "2"
    assert LS.stufe("kolmonen") == "3"


def test_eine_auszeichnung_ist_kein_wettbewerb():
    """09.09.2026, vierter Wachhund-Treffer — und eine ANDERE Klasse als die drei davor.
    „reserva", „efl-trophy" und „mizoram-premier-league" waren Wettbewerbe, deren Ebene nur
    fehlte. Der Ballon d'Or ist gar keiner: „Ballon dor 2026 · Winner · Harry Kane" ist eine
    Auszeichnung mit einem Sieger. Eine Spielklasse dafuer waere erfunden."""
    assert LS.stufe("ballon-dor") == "auszeichnung"
    assert LS.stufe("golden-boy") == "auszeichnung"
    # Gegenprobe: „winner" oder „award" in einem echten Ligennamen darf nichts ausloesen.
    assert LS.stufe("premier-league") == "1"
    assert LS.stufe("championship") == LS.stufe("championship")
    assert LS.stufe("usl-championship") == "1"


def test_premier_im_namen_ist_keine_spielklasse():
    """09.09.2026, dritter Wachhund-Treffer des Tages: „mizoram-premier-league". Eine indische
    STAATSliga — trotz „Premier" im Namen nicht die oberste Klasse des Landes. Genau deshalb
    gehoert sie in die Tabelle und nicht in eine Regel: ein Muster wuerde aus dem Wort das
    Gegenteil lesen."""
    assert LS.stufe("mizoram-premier-league") == "3"
    # Gegenprobe: die echten obersten Klassen bleiben, wo sie sind.
    assert LS.stufe("premier-league") == "1"
    assert LS.stufe("premier-soccer-league") == "1"


def test_pokal_heisst_nicht_ueberall_cup():
    """08.09.2026, zweiter Wachhund-Treffer des Tages: „efl-trophy". Die Regel kannte drei
    Woerter fuer Pokal — englisch, spanisch, deutsch. Trophy, Shield, Coupe und Taca sind
    derselbe Wettbewerbstyp und fielen durch. Dieselbe Klasse wie „reserve" gegen „reserva"."""
    assert LS.stufe("efl-trophy") == "pokal"
    assert LS.stufe("coupe-de-france") == "pokal"
    assert LS.stufe("taca-de-portugal") == "pokal"
    # Gegenprobe: eine echte Spielklasse darf die breitere Regel nicht verschlucken.
    assert LS.stufe("premier-league") == "1"
    assert LS.stufe("la-liga-2") == "2"


def test_reserveliga_in_jeder_sprache():
    """08.09.2026: der Wachhund fiel mit „campeonato-de-reserva-de-primera-division-c".
    Die Regel kannte nur „reserve" — dieselbe Sache heisst in Suedamerika „reserva" und in
    Italien „riserve". Ein Muster, das eine Sprache kennt, ist kein Muster, sondern ein
    Einzelfall mit Platzhalter."""
    assert LS.stufe("campeonato-de-reserva-de-primera-division-c") == "reserve"
    assert LS.stufe("primera-division-reserve-clausura") == "reserve"
    assert LS.stufe("campionato-primavera-riserve") in ("reserve", "jugend")
    # Gegenprobe: die breitere Regel darf keine echte Spielklasse verschlucken.
    assert LS.stufe("usl-championship") == "1"
    assert LS.stufe("la-liga-2") == "2"


def test_ausgeschriebener_nachwuchs_wird_erkannt():
    # Die Regel las nur die ersten drei Zeichen und fing deshalb „u19-…", aber keinen
    # Wettbewerb, der seine Jugend ausschreibt.
    for slug in ("uefa-youth-league", "premier-league-youth", "primavera-1",
                 "junior-league", "academy-cup-de"):
        assert LS.stufe(slug) == "jugend", slug


def test_kuerzel_zaehlt_auch_mitten_im_slug():
    assert LS.stufe("u19-bundesliga") == "jugend"
    assert LS.stufe("npl-victoria-u21") == "jugend"


def test_die_breitere_regel_stuft_nichts_um():
    # Gegenprobe an allen 170 Fussball-Slugs des echten Ledgers: die alte Prefix-Regel und die
    # neue duerfen sich nur dort unterscheiden, wo vorher GAR NICHTS herauskam.
    alt = lambda s: s[:3] in ("u17", "u19", "u20", "u21", "u23")
    for slug in ("usl-championship", "u20-womens-world-cup", "u23-queensland-npl",
                 "uefa-champions-league", "eliteserien", "championship", "league-two"):
        neu_j = bool(LS._JUGEND_RX.search(slug))
        if alt(slug):
            assert neu_j, "%s war Jugend und darf es bleiben" % slug


def test_nachwuchs_schlaegt_kontinental():
    # Die UEFA Youth League ist beides. Fuer die Frage, die diese Tabelle beantwortet — wie
    # verhaelt sich ein grosser Einsatz —, ist „Nachwuchs" die staerkere Auskunft.
    assert LS.stufe("uefa-youth-league") == "jugend"
    assert LS.stufe("uefa-champions-league") == "kontinental"


# ── 10.09.2026: der Wachhund, vierter und fuenfter Slug ──────────────────────
def test_super_im_namen_entscheidet_nicht_ueber_die_ebene():
    """„superettan" ist Schwedens ZWEITE Klasse — und heisst trotzdem „super".

    Das ist der Grund, warum diese beiden Slugs in der TABELLE stehen und nicht in einer
    Regel: ein Muster auf „super" wuerde vier korrekte Ebene-1-Eintraege umstuerzen, um
    einen einzigen Nachtrag zu sparen. Der Wachhund wird deshalb bei jedem neuen Land
    wieder feuern — das ist kein Mangel, sondern die ehrliche Antwort darauf, dass ein
    Ligaslug seine Spielklasse nicht mitbringt.
    """
    assert LS.stufe("superettan") == "2"
    for eins in ("super-lig", "super-league", "super-league-1", "chinese-super-league"):
        assert LS.stufe(eins) == "1", eins


def test_v_league_nur_im_fussball():
    """Vietnams oberste Klasse — aber „v-league" heisst in Korea und Japan die
    VOLLEYBALL-Liga. Die Ebene darf deshalb nur unter `sport == "soccer"` herauskommen;
    dieselbe Vorsichtsmassnahme, die „bundesliga" (Fussball und Handball) braucht."""
    assert LS.stufe("v-league") == "1"
    assert LS.stufe("v-league", "volleyball") is None
    assert LS.stufe("v-league", "basketball") is None


# ── 10.09.2026, zweiter Schlag des Wachhunds ─────────────────────────────────
def test_der_pokal_haengt_den_artikel_auch_hinten_an():
    """„dbu-pokalen" — dieselbe Klasse wie „efl-trophy" und „reserva": ein Pokal, den die Regel
    nicht als Pokal las. `-pokal` fing die deutsche Form; im Skandinavischen haengt der bestimmte
    Artikel HINTEN an („pokalen" = der Pokal, „cupen" = der Cup)."""
    for slug in ("dbu-pokalen", "nm-cupen-pokalen", "svenska-pokalen", "norges-cupen"):
        assert LS.stufe(slug) == "pokal", slug
    assert LS.stufe("dfb-pokal") == "pokal"          # die alte Form bleibt
    # ⚠️ Die Regel verlangt eine WORTGRENZE. Ein Slug, der den Pokal ohne Bindestrich
    # anhaengt („landspokalen"), faellt weiterhin durch — bewusst: `pokal` mitten im Wort zu
    # suchen wuerde irgendwann einen Vereinsnamen zum Pokal machen. Taucht so ein Slug im
    # Ledger auf, meldet ihn der Wachhund, und DANN wird entschieden.
    assert LS.stufe("landspokalen") is None
    # Gegenprobe: die breitere Regel darf keine Spielklasse verschlucken.
    for liga, ebene in (("premium-liiga", "1"), ("allsvenskan", "1"), ("superettan", "2"),
                        ("ekstraklasa", "1"), ("la-liga-2", "2")):
        assert LS.stufe(liga) == ebene, liga


def test_estland_und_georgien_stehen_in_der_tabelle():
    """Zwei reine Nachtraege — die Slugs tragen nichts, woraus eine Regel etwas ableiten koennte.
    „esiliiga" ist Estlands ZWEITE Klasse; die oberste steht seit jeher als „premium-liiga"
    (Sponsorname der Meistriliiga) da. Ohne diese Zeile waere ausgerechnet die Liga darunter die
    einzige ohne Ebene."""
    assert LS.stufe("erovnuli-liga") == "1"
    assert LS.stufe("esiliiga") == "2"
    assert LS.stufe("premium-liiga") == "1"


# ── 11.09.2026: der Wachhund, sechster und siebter Slug ──────────────────────
def test_aufstiegsligen_stehen_in_der_tabelle_nicht_in_einer_regel():
    """„ascenso" und „promotion" im Namen sagen nichts ueber den Rang: in Mexiko ist die „Liga de
    Ascenso" die zweite Klasse, anderswo steht dasselbe Wort im Namen der obersten. Die Schweizer
    Promotion League ist die DRITTE Klasse (Super League 1, Challenge League 2 stehen schon oben).
    Ein Muster waere in der Haelfte der Faelle falsch — deshalb Tabelle."""
    assert LS.stufe("liga-nacional-de-ascenso") == "2"
    assert LS.stufe("promotion-league") == "3"
    # Gegenprobe: die schon eingestuften Schweizer Klassen bleiben, wo sie sind.
    assert LS.stufe("challenge-league") == "2"


# ── 12.09.2026: der Wachhund, achter und neunter Slug ────────────────────────
def test_eine_regionalgruppe_erbt_die_ebene_ihrer_liga():
    """Zum zweiten Mal fiel eine GRUPPE derselben Liga durch: `tercera-division-group-7` stand
    von Hand in der Tabelle, `-group-4` nicht — und die spanische Tercera hat achtzehn Gruppen.
    Eine Zeile je Gruppe ist die Instanz. Die Klasse ist: eine Regionalstaffel IST ihre Liga,
    das sagt der Slug selbst, dafuer braucht es kein Wissen."""
    assert LS.stufe("tercera-division-group-4") == "3"
    assert LS.stufe("tercera-division-group-11") == "3", "auch zweistellig"
    assert LS.stufe("serie-c-group-d") == "3", "Buchstaben-Staffeln genauso"


def test_eine_gruppennummer_macht_eine_unbekannte_liga_nicht_bekannt():
    """Die Grenze der Regel: sie liest den Rumpf, sie raet ihn nicht. Ohne Rumpf in der Tabelle
    bleibt None — sonst waere „irgendwas-group-2" stillschweigend eine Spielklasse."""
    assert LS.stufe("voellig-unbekannte-liga-group-2") is None
    assert LS.stufe("group-3") is None


def test_tabelle_und_gruppenregel_widersprechen_sich_nicht():
    """Die von Hand eingetragenen Gruppen bleiben drin (schneller Weg), muessen aber dasselbe
    sagen wie die Regel — sonst haengt die Antwort davon ab, welcher Weg zuerst greift."""
    widerspruch = []
    for slug, ebene in LS.EBENE.items():
        if "-group-" not in slug:
            continue
        rumpf = slug.rsplit("-group-", 1)[0]
        aus_regel = LS.EBENE.get(rumpf)
        if aus_regel and aus_regel != ebene:
            widerspruch.append(f"{slug}={ebene} vs. {rumpf}={aus_regel}")
    assert not widerspruch, "Tabelle und Regel sagen Verschiedenes: %s" % widerspruch


def test_philippinen_sind_die_oberste_klasse():
    """Der Slug kommt abgekuerzt („footb.") aus dem Feed und sieht nach Amateurstaffel aus.
    Die Philippines Football League ist die oberste Klasse des Landes — das ist Wissen und
    gehoert deshalb in die Tabelle, nicht in eine Regel."""
    assert LS.stufe("philippines-footb-league") == "1"
    assert LS.stufe("philippines-footb-league", "basketball") is None


# ── 13.09.2026: der Wachhund, zehnter und elfter Slug ────────────────────────
def test_generische_divisionsnamen_kommen_aus_der_paarung_nicht_aus_der_zahl():
    """„Division 2" ist in Hongkong die DRITTE Klasse (unter Premier League und First Division),
    während „Jordan 1st Division" die zweite ist. Eine Regel „division-N → Ebene N" wäre in
    beiden Fällen falsch — deshalb Tabelle, mit der Paarung als Beleg."""
    assert LS.stufe("division-2") == "3"
    assert LS.stufe("division-1") == "3"
    assert LS.stufe("jordan-1st-division") == "3"


def test_panama_ist_die_oberste_klasse():
    """Apertura ist die Halbsaison, kein Rang."""
    assert LS.stufe("liga-panamena-de-futbol-apertura") == "1"
    assert LS.stufe("liga-panamena-de-futbol-apertura", "basketball") is None
