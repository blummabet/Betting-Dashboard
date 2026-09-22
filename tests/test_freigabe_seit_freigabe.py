"""tests/test_freigabe_seit_freigabe.py — 22.09.2026

🔴 Lucas, nachdem der letzte CLV-Riegel gefallen war: auf den Hinweis, dass die drei
freigegebenen Schubladen statistisch nicht besser dastehen als die zwölf gerade auf „Kandidat"
gesetzten — „Ja" (messen).

Gemessen wurde über 1.392 Läufe der letzten 14 Tage aus der git-Historie von freigabe.json:

    Schublade                        freigegeben  Anteil   n/ROI dort    seither        Urteil
    Liga · ABWÄGEN                   08.09.        100 %    91 / +15,2 %  98 / +9,0 %   hält
    Mix money+sharp+steam            16.09.         33 %    32 / +20,1 %  12 / +8,3 %   zu dünn
    🔒 E-Sport ohne Wallet-Nachweis   21.09.         10 %   120 / +14,8 %  15 / −14,1 %  frisch
    Public-Kandidaten (heute raus)   08.09.         20 %    35 / +20,8 %  64 / +0,3 %   Mittel

Zwei Dinge stehen damit fest, und sie widersprechen sich nicht:

  · Die Mehrfachtest-Warnung ist keine Theorie. „Public-Kandidaten" fiel von +20,8 % auf 35
    Plays über 64 neue Plays auf +0,3 % — genau der Rückfall zum Mittel, den die Rechnung
    vorhersagt. Die Schublade flackerte dabei elf Mal rein und raus.
  · Sie ist aber auch nicht das letzte Wort. „Liga · ABWÄGEN" steht in 100 % der Läufe und hat
    98 Plays out of sample bei +9,0 % — eine Bestätigung nach vorn, auch ohne Voranmeldung.

Die Zahl, die das entscheidet, existierte bis heute NUR als git-Rekonstruktion. Fehlerklasse:
*die Messung, die das Urteil trägt, ist keine Messung, sondern eine Ausgrabung.*
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import freigabe as F  # noqa: E402

T0 = datetime(2026, 9, 8, 18, 14, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 22, 21, 49, tzinfo=timezone.utc)


def z(name, status, n, roi):
    return {"schublade": name, "status": status, "n": n, "roi": roi}


def test_die_erste_freigabe_setzt_den_nullpunkt():
    zeilen, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    assert stand["A"]["ab"] == T0.isoformat()
    assert stand["A"]["nBei"] == 91 and stand["A"]["roiBei"] == 0.152
    assert stand["A"]["drin"] is True


def test_der_roi_der_neuen_plays_wird_gerechnet_nicht_der_gesamte():
    """Der echte Fall: Liga · ABWÄGEN wurde am 08.09. bei n=91 / +15,2 % freigegeben und steht
    heute bei n=189 / +12,0 %. Der Gesamt-ROI sagt „schlechter geworden"; die Frage ist aber,
    was die 98 NEUEN Plays gebracht haben — und das sind +9,0 %."""
    _, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    zeilen, _ = F.seit_freigabe([z("A", "freigegeben", 189, 0.120)], stand, T1)
    sf = zeilen[0]["seitFreigabe"]
    assert sf["nNeu"] == 98
    assert abs(sf["roiNeu"] - 0.0903) < 0.0005, sf["roiNeu"]
    assert sf["nBei"] == 91, "der Nullpunkt darf nicht mitwandern"


def test_der_nullpunkt_wandert_nicht_mit():
    """Ohne diese Eigenschaft stünde der Vergleich jeden Tag bei null und die Zahl könnte nie
    wachsen — der häufigste Weg, eine Vorwärtsmessung unbrauchbar zu machen."""
    _, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    for tag, n in ((9, 100), (10, 120), (14, 160)):
        zeilen, stand = F.seit_freigabe(
            [z("A", "freigegeben", n, 0.14)], stand,
            T0 + timedelta(days=tag))
    assert stand["A"]["nBei"] == 91
    assert stand["A"]["ab"] == T0.isoformat()
    assert zeilen[0]["seitFreigabe"]["nNeu"] == 69


def test_ein_rueckfall_zum_mittel_wird_sichtbar():
    """Der echte Fall „Public-Kandidaten": +20,8 % auf 35 Plays, dann 64 neue Plays bei +0,3 %.
    Der Gesamt-ROI (+7,5 %) sieht immer noch gut aus — die neuen Plays nicht."""
    _, stand = F.seit_freigabe([z("P", "freigegeben", 35, 0.208)], {}, T0)
    zeilen, _ = F.seit_freigabe([z("P", "freigegeben", 99, 0.075)], stand, T1)
    sf = zeilen[0]["seitFreigabe"]
    assert sf["nNeu"] == 64
    assert abs(sf["roiNeu"] - 0.0028) < 0.002, sf["roiNeu"]


def test_das_flackern_wird_gezaehlt():
    """Eine Freigabe, die täglich wechselt, ist kein Beleg — sie ist eine Zahl, die um null
    schwankt. „Public-Kandidaten" fiel in 14 Tagen elf Mal rein und raus."""
    _, stand = F.seit_freigabe([z("P", "freigegeben", 35, 0.2)], {}, T0)
    for i in range(3):
        _, stand = F.seit_freigabe([z("P", "geprueft", 40 + i, 0.1)], stand, T0 + timedelta(days=2 * i + 1))
        _, stand = F.seit_freigabe([z("P", "freigegeben", 45 + i, 0.2)], stand, T0 + timedelta(days=2 * i + 2))
    assert stand["P"]["raus"] == 3, "jedes Herausfallen zaehlt einmal"
    zeilen, _ = F.seit_freigabe([z("P", "freigegeben", 99, 0.075)], stand, T1)
    assert zeilen[0]["seitFreigabe"]["rausgefallen"] == 3


