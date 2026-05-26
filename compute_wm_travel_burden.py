#!/usr/bin/env python3
"""
compute_wm_travel_burden.py
Liest wm2026-data.json, berechnet für jedes Team:
  - Venues aller 3 Gruppenspiele
  - Distanz (km) + Ruhetage zwischen den Spielen
  - Border Crossings (USA / Kanada / Mexiko)
  - Burden Score 0-10 + Label
Output: wm_travel_burden.json
"""
import json, math, os
from datetime import date

# ── Haversine ──────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

# ── All 16 confirmed WM 2026 venues ───────────────────────────────────────
VENUES = {
    # Mexico
    'estadio azteca':         {'city':'Mexico City',   'country':'Mexiko', 'flag':'🇲🇽', 'lat':19.303,  'lon':-99.151,  'alt':2200, 'temp':18, 'hum':55, 'type':'outdoor'},
    'estadio akron':          {'city':'Guadalajara',   'country':'Mexiko', 'flag':'🇲🇽', 'lat':20.687,  'lon':-103.467, 'alt':1566, 'temp':25, 'hum':68, 'type':'outdoor'},
    'estadio bbva':           {'city':'Monterrey',     'country':'Mexiko', 'flag':'🇲🇽', 'lat':25.669,  'lon':-100.312, 'alt':540,  'temp':36, 'hum':45, 'type':'outdoor'},
    # Canada
    'bc place':               {'city':'Vancouver',     'country':'Kanada', 'flag':'🇨🇦', 'lat':49.277,  'lon':-123.112, 'alt':5,    'temp':22, 'hum':60, 'type':'dome'},
    'bmo field':              {'city':'Toronto',       'country':'Kanada', 'flag':'🇨🇦', 'lat':43.633,  'lon':-79.419,  'alt':76,   'temp':28, 'hum':65, 'type':'outdoor'},
    # USA
    'metlife stadium':        {'city':'New York',      'country':'USA',    'flag':'🇺🇸', 'lat':40.813,  'lon':-74.074,  'alt':10,   'temp':27, 'hum':62, 'type':'outdoor'},
    "at&t stadium":           {'city':'Dallas',        'country':'USA',    'flag':'🇺🇸', 'lat':32.748,  'lon':-97.093,  'alt':170,  'temp':22, 'hum':50, 'type':'dome'},
    'sofi stadium':           {'city':'Los Angeles',   'country':'USA',    'flag':'🇺🇸', 'lat':33.953,  'lon':-118.339, 'alt':55,   'temp':27, 'hum':55, 'type':'open-roof'},
    'hard rock stadium':      {'city':'Miami',         'country':'USA',    'flag':'🇺🇸', 'lat':25.958,  'lon':-80.239,  'alt':2,    'temp':33, 'hum':76, 'type':'outdoor'},
    "levi's stadium":         {'city':'San Francisco', 'country':'USA',    'flag':'🇺🇸', 'lat':37.403,  'lon':-121.970, 'alt':10,   'temp':23, 'hum':55, 'type':'outdoor'},
    'arrowhead stadium':      {'city':'Kansas City',   'country':'USA',    'flag':'🇺🇸', 'lat':39.049,  'lon':-94.484,  'alt':320,  'temp':33, 'hum':62, 'type':'outdoor'},
    'nrg stadium':            {'city':'Houston',       'country':'USA',    'flag':'🇺🇸', 'lat':29.685,  'lon':-95.411,  'alt':15,   'temp':22, 'hum':50, 'type':'dome'},
    'lumen field':            {'city':'Seattle',       'country':'USA',    'flag':'🇺🇸', 'lat':47.595,  'lon':-122.332, 'alt':20,   'temp':23, 'hum':65, 'type':'outdoor'},
    'gillette stadium':       {'city':'Boston',        'country':'USA',    'flag':'🇺🇸', 'lat':42.091,  'lon':-71.264,  'alt':10,   'temp':26, 'hum':60, 'type':'outdoor'},
    'lincoln financial field':{'city':'Philadelphia',  'country':'USA',    'flag':'🇺🇸', 'lat':39.901,  'lon':-75.168,  'alt':10,   'temp':28, 'hum':64, 'type':'outdoor'},
    # ── Previously missing venues ──────────────────────────────────────────
    'mercedes-benz stadium':  {'city':'Atlanta',       'country':'USA',    'flag':'🇺🇸', 'lat':33.755,  'lon':-84.401,  'alt':309,  'temp':31, 'hum':68, 'type':'dome'},
    'empower field':          {'city':'Denver',        'country':'USA',    'flag':'🇺🇸', 'lat':39.744,  'lon':-105.020, 'alt':1609, 'temp':29, 'hum':38, 'type':'outdoor'},  # ← 1609m!
    'camping world stadium':  {'city':'Orlando',       'country':'USA',    'flag':'🇺🇸', 'lat':28.540,  'lon':-81.403,  'alt':29,   'temp':34, 'hum':72, 'type':'outdoor'},
    'rose bowl':              {'city':'Los Angeles',   'country':'USA',    'flag':'🇺🇸', 'lat':34.162,  'lon':-118.168, 'alt':260,  'temp':30, 'hum':52, 'type':'outdoor'},
}

