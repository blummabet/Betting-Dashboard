#!/usr/bin/env python3
"""fetch_wm_squads.py v2 — WM 2026 Squad Spotlight"""
import json, os, sys, time, http.client
from pathlib import Path

BASE = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2
MAX_PAGES = 6
FORCE = "--force" in sys.argv

APIF_NAME_OVERRIDE = {
    "ARG":"Argentina","AUS":"Australia","AUT":"Austria","BEL":"Belgium",
    "BIH":"Bosnia","BRA":"Brazil","CAN":"Canada","CIV":"Ivory Coast",
    "COD":"Congo DR","COL":"Colombia","CPV":"Cape Verde","CRO":"Croatia",
    "CUW":"Curacao","CZE":"Czech Republic","DZA":"Algeria","ECU":"Ecuador",
    "EGY":"Egypt","ENG":"England","ESP":"Spain","FRA":"France",
    "GER":"Germany","GHA":"Ghana","HTI":"Haiti","IRN":"Iran","IRQ":"Iraq",
    "JOR":"Jordan","JPN":"Japan","KOR":"South Korea","MAR":"Morocco",
    "MEX":"Mexico","NED":"Netherlands","NOR":"Norway","NZL":"New Zealand",
    "PAN":"Panama","POR":"Portugal","PRY":"Paraguay","QAT":"Qatar",
    "SAU":"Saudi Arabia","SCO":"Scotland","SEN":"Senegal","SUI":"Switzerland",
    "SWE":"Sweden","TUN":"Tunisia","TUR":"Türkiye","URU":"Uruguay",
    "USA":"United States","UZB":"Uzbekistan","ZAF":"South Africa",
}

def apif_get(endpoint, params):
    if not APIF_KEY: return [], 0
    q = "&".join(f"{k}={v}" for k,v in params.items())
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", f"/{endpoint}?{q}", headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        return data.get("response",[]), data.get("paging",{}).get("total",1)
    except Exception as e:
        print(f"  ERR {endpoint}: {e}"); return [], 0

def normalize(s):
    return s.lower().strip().replace("é","e").replace("ü","u").replace("ô","o").replace("ö","o")

def match_team(our_id, teams):
    target = normalize(APIF_NAME_OVERRIDE.get(our_id, our_id))
    for t in teams:
        n = normalize(t.get("team",{}).get("name",""))
        if n == target or target in n or n in target: return t
    return None

def best_attacker(players):
    cands = []
    for p in players:
        s = (p.get("statistics") or [{}])[0]
        pos = (s.get("games",{}).get("position") or "").upper()
        if pos == "GOALKEEPER": continue
        g = s.get("goals",{}).get("total") or 0
        a = s.get("goals",{}).get("assists") or 0
        sh = s.get("shots",{}).get("total") or 0
        m = s.get("games",{}).get("minutes") or 0
        if g == 0 and a == 0 and m < 60: continue
        sc = g*6 + a*3 + sh*0.2 + (8 if pos=="ATTACKER" else 2 if pos=="MIDFIELDER" else 0)
        cands.append({"name":p["player"].get("name","?"),"position":pos,"goals":g,"assists":a,"minutes":m,"sc":sc})
    if not cands: return None
    cands.sort(key=lambda x:-x["sc"])
    best = cands[0]
    lbl = {"ATTACKER":"ST","MIDFIELDER":"CAM","DEFENDER":"DEF"}.get(best["position"],best["position"])
    return {"name":best["name"],"position":lbl,"goals":best["goals"],"assists":best["assists"],"minutes":best["minutes"]}

def main():
    print(f"fetch_wm_squads.py v2  key={'set' if APIF_KEY else 'MISSING'}  force={FORCE}")
    if not APIF_KEY: sys.exit(0)
    with open(WM_FILE) as f: wm = json.load(f)
    squads = {} if FORCE else (wm.get("squads") or {})
    ids = sorted(t["id"] for g in wm["groups"].values() for t in g["teams"])
    time.sleep(APIF_DELAY)
    apif_teams, _ = apif_get("teams", {"league":1,"season":2026})
    print(f"API teams: {len(apif_teams)}")
    found = skipped = 0
    for tid in ids:
        if not FORCE and squads.get(tid,{}).get("name"):
            skipped += 1; continue
        entry = match_team(tid, apif_teams)
        if not entry:
            print(f"  NOMATCH {tid}"); continue
        aid = entry["team"]["id"]
        all_p = []
        for season in (2026,2025,2024):
            for pg in range(1,MAX_PAGES+1):
                time.sleep(APIF_DELAY)
                pl, tp = apif_get("players", {"team":aid,"season":season,"page":pg})
                all_p.extend(pl)
                if not pl or pg >= tp: break
            if all_p: break
        best = best_attacker(all_p) if all_p else None
        if best:
            squads[tid] = best
            print(f"  {tid}: {best['name']} {best['goals']}G {best['assists']}A")
            found += 1
    wm["squads"] = squads
    with open(WM_FILE,"w") as f: json.dump(wm, f, ensure_ascii=False, indent=2)
    print(f"Done: {found} fetched, {skipped} skipped, total {len(squads)}/48")

if __name__ == "__main__": main()