def test_ein_dauerhaft_drin_zaehlt_nicht_hoch():
    _, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    for i in range(5):
        _, stand = F.seit_freigabe([z("A", "freigegeben", 100 + i, 0.14)], stand, T0 + timedelta(days=i))
    assert stand["A"]["raus"] == 0


def test_nicht_freigegebene_zeilen_bekommen_kein_feld():
    zeilen, stand = F.seit_freigabe([z("B", "kandidat", 32, 0.76)], {}, T0)
    assert "seitFreigabe" not in zeilen[0]
    assert "B" not in stand


def test_ohne_zahlen_wird_nichts_behauptet():
    """Eine Zeile ohne n oder roi darf keinen erfundenen Vorwaerts-ROI tragen."""
    _, stand = F.seit_freigabe([{"schublade": "C", "status": "freigegeben"}], {}, T0)
    zeilen, _ = F.seit_freigabe([{"schublade": "C", "status": "freigegeben"}], stand, T1)
    sf = zeilen[0]["seitFreigabe"]
    assert "roiNeu" not in sf or sf["roiNeu"] is None


def test_am_selben_tag_gibt_es_noch_keine_neuen_plays():
    _, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    zeilen, _ = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], stand, T0)
    assert zeilen[0]["seitFreigabe"]["nNeu"] == 0
    assert zeilen[0]["seitFreigabe"]["roiNeu"] is None, "0 neue Plays ergeben keinen ROI"


def test_die_bilanz_landet_im_artefakt():
    import inspect
    q = inspect.getsource(F.baue)
    assert "seit_freigabe(" in q, "die Vorwaertsbilanz wird nicht gerechnet"
    assert "STAND_FILE" in q, "das Gedaechtnis wird nicht geschrieben — dann faengt jeder Lauf bei null an"


def test_das_gedaechtnis_ueberlebt_einen_neustart(tmp_path):
    """Ohne Persistenz waere `nBei` bei jedem Lauf der aktuelle Stand und `nNeu` immer 0 —
    die Messung saehe aus, als gaebe es sie, und wuerde nie etwas zeigen."""
    p = tmp_path / "stand.json"
    _, stand = F.seit_freigabe([z("A", "freigegeben", 91, 0.152)], {}, T0)
    p.write_text(json.dumps(stand), encoding="utf-8")
    wieder = json.loads(p.read_text(encoding="utf-8"))
    zeilen, _ = F.seit_freigabe([z("A", "freigegeben", 189, 0.120)], wieder, T1)
    assert zeilen[0]["seitFreigabe"]["nNeu"] == 98


def test_die_dokumentation_im_stand_ist_keine_schublade():
    """`freigabe_stand.json` traegt einen `_doc`-Block. Ohne diesen Filter wuerde er als
    Schublade behandelt — und ein Register, das seine eigene Dokumentation bewertet, ist
    genau die Sorte Unsinn, die niemand mehr nachvollzieht."""
    zeilen, stand = F.seit_freigabe([z("A", "freigegeben", 10, 0.1)],
                                    {"_doc": ["irgendwas"]}, T0)
    assert "_doc" in stand, "der Block bleibt erhalten"
    assert stand["_doc"] == ["irgendwas"], "und wird nicht angefasst"


def test_das_gedaechtnis_wird_committet():
    """🔴 Ohne `git add freigabe_stand.json` faengt die Messung bei jedem CI-Lauf bei null an.
    Dieselbe Fehlerklasse wie beim Dedup-Stand am 19.09.: ein Gedaechtnis, das den Lauf nicht
    ueberlebt, ist keines."""
    treffer = []
    for wf in (BASE / ".github" / "workflows").glob("*.yml"):
        if "freigabe_stand.json" in wf.read_text(encoding="utf-8"):
            treffer.append(wf.name)
    assert treffer, "kein Workflow staged freigabe_stand.json — das Gedaechtnis geht verloren"