# Additional aliases for fuzzy matching
ALIASES = {
    'azteca': 'estadio azteca', 'mexico city': 'estadio azteca',
    'akron': 'estadio akron', 'guadalajara': 'estadio akron',
    'bbva': 'estadio bbva', 'monterrey': 'estadio bbva',
    'bc place': 'bc place', 'vancouver': 'bc place',
    'bmo': 'bmo field', 'toronto': 'bmo field',
    'metlife': 'metlife stadium', 'new york': 'metlife stadium', 'new jersey': 'metlife stadium',
    'att stadium': 'at&t stadium', 'dallas': 'at&t stadium',
    'sofi': 'sofi stadium', 'los angeles': 'sofi stadium',
    'hard rock': 'hard rock stadium', 'miami': 'hard rock stadium',
    'levis': "levi's stadium", 'san francisco': "levi's stadium", 'santa clara': "levi's stadium",
    'arrowhead': 'arrowhead stadium', 'kansas city': 'arrowhead stadium',
    'nrg': 'nrg stadium', 'houston': 'nrg stadium',
    'lumen': 'lumen field', 'seattle': 'lumen field',
    'gillette': 'gillette stadium', 'boston': 'gillette stadium', 'foxborough': 'gillette stadium',
    'lincoln financial': 'lincoln financial field', 'philadelphia': 'lincoln financial field',
    'mercedes': 'mercedes-benz stadium', 'mercedes-benz': 'mercedes-benz stadium', 'atlanta': 'mercedes-benz stadium',
    'empower': 'empower field', 'denver': 'empower field', 'mile high': 'empower field',
    'camping world': 'camping world stadium', 'orlando': 'camping world stadium',
    'rose bowl': 'rose bowl', 'pasadena': 'rose bowl',
}

def lookup(venue_str):
    if not venue_str: return None
    # "Estadio Azteca, Mexico City" → try full name first, then first part
    raw = venue_str.lower().strip()
    k   = raw.split(',')[0].strip()
    if k in VENUES: return {**VENUES[k], 'name': venue_str.split(',')[0].strip()}
    if k in ALIASES and ALIASES[k] in VENUES:
        return {**VENUES[ALIASES[k]], 'name': venue_str.split(',')[0].strip()}
    for alias, canonical in ALIASES.items():
        if alias in k and canonical in VENUES:
            return {**VENUES[canonical], 'name': venue_str.split(',')[0].strip()}
    for canon_key, v in VENUES.items():
        if canon_key in k or k in canon_key:
            return {**v, 'name': venue_str.split(',')[0].strip()}
    return None

# ── Load schedule ─────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, 'wm2026-data.json')) as f:
    data = json.load(f)

team_games = {}
team_meta  = {}

for gk, gv in data['groups'].items():
    for t in gv.get('teams', []):
        team_meta[t['id']] = {'name': t['name'], 'flag': t.get('flag',''), 'group': gk}
    for fx in gv.get('fixtures', []):
        for side in ['home', 'away']:
            tid = fx[side]
            if tid not in team_games: team_games[tid] = []
            v = lookup(fx.get('venue', ''))
            team_games[tid].append({
                'matchday':  fx['matchday'],
                'date':      fx['date'],
                'venue_str': fx.get('venue', ''),
                'venue':     v,
                'opponent':  fx['away'] if side == 'home' else fx['home'],
            })

for tid in team_games:
    team_games[tid].sort(key=lambda x: (x['date'], x['matchday']))

# ── Compute burden ────────────────────────────────────────────────────────
output = {}

for tid, games in team_games.items():
    meta = team_meta.get(tid, {})
    legs = []

    for i in range(1, len(games)):
        g0, g1 = games[i-1], games[i]
        v0, v1 = g0['venue'], g1['venue']
        if not v0 or not v1:
            legs.append({'error': f'venue missing: {g0["venue_str"]} or {g1["venue_str"]}'})
            continue

        km         = haversine(v0['lat'], v0['lon'], v1['lat'], v1['lon'])
        d0         = date.fromisoformat(g0['date'])
        d1         = date.fromisoformat(g1['date'])
        rest_days  = (d1 - d0).days - 1
        crossing   = v0['country'] != v1['country']
        same_venue = km < 50  # within 50km = same city

        # Climate shift penalty: if altitude changes significantly
        alt_shift = abs(v1.get('alt',0) - v0.get('alt',0))

        if same_venue:
            burden = 'none'
        elif km >= 3500 or (km >= 2500 and rest_days <= 3):
            burden = 'critical'
        elif km >= 2000 or (km >= 1200 and rest_days <= 3) or (crossing and km >= 800):
            burden = 'significant'
        elif km >= 700 or crossing:
            burden = 'moderate'
        else:
            burden = 'low'

        legs.append({
            'matchday_from': g0['matchday'],
            'matchday_to':   g1['matchday'],
            'from_city':     v0['city'],
            'from_country':  v0['country'],
            'from_venue':    v0.get('name', v0['city']),
            'to_city':       v1['city'],
            'to_country':    v1['country'],
            'to_venue':      v1.get('name', v1['city']),
            'km':            km,
            'rest_days':     rest_days,
            'border_crossing': crossing,
            'same_venue':    same_venue,
            'alt_shift':     alt_shift,
            'burden':        burden,
        })

    valid_legs  = [l for l in legs if 'error' not in l]
    errors      = [l['error'] for l in legs if 'error' in l]
    total_km    = sum(l['km'] for l in valid_legs)
    max_km      = max((l['km'] for l in valid_legs), default=0)
    crossings   = sum(1 for l in valid_legs if l['border_crossing'])
    n_critical  = sum(1 for l in valid_legs if l['burden'] == 'critical')
    n_signif    = sum(1 for l in valid_legs if l['burden'] == 'significant')
    n_moderate  = sum(1 for l in valid_legs if l['burden'] == 'moderate')
    min_rest    = min((l['rest_days'] for l in valid_legs), default=99)

    # Score 0-10
    score = min(10, round(
        (total_km / 600) +
        (crossings * 1.5) +
        (n_critical * 3.0) +
        (n_signif  * 1.5) +
        (n_moderate * 0.5) +
        (max(0, 3 - min_rest) * 0.5)
    ))

    if score >= 7:   label = 'Extrem'
    elif score >= 5: label = 'Schwer'
    elif score >= 3: label = 'Moderat'
    elif score >= 1: label = 'Leicht'
    else:            label = 'Kein'

    worst = max(valid_legs, key=lambda l: l['km']) if valid_legs else None

    output[tid] = {
        'id':              tid,
        'name':            meta.get('name', ''),
        'flag':            meta.get('flag', ''),
        'group':           meta.get('group', ''),
        'games': [{
            'matchday': g['matchday'],
            'date':     g['date'],
            'venue':    g['venue_str'],
            'city':     g['venue']['city'] if g['venue'] else '',
            'country':  g['venue']['country'] if g['venue'] else '',
            'alt':      g['venue'].get('alt', 0) if g['venue'] else 0,
        } for g in games],
        'legs':            valid_legs,
        'total_km':        total_km,
        'max_km':          max_km,
        'min_rest_days':   min_rest if valid_legs else 99,
        'border_crossings': crossings,
        'burden_score':    score,
        'burden_label':    label,
        'worst_leg':       worst,
        'errors':          errors,
    }

# ── Write output ──────────────────────────────────────────────────────────
out_path = os.path.join(BASE, 'wm_travel_burden.json')
with open(out_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# ── Summary print ─────────────────────────────────────────────────────────
ranked = sorted(output.values(), key=lambda x: -x['burden_score'])
print(f"{'Fl':<4} {'Team':<20} {'Gr':<4} {'Sc':<4} {'Label':<10} {'Total':<7} {'Max':<7} {'X':<3} {'RestMin'}")
print("-" * 80)
for r in ranked:
    print(f"{r['flag']:<4} {r['name']:<20} {r['group']:<4} {r['burden_score']:<4} {r['burden_label']:<10} {r['total_km']:<7} {r['max_km']:<7} {r['border_crossings']:<3} {r['min_rest_days']}")
    if r['errors']:
        print(f"   ⚠️  {r['errors']}")

print(f"\n✅ Written: {out_path}")
print(f"   {len(output)} teams processed")
print(f"   Missing venues: {sum(1 for r in output.values() if r['errors'])} teams affected")