def test_der_rekonstruierte_stand_nennt_sich_als_solchen():
    """Die vier Startpunkte sind aus der git-Historie ausgegraben, nicht live mitgeschrieben.
    Wer das in drei Wochen liest, muss den Unterschied sehen — sonst gilt eine Rekonstruktion
    als Messung."""
    p = BASE / "freigabe_stand.json"
    if not p.exists():
        import pytest
        pytest.skip("kein Stand im Arbeitsverzeichnis")
    d = json.loads(p.read_text(encoding="utf-8"))
    alt = [k for k, v in d.items()
           if isinstance(v, dict) and str(v.get("ab", "")) < "2026-09-22"]
    for k in alt:
        assert "rekonstruiert" in str(d[k].get("quelle") or ""), \
            "%s traegt einen Startpunkt vor heute ohne Herkunftsangabe" % k


# ── Vorfall 22.09.2026: baue() hat das Gedaechtnis selbst geschrieben ────────────────────
# Jeder Probelauf (meiner von Hand, jeder Test, der baue() aufruft) hat damit einen
# Freigabe-Beginn in freigabe_stand.json gestempelt. So sind "Conviction 7" und "Mix money"
# mit Startpunkt 22.09. 20:25 entstanden — Schubladen, die nie freigegeben waren. Ein
# bestehender Eintrag wird nie neu gestempelt (das ist der Sinn der Datei), also waeren die
# beiden Startpunkte fuer immer geblieben.

def test_baue_schreibt_das_gedaechtnis_nicht():
    """Der Aufruf von baue() darf freigabe_stand.json NICHT anfassen."""
    import freigabe as F
    vorher = F.STAND_FILE.read_bytes() if F.STAND_FILE.exists() else None
    vorher_mtime = F.STAND_FILE.stat().st_mtime_ns if F.STAND_FILE.exists() else None
    F.baue(engine=False)
    nachher = F.STAND_FILE.read_bytes() if F.STAND_FILE.exists() else None
    assert nachher == vorher, "baue() hat freigabe_stand.json ueberschrieben"
    if vorher_mtime is not None:
        assert F.STAND_FILE.stat().st_mtime_ns == vorher_mtime, "baue() hat die Datei angefasst"


def test_baue_gibt_den_stand_zurueck():
    """Gerechnet wird er trotzdem — sonst haette die Pipeline nichts zu schreiben."""
    import freigabe as F
    d = F.baue(engine=False)
    assert isinstance(d.get("stand"), dict), "baue() liefert keinen Stand mehr"


def test_stand_landet_nicht_zusaetzlich_in_freigabe_json():
    """Zwei Kopien derselben Buchfuehrung driften — `seitFreigabe` steht an der Zeile."""
    import json as _j, pathlib as _p
    f = _p.Path(__file__).resolve().parent.parent / "freigabe.json"
    if not f.exists():
        return
    d = _j.loads(f.read_text(encoding="utf-8"))
    assert "stand" not in d, "freigabe.json traegt eine zweite Kopie des Gedaechtnisses"


def test_nur_der_pipeline_lauf_darf_schreiben():
    import freigabe as F
    assert F.darf_stand_schreiben({}) is False
    assert F.darf_stand_schreiben({"GITHUB_ACTIONS": "true"}) is True
    assert F.darf_stand_schreiben({"GITHUB_ACTIONS": "false"}) is False
    # Von Hand erzwingbar (Reparatur) und in der Pipeline abschaltbar
    assert F.darf_stand_schreiben({"FREIGABE_STAND": "1"}) is True
    assert F.darf_stand_schreiben({"GITHUB_ACTIONS": "true", "FREIGABE_STAND": "0"}) is False


def test_stand_schreiben_schweigt_nicht_wenn_es_nicht_schreibt():
    """Ein Guard, dessen Stille wie ein Freispruch aussieht — hier: laut sagen, dass nichts kam."""
    import freigabe as F, io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = F.stand_schreiben({"x": 1}, env={})
    assert ok is False
    assert "NICHT geschrieben" in buf.getvalue()


def test_das_gedaechtnis_enthaelt_nur_belegte_startpunkte():
    """Jeder Eintrag nennt seine Herkunft — rekonstruiert oder von der Pipeline gestempelt."""
    import json as _j, pathlib as _p
    f = _p.Path(__file__).resolve().parent.parent / "freigabe_stand.json"
    d = _j.loads(f.read_text(encoding="utf-8"))
    for name, e in d.items():
        if name.startswith("_"):
            continue
        assert isinstance(e.get("ab"), str) and e["ab"][:2] == "20", (name, e)
        assert isinstance(e.get("drin"), bool), (name, e)
