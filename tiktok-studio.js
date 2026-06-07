/*
 * tiktok-studio.js — Manueller Card-Generator
 * ─────────────────────────────────────────────────────────────────────
 * Refactor-konform (06.06.2026 Standards):
 *   · Config:    studio_config.json    (Layout, Theme, Defaults — Profile-aware)
 *   · Pools:     studio_pools.json     (Hooks, Stats-Templates, Vergleiche)
 *   · Templates: studio_templates/*.html (HTML mit {{var}} Placeholders)
 *
 * Strikte Trennung zum Daily-Cron — Studio ist standalone, ändert hier
 * kaputt nichts an tiktok_card_templates.py oder generate_daily_tiktok.py.
 *
 * Liga-Switch: studio_config.json + studio_pools.json profiles.active wechseln.
 * Subject-Auswahl (Teams/Players) wird durch Profile gefiltert.
 */

(function(){
  'use strict';

  // ─────────────────────────────────────────────────────────────────────
  // Hilfen
  // ─────────────────────────────────────────────────────────────────────
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $$(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }

  // ─────────────────────────────────────────────────────────────────────
  // External Data (geladen via fetch in init)
  // ─────────────────────────────────────────────────────────────────────
  let CONFIG = null;        // studio_config.json
  let POOLS = null;         // studio_pools.json
  let TEMPLATE_HTML = {};   // {team_hook: "<style>...</style><div>...", ...}
  let COMMON_CSS = '';      // _common.css contents
  let WM_DATA = null;
  let PLAYER_DATA = null;
  let POLY_DATA = null;
  let ACTIVE_PROFILE = 'wm2026';

  const TEMPLATE_FILES = {
    team_hook:    {file: 'team_hook.html',    label: '🔥 Team Hook',          desc: 'Hook-Statement + Killer-Stat über einem Team'},
    player:       {file: 'player.html',       label: '⭐ Player Spotlight',    desc: 'Spieler + Killer-Linie aus Squad-Daten'},
    bizarre:      {file: 'bizarre.html',      label: '🤯 Bizarre Compare',     desc: '3 schiefe Vergleiche zu einer Quote'},
    match_pick:   {file: 'match_pick.html',   label: '🎯 Match Pick',          desc: 'Bester Pick zu einem Match'},
    killer_stat:  {file: 'killer_stat.html',  label: '💥 Killer Stat',         desc: 'Team + EINE große Zahl'},
    quiz:         {file: 'quiz.html',         label: '🎲 Quiz: Wer gewinnt?',  desc: 'Match + 3 Optionen mit Polymarket-Quoten'}
  };

  async function fetchJson(path, fallback){
    try { return await (await fetch(path)).json(); }
    catch(e){ console.warn(`[Studio] ${path} fehlt:`, e); return fallback; }
  }
  async function fetchText(path, fallback){
    try { return await (await fetch(path)).text(); }
    catch(e){ console.warn(`[Studio] ${path} fehlt:`, e); return fallback || ''; }
  }

  async function loadAll(){
    CONFIG = await fetchJson('studio_config.json', null);
    POOLS  = await fetchJson('studio_pools.json',  null);
    WM_DATA      = await fetchJson('wm2026-data.json',          {});
    PLAYER_DATA  = await fetchJson('wm2026-player-props.json',  {});
    POLY_DATA    = await fetchJson('wm_poly_prices.json',       {});
    COMMON_CSS   = await fetchText('studio_templates/_common.css', '');
    // Templates
    for(const [type, meta] of Object.entries(TEMPLATE_FILES)){
      TEMPLATE_HTML[type] = await fetchText(`studio_templates/${meta.file}`, '');
    }
    // Profile
    ACTIVE_PROFILE = (CONFIG?.profiles?.active) || 'wm2026';
  }

  // ─────────────────────────────────────────────────────────────────────
  // Profile-aware Getter — verschmilzt shared + active profile
  // ─────────────────────────────────────────────────────────────────────
  function cfg(section, key, fallback){
    const p = CONFIG?.profiles?.[ACTIVE_PROFILE] || {};
    return p[section]?.[key] ?? fallback;
  }
  function pool(key, fallback){
    // Pool kann shared oder profile-specific sein
    const shared = POOLS?.profiles?.shared || {};
    const prof   = POOLS?.profiles?.[ACTIVE_PROFILE] || {};
    return prof[key] ?? shared[key] ?? (fallback || []);
  }

  // ─────────────────────────────────────────────────────────────────────
  // Sehr schlanke Template-Engine: {{var}} + {{#if var}}...{{/if}}
  // Reicht völlig für unsere Cards. Verhindert Inline-JS-Logik.
  // ─────────────────────────────────────────────────────────────────────
  function renderTemplate(tmpl, data){
    if(!tmpl) return '';
    // {{#if key}}...{{/if}} blocks
    tmpl = tmpl.replace(/\{\{#if\s+(\w+)\}\}([\s\S]*?)\{\{\/if\}\}/g, (m, key, body) => {
      const v = data[key];
      return (v != null && v !== '' && v !== false) ? body : '';
    });
    // {{var}} replacements (escaped by default)
    tmpl = tmpl.replace(/\{\{(\w+)\}\}/g, (m, key) => {
      const v = data[key];
      if(v == null) return '';
      return esc(v);
    });
    return tmpl;
  }

  // CSS-Variablen für Card aus Theme bauen
  function buildCssVars(){
    const theme = CONFIG?.profiles?.[ACTIVE_PROFILE]?.theme || {};
    const card  = CONFIG?.profiles?.[ACTIVE_PROFILE]?.card || {};
    return `
      :root, .stc {
        --card-w: ${card.width_px || 1080}px;
        --card-h: ${card.height_px || 1920}px;
        --accent: ${theme.accent || '#fbbf24'};
        --accent-secondary: ${theme.accent_secondary || '#dc2626'};
        --success: ${theme.success || '#34d399'};
        --primary-bg: ${theme.primary_bg || '#0a0e27'};
        --text: ${theme.text || '#ffffff'};
      }
    `;
  }

  function buildBrandData(){
    const card = CONFIG?.profiles?.[ACTIVE_PROFILE]?.card || {};
    return {
      brand:     card.brand_text    || 'COCOBET',
      brand_sub: card.brand_subtext || 'cocobet.app'
    };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Subject-Auswahl: Teams, Players, Matches — Profile-aware
  // ─────────────────────────────────────────────────────────────────────
  function listTeams(){
    if(!WM_DATA?.groups) return [];
    const out = [];
    for(const [gk, g] of Object.entries(WM_DATA.groups)){
      for(const t of (g.teams||[])){
        out.push({id:t.id, name:t.name, flag:t.flag, group:gk, elo:t.elo, confederation:t.confederation});
      }
    }
    return out.sort((a,b) => a.name.localeCompare(b.name));
  }

  function listMatches(){
    if(!WM_DATA?.groups) return [];
    const teamMap = {};
    listTeams().forEach(t => teamMap[t.id] = t);
    const out = [];
    for(const [gk, g] of Object.entries(WM_DATA.groups)){
      for(const fx of (g.fixtures||[])){
        const home = teamMap[fx.home] || {name:fx.home, flag:'🏳'};
        const away = teamMap[fx.away] || {name:fx.away, flag:'🏳'};
        const key  = `${gk}-${fx.matchday||'?'}-${fx.home}-${fx.away}`;
        out.push({
          key, home: fx.home, away: fx.away, date: fx.date, time: fx.time,
          matchday: fx.matchday, group: gk,
          label: `${home.flag} ${home.name} vs ${away.flag} ${away.name}`,
          picks: (WM_DATA.picks || {})[key] || []
        });
      }
    }
    return out;
  }

  function bestPickForMatch(match){
    const picks = (match.picks||[]).filter(p =>
      !p.trackingExcluded && (p.verdict==='BET' || p.verdict==='ABWÄGEN')
    );
    if(!picks.length) return null;
    picks.sort((a,b) => (b.edgePP||0) - (a.edgePP||0));
    return picks[0];
  }

  // ─────────────────────────────────────────────────────────────────────
  // Pool-Picker mit Rotation (anti "gleich wie zuletzt")
  // ─────────────────────────────────────────────────────────────────────
  const _poolIndex = {};
  function fromPool(key, list){
    if(!list?.length) return '';
    if(list.length === 1) return list[0];
    let idx;
    const last = _poolIndex[key];
    do { idx = Math.floor(Math.random() * list.length); } while(idx === last && list.length > 1);
    _poolIndex[key] = idx;
    return list[idx];
  }
  function rollAllPools(){
    for(const k of Object.keys(_poolIndex)) delete _poolIndex[k];
  }

  // ─────────────────────────────────────────────────────────────────────
  // Team-Pack — extrahiert alle Daten für Auto-Fill
  // ─────────────────────────────────────────────────────────────────────
  function teamPack(teamId){
    if(!teamId || !WM_DATA) return null;
    const team = listTeams().find(t => t.id === teamId);
    if(!team) return null;
    const form    = (WM_DATA.form    || {})[teamId] || {};
    const squad   = (WM_DATA.squads  || {})[teamId] || {};

    // Streaks
    const last10 = form.last10 || [];
    let undefeated = 0, winStreak = 0;
    for(let i = last10.length - 1; i >= 0; i--){
      const r = last10[i];
      if(r === 'W'){ undefeated++; winStreak++; }
      else if(r === 'D'){ undefeated++; break; }
      else break;
    }
    const wins10   = last10.filter(r => r === 'W').length;
    const losses10 = last10.filter(r => r === 'L').length;
    const last5Str = (form.last5 || []).join('-');

    // Elo-Percentile
    const elos = listTeams().map(t => t.elo).filter(x => x > 0).sort((a,b) => b-a);
    const elo  = team.elo || 0;
    const eloRank = elos.findIndex(x => x <= elo) + 1;
    const eloPct  = elo > 0 ? Math.round(100 * (1 - eloRank / elos.length)) : 0;
    const topPct  = elo > 0 ? Math.round(100 - eloPct) : 0;

    return {
      team, form, squad,
      undefeatedStreak: undefeated, winStreak, wins10, losses10, last5Str,
      elo, eloRank, eloPct, topPct
    };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Stat-Template-Engine: nimmt POOLS.shared.stat_templates und filtert
  // basierend auf den team-Daten, dann replaced Placeholders
  // ─────────────────────────────────────────────────────────────────────
  function generateStatPool(teamId){
    const p = teamPack(teamId);
    if(!p) return [];
    const templates = POOLS?.profiles?.shared?.stat_templates || [];
    const out = [];

    // Helper für Eligibility-Check + Replacement-Vars
    const sq = p.squad;
    const goalsPer90 = sq.minutes && sq.minutes > 0 ? (sq.goals * 90 / sq.minutes) : null;
    const minsPerGoal = sq.goals && sq.goals > 0 ? Math.round(sq.minutes / sq.goals) : null;
    const overPct = p.form.over25Rate != null ? Math.round(p.form.over25Rate * 100) : null;
    const bttsPct = p.form.bttsRate   != null ? Math.round(p.form.bttsRate   * 100) : null;

    const vars = {
      team_upper:    (p.team.name || '').toUpperCase(),
      elo:           p.elo,
      top_pct:       p.topPct,
      avg_scored:    p.form.avgScored != null ? p.form.avgScored.toFixed(1) : '',
      avg_conceded:  p.form.avgConceded != null ? p.form.avgConceded.toFixed(2) : '',
      games:         p.form.games || 15,
      over25_pct:    overPct,
      btts_pct:      bttsPct,
      win_streak:    p.winStreak,
      undefeated:    p.undefeatedStreak,
      wins10:        p.wins10,
      losses10:      p.losses10,
      scorer_name:   sq.name || '',
      scorer_pos:    sq.position || '',
      goals:         sq.goals || 0,
      assists:       sq.assists || 0,
      mins_per_goal: minsPerGoal,
      per_90:        goalsPer90 ? goalsPer90.toFixed(2) : ''
    };

    for(const t of templates){
      // Eligibility-Check
      if(t.min_elo_pct != null     && p.topPct < t.min_elo_pct) continue;
      if(t.max_elo_pct != null     && p.topPct > t.max_elo_pct) continue;
      if(t.min_avg_scored != null  && (p.form.avgScored || 0) < t.min_avg_scored) continue;
      if(t.max_avg_conceded != null&& (p.form.avgConceded || 999) > t.max_avg_conceded) continue;
      if(t.min_over25_rate != null && (overPct || 0) < t.min_over25_rate) continue;
      if(t.max_over25_rate != null && (overPct || 999) > t.max_over25_rate) continue;
      if(t.min_btts_rate != null   && (bttsPct || 0) < t.min_btts_rate) continue;
      if(t.min_win_streak != null  && p.winStreak < t.min_win_streak) continue;
      if(t.min_undefeated != null  && p.undefeatedStreak < t.min_undefeated) continue;
      if(t.min_wins10 != null      && p.wins10 < t.min_wins10) continue;
      if(t.max_losses10 != null    && p.losses10 > t.max_losses10) continue;
      if(t.needs_scorer            && !sq.name) continue;
      if(t.min_minutes != null     && (sq.minutes || 0) < t.min_minutes) continue;
      if(t.min_assists != null     && (sq.assists || 0) < t.min_assists) continue;
      // Render
      let line = t.template;
      for(const [k, v] of Object.entries(vars)){
        line = line.replace(new RegExp(`\\{${k}\\}`, 'g'), v ?? '');
      }
      out.push(line);
    }

    // Confederation-Lines (Profile-spezifisch)
    const conf = POOLS?.profiles?.[ACTIVE_PROFILE]?.confederation_lines || {};
    const confLines = conf[p.team.confederation] || [];
    for(const line of confLines) out.push(line);

    return out.filter(Boolean);
  }

  function generateHookPool(teamId){
    const t = listTeams().find(x => x.id === teamId);
    if(!t) return [];
    const hooks = pool('hook_templates') || [];
    return hooks.map(h => h.replace(/\{team_upper\}/g, (t.name||'?').toUpperCase()));
  }

  function generateTagPool(){
    return pool('tag_pool', []);
  }

  function generatePunchPool(){
    return pool('punchlines', []);
  }

  function generateQuizQuestionPool(){
    return pool('quiz_questions', []);
  }

  function generateBizarrePool(){
    return POOLS?.profiles?.shared?.bizarre_compares || [];
  }

  function generatePositionLabel(posCode){
    const map = POOLS?.profiles?.shared?.position_map || {};
    return map[posCode] || posCode || '';
  }

  function generatePlayerToplines(teamId){
    const p = teamPack(teamId);
    if(!p) return [];
    const sq = p.squad;
    const templates = POOLS?.profiles?.shared?.player_topline_templates || [];
    const goalsPer90 = sq.minutes && sq.minutes > 0 ? (sq.goals * 90 / sq.minutes) : null;
    const minsPerGoal = sq.goals && sq.goals > 0 ? Math.round(sq.minutes / sq.goals) : null;
    const gamesPlayed = sq.minutes ? Math.round(sq.minutes / 90) : 0;

    const vars = {
      goals: sq.goals || 0, assists: sq.assists || 0,
      games_played: gamesPlayed,
      per_90: goalsPer90 ? goalsPer90.toFixed(2) : '',
      mins_per_goal: minsPerGoal || ''
    };
    const out = [];
    for(const t of templates){
      const needs = t.needs || [];
      let ok = true;
      for(const need of needs){
        if(need === 'scorer_goals'         && !sq.goals) ok = false;
        if(need === 'scorer_games'         && !gamesPlayed) ok = false;
        if(need === 'scorer_per_90'        && !goalsPer90) ok = false;
        if(need === 'scorer_mins_per_goal' && !minsPerGoal) ok = false;
        if(need === 'scorer_assists_gt_0'  && (sq.assists || 0) <= 0) ok = false;
      }
      if(!ok) continue;
      let line = t.template;
      for(const [k,v] of Object.entries(vars)){
        line = line.replace(new RegExp(`\\{${k}\\}`, 'g'), v ?? '');
      }
      out.push(line);
    }
    return out;
  }

  function generatePlayerSublines(teamId){
    const p = teamPack(teamId);
    if(!p) return [];
    const templates = POOLS?.profiles?.shared?.player_subline_templates || [];
    const bttsPct = p.form.bttsRate != null ? Math.round(p.form.bttsRate * 100) : null;
    const vars = {
      avg_scored: p.form.avgScored != null ? p.form.avgScored.toFixed(1) : '',
      btts_pct: bttsPct || '',
      last5_str: p.last5Str || ''
    };
    const out = [];
    for(const t of templates){
      const needs = t.needs || [];
      let ok = true;
      for(const need of needs){
        if(need === 'team_avg_scored_gt_0' && !(p.form.avgScored > 0)) ok = false;
        if(need === 'team_btts_gt_50'      && !(bttsPct >= 50)) ok = false;
        if(need === 'last5_str'            && !p.last5Str) ok = false;
      }
      if(!ok) continue;
      let line = t.template;
      for(const [k,v] of Object.entries(vars)){
        line = line.replace(new RegExp(`\\{${k}\\}`, 'g'), v ?? '');
      }
      out.push(line);
    }
    return out;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Card-Templates (Field-Configs + Auto-Fill-Logik)
  // Render selbst kommt aus den HTML-Files (TEMPLATE_HTML)
  // ─────────────────────────────────────────────────────────────────────
  const CARD_LOGIC = {

    team_hook: {
      fields: [
        {key:'team', type:'team', label:'Team', required:true},
        {key:'hook', type:'text', label:'Hook (große Zeile)', maxLen:60},
        {key:'stat', type:'text', label:'Killer-Stat', maxLen:140},
        {key:'tag',  type:'text', label:'Bottom-Tag', maxLen:30}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        if(!data.team) return data;
        if(force || !data.hook) data.hook = fromPool('th.hook', generateHookPool(data.team));
        if(force || !data.stat) data.stat = fromPool('th.stat', generateStatPool(data.team)) || 'Vor der WM in absoluter Topform';
        if(force || !data.tag)  data.tag  = fromPool('th.tag', generateTagPool());
        return data;
      },
      buildRenderData: (data) => {
        const t = listTeams().find(x => x.id === data.team) || {flag:'🏳', name:'?'};
        return { ...buildBrandData(), flag:t.flag, hook:data.hook||'', stat:data.stat||'', tag:data.tag||'' };
      }
    },

    player: {
      fields: [
        {key:'team',     type:'team', label:'Team', required:true},
        {key:'player',   type:'text', label:'Spieler-Name', required:true},
        {key:'position', type:'text', label:'Position'},
        {key:'topline',  type:'text', label:'Killer-Stat', maxLen:80},
        {key:'subline',  type:'text', label:'Sub-Stat',    maxLen:80}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        if(!data.team) return data;
        const sq = (WM_DATA?.squads || {})[data.team] || {};
        if(force || !data.player)   data.player   = sq.name || '';
        if(force || !data.position) data.position = generatePositionLabel(sq.position);
        if(force || !data.topline)  data.topline  = fromPool('pl.top', generatePlayerToplines(data.team));
        if(force || !data.subline)  data.subline  = fromPool('pl.sub', generatePlayerSublines(data.team));
        return data;
      },
      buildRenderData: (data) => {
        const t = listTeams().find(x => x.id === data.team) || {flag:'🏳', name:'?'};
        return {
          ...buildBrandData(),
          flag: t.flag,
          team_upper: (t.name || '').toUpperCase(),
          player: data.player || '',
          position_upper: (data.position || '').toUpperCase(),
          topline: data.topline || '',
          subline: data.subline || ''
        };
      }
    },

    bizarre: {
      fields: [
        {key:'subject', type:'text', label:'Wer/Was', required:true},
        {key:'quote',   type:'text', label:'Quote'},
        {key:'cmp1',    type:'text', label:'Vergleich 1', maxLen:80},
        {key:'cmp2',    type:'text', label:'Vergleich 2', maxLen:80},
        {key:'cmp3',    type:'text', label:'Vergleich 3', maxLen:80}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        const cmps = generateBizarrePool();
        if(force || !data.cmp1) data.cmp1 = fromPool('bz.cmp1', cmps);
        if(force || !data.cmp2) data.cmp2 = fromPool('bz.cmp2', cmps);
        if(force || !data.cmp3) data.cmp3 = fromPool('bz.cmp3', cmps);
        return data;
      },
      buildRenderData: (data) => ({
        ...buildBrandData(),
        subject: data.subject || '',
        quote: data.quote || '',
        cmp1: data.cmp1 || '', cmp2: data.cmp2 || '', cmp3: data.cmp3 || ''
      })
    },

    match_pick: {
      fields: [
        {key:'match', type:'match', label:'Spiel', required:true},
        {key:'pick',  type:'text',  label:'Pick-Markt'},
        {key:'odds',  type:'text',  label:'Quote'},
        {key:'edge',  type:'text',  label:'Edge'},
        {key:'why',   type:'text',  label:'Begründung', maxLen:120}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        if(!data.match) return data;
        const m = listMatches().find(x => x.key === data.match);
        if(!m) return data;
        const allBets = (m.picks||[]).filter(p =>
          !p.trackingExcluded && (p.verdict==='BET' || p.verdict==='ABWÄGEN')
        );
        allBets.sort((a,b) => (b.edgePP||0) - (a.edgePP||0));
        if(force || !data.pick){
          const pickPool = allBets.slice(0, 5).map(p => p.market);
          const picked = fromPool('mp.pick', pickPool) || allBets[0]?.market;
          if(picked){
            data.pick = picked;
            const p = allBets.find(x => x.market === picked) || allBets[0];
            if(p){
              if(force || !data.odds) data.odds = String(p.odds || '');
              if(force || !data.edge) data.edge = p.edgePP ? `+${p.edgePP}pp Edge` : '';
              const whys = [];
              if(p.story) whys.push(p.story);
              if(p.signal) whys.push(p.signal);
              if(p.conf === 'high') whys.push('Hohe Confidence — Modell + Form + Bookies in Linie');
              whys.push(`Modell-Edge +${p.edgePP||'?'}pp vs Pinnacle Fair-Quote`);
              if(force || !data.why) data.why = fromPool('mp.why', whys) || '';
            }
          }
        }
        return data;
      },
      buildRenderData: (data) => {
        const m = listMatches().find(x => x.key === data.match) || {label:'?', date:'', time:''};
        return {
          ...buildBrandData(),
          date_time: (m.date || '') + (m.time ? ' · ' + m.time : ''),
          match_label: m.label || '',
          pick: data.pick || '',
          odds: data.odds || '',
          edge: data.edge || '',
          why: data.why || ''
        };
      }
    },

    killer_stat: {
      fields: [
        {key:'team',      type:'team', label:'Team', required:true},
        {key:'number',    type:'text', label:'Die Zahl', required:true},
        {key:'unit',      type:'text', label:'Einheit'},
        {key:'context',   type:'text', label:'Kontext',   maxLen:100},
        {key:'punchline', type:'text', label:'Punchline', maxLen:120}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        if(!data.team) return data;
        const p = teamPack(data.team);
        if(!p) return data;
        const sq = p.squad;
        const triplets = [];
        if(sq.goals) triplets.push({number:String(sq.goals), unit:'TORE', context:`${sq.name} in den letzten ${Math.round((sq.minutes||0)/90)} Pflichtspielen`});
        if(sq.assists) triplets.push({number:String(sq.assists), unit:'ASSISTS', context:`${sq.name} — die andere Hälfte ihrer Power`});
        if(p.form.over25Rate != null) triplets.push({number:String(Math.round(p.form.over25Rate*100)), unit:'%', context:`Über 2.5 Tore in den letzten ${p.form.games||15} Spielen`});
        if(p.form.bttsRate != null)   triplets.push({number:String(Math.round(p.form.bttsRate*100)),   unit:'%', context:`Beide Teams treffen in den letzten ${p.form.games||15} Spielen`});
        if(p.wins10 >= 5)              triplets.push({number:String(p.wins10), unit:'SIEGE', context:`In den letzten 10 Pflichtspielen`});
        if(p.undefeatedStreak >= 3)    triplets.push({number:String(p.undefeatedStreak), unit:'SPIELE', context:`Unbesiegt in Folge`});
        if(p.form.avgScored > 1.5)     triplets.push({number:p.form.avgScored.toFixed(1), unit:'TORE / SPIEL', context:`Durchschnitt der letzten ${p.form.games||15} Pflichtspiele`});
        if(p.elo)                      triplets.push({number:String(p.elo), unit:'ELO', context:`Top ${p.topPct}% aller Teilnehmer`});

        const picked = fromPool('ks.triplet', triplets.map((_,i) => i));
        const pick = triplets[picked] ?? triplets[0];
        if(pick){
          if(force || !data.number)  data.number  = pick.number;
          if(force || !data.unit)    data.unit    = pick.unit;
          if(force || !data.context) data.context = pick.context;
        }
        if(force || !data.punchline) data.punchline = fromPool('ks.punch', generatePunchPool());
        return data;
      },
      buildRenderData: (data) => {
        const t = listTeams().find(x => x.id === data.team) || {flag:'🏳', name:'?'};
        return {
          ...buildBrandData(),
          flag: t.flag,
          team_upper: (t.name || '').toUpperCase(),
          number: data.number || '',
          unit_upper: (data.unit || '').toUpperCase(),
          context: data.context || '',
          punchline: data.punchline || ''
        };
      }
    },

    quiz: {
      fields: [
        {key:'match',    type:'match', label:'Spiel', required:true},
        {key:'home_pct', type:'text',  label:'% Heimsieg'},
        {key:'draw_pct', type:'text',  label:'% Remis'},
        {key:'away_pct', type:'text',  label:'% Auswärtssieg'},
        {key:'question', type:'text',  label:'Bottom-Frage', maxLen:50}
      ],
      autoFill: (data, opts) => {
        const force = opts?.force;
        if(!data.match) return data;
        const m = listMatches().find(x => x.key === data.match);
        if(!m) return data;
        const poly = (POLY_DATA?.prices)?.[`${m.home}-${m.away}`];
        if(poly){
          if(force || !data.home_pct) data.home_pct = poly.hw ? String(Math.round(poly.hw*100)) : '';
          if(force || !data.draw_pct) data.draw_pct = poly.dr ? String(Math.round(poly.dr*100)) : '';
          if(force || !data.away_pct) data.away_pct = poly.aw ? String(Math.round(poly.aw*100)) : '';
        }
        if(force || !data.question) data.question = fromPool('qz.q', generateQuizQuestionPool());
        return data;
      },
      buildRenderData: (data) => {
        const m = listMatches().find(x => x.key === data.match) || {home:'?', away:'?'};
        const teams = listTeams();
        const home = teams.find(t => t.id === m.home) || {name:m.home, flag:'🏳'};
        const away = teams.find(t => t.id === m.away) || {name:m.away, flag:'🏳'};
        const tournLabel = ACTIVE_PROFILE === 'wm2026' ? 'WM 2026' : 'LIGA';
        return {
          ...buildBrandData(),
          tournament_label: tournLabel,
          home_flag: home.flag, away_flag: away.flag,
          home_upper: (home.name || '').toUpperCase(),
          away_upper: (away.name || '').toUpperCase(),
          home_pct: data.home_pct || '?',
          draw_pct: data.draw_pct || '?',
          away_pct: data.away_pct || '?',
          question: data.question || 'WAS TIPPST DU?'
        };
      }
    }
  };

  // ─────────────────────────────────────────────────────────────────────
  // Rendering einer Card
  // ─────────────────────────────────────────────────────────────────────
  function renderCard(type, data){
    const logic = CARD_LOGIC[type];
    const tmpl  = TEMPLATE_HTML[type];
    if(!logic || !tmpl) return '<div class="tts-error">Template nicht geladen</div>';
    const renderData = logic.buildRenderData(data);
    const cardHtml   = renderTemplate(tmpl, renderData);
    return `<style>${buildCssVars()}${COMMON_CSS}</style>${cardHtml}`;
  }

  // ─────────────────────────────────────────────────────────────────────
  // UI Rendering
  // ─────────────────────────────────────────────────────────────────────
  let _currentType = 'team_hook';
  let _currentData = {};

  function buildTypeSelector(){
    const opts = Object.entries(TEMPLATE_FILES).map(([k, m]) =>
      `<option value="${k}" ${k===_currentType?'selected':''}>${m.label}</option>`
    ).join('');
    return `<select class="tts-type" id="ttsType">${opts}</select>`;
  }

  function buildFieldInput(field){
    const val = _currentData[field.key] || '';
    if(field.type === 'team'){
      const teams = listTeams();
      const opts = ['<option value="">— wählen —</option>',
        ...teams.map(t => `<option value="${t.id}" ${val===t.id?'selected':''}>${t.flag} ${t.name}</option>`)
      ].join('');
      return `<select class="tts-input" data-key="${field.key}">${opts}</select>`;
    }
    if(field.type === 'match'){
      const matches = listMatches();
      const opts = ['<option value="">— wählen —</option>',
        ...matches.map(m => `<option value="${m.key}" ${val===m.key?'selected':''}>${m.label} · ${m.date||''}</option>`)
      ].join('');
      return `<select class="tts-input" data-key="${field.key}">${opts}</select>`;
    }
    const maxLen = field.maxLen ? ` maxlength="${field.maxLen}"` : '';
    return `<input type="text" class="tts-input" data-key="${field.key}" value="${esc(val)}"${maxLen}>`;
  }

  function buildForm(){
    const logic = CARD_LOGIC[_currentType];
    const meta  = TEMPLATE_FILES[_currentType];
    if(!logic || !meta) return '<div class="tts-error">Unbekannter Typ</div>';
    const fields = logic.fields.map(f => `
      <div class="tts-field">
        <label class="tts-label">${esc(f.label)}${f.required?' <span class="tts-req">*</span>':''}</label>
        ${buildFieldInput(f)}
      </div>
    `).join('');
    return `
      <div class="tts-desc">${esc(meta.desc)}</div>
      ${fields}
      <div class="tts-actions">
        <button class="tts-btn tts-btn-fill" id="ttsAutoFill" title="Füllt nur leere Felder">✨ Leere Felder füllen</button>
        <button class="tts-btn tts-btn-roll" id="ttsRoll"     title="Überschreibt ALLE Felder">🎲 Alles neu würfeln</button>
        <button class="tts-btn tts-btn-clear" id="ttsClear">🔄 Reset</button>
      </div>
      <div class="tts-export">
        <button class="tts-btn tts-btn-png"  id="ttsDownload">📸 PNG Download</button>
        <button class="tts-btn tts-btn-link" id="ttsShare">🔗 Share-Link kopieren</button>
        <button class="tts-btn tts-btn-open" id="ttsOpenNew">🪟 Vollformat öffnen</button>
      </div>
    `;
  }

  function renderPreview(){
    $('#ttsPreviewInner').innerHTML = renderCard(_currentType, _currentData);
  }

  function updateFromForm(){
    $$('.tts-input', $('#ttsForm')).forEach(el => {
      _currentData[el.dataset.key] = el.value;
    });
    persistToUrl();
    renderPreview();
  }

  function persistToUrl(){
    const payload = btoa(unescape(encodeURIComponent(JSON.stringify({t:_currentType, d:_currentData}))));
    history.replaceState(null, '', `#studio=${payload}`);
  }

  function restoreFromUrl(){
    const m = location.hash.match(/studio=([^&]+)/);
    if(!m) return false;
    try {
      const p = JSON.parse(decodeURIComponent(escape(atob(m[1]))));
      if(p.t && CARD_LOGIC[p.t]){ _currentType = p.t; _currentData = p.d || {}; return true; }
    } catch(e){ console.warn('[Studio] Bad URL hash:', e); }
    return false;
  }

  function doAutoFill(force){
    const logic = CARD_LOGIC[_currentType];
    if(!logic) return;
    rollAllPools();
    _currentData = logic.autoFill({..._currentData}, {force: !!force});
    rerenderForm();
  }
  function doRoll(){ doAutoFill(true); }
  function doClear(){ _currentData = {}; rerenderForm(); }

  function rerenderForm(){
    $('#ttsForm').innerHTML = buildForm();
    persistToUrl();
    renderPreview();
    bindFormEvents();
  }

  function bindFormEvents(){
    $$('.tts-input', $('#ttsForm')).forEach(el => {
      el.addEventListener('input', updateFromForm);
      el.addEventListener('change', updateFromForm);
    });
    $('#ttsAutoFill')?.addEventListener('click', () => doAutoFill(false));
    $('#ttsRoll')?.addEventListener('click', doRoll);
    $('#ttsClear')?.addEventListener('click', doClear);
    $('#ttsDownload')?.addEventListener('click', downloadPng);
    $('#ttsShare')?.addEventListener('click', copyShareUrl);
    $('#ttsOpenNew')?.addEventListener('click', openFullSize);
  }

  // ─────────────────────────────────────────────────────────────────────
  // Export-Funktionen
  // ─────────────────────────────────────────────────────────────────────
  async function downloadPng(){
    const btn = $('#ttsDownload');
    btn.textContent = '⏳ Rendere…'; btn.disabled = true;
    try {
      if(!window.html2canvas){
        await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
      }
      const target = $('#ttsPreviewInner').firstElementChild;
      if(!target) throw new Error('Keine Card-Node gefunden');
      const canvas = await html2canvas(target, { backgroundColor:null, scale:1, useCORS:true });
      const a = document.createElement('a');
      a.download = `cocobet_${_currentType}_${Date.now()}.png`;
      a.href = canvas.toDataURL('image/png');
      a.click();
    } catch(e){
      alert('PNG-Export fehlgeschlagen: ' + e.message);
      console.error(e);
    } finally {
      btn.textContent = '📸 PNG Download'; btn.disabled = false;
    }
  }

  function loadScript(src){
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src; s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function copyShareUrl(){
    persistToUrl();
    const url = location.href;
    navigator.clipboard.writeText(url).then(() => {
      const btn = $('#ttsShare');
      const original = btn.textContent;
      btn.textContent = '✅ Kopiert!';
      setTimeout(() => { btn.textContent = original; }, 1500);
    }).catch(() => prompt('URL kopieren:', url));
  }

  function openFullSize(){
    const html = $('#ttsPreviewInner').innerHTML;
    const w = window.open('', '_blank');
    w.document.write(`<!DOCTYPE html><html><head><title>CocoBet TikTok Card</title>
      <style>body{margin:0;background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh;}</style>
      </head><body>${html}</body></html>`);
    w.document.close();
  }

  // ─────────────────────────────────────────────────────────────────────
  // Init
  // ─────────────────────────────────────────────────────────────────────
  window.initTiktokStudio = async function initTiktokStudio(){
    const panel = $('#tiktokStudioPanel');
    if(!panel) return;

    panel.innerHTML = `
      <div class="tts-wrap">
        <div class="tts-header">
          <h2 class="tts-title">🎬 TikTok Studio</h2>
          <div class="tts-sub">Manueller Card-Generator · getrennt vom Daily-Cron · Profile: <code>${esc(ACTIVE_PROFILE)}</code></div>
        </div>
        <div class="tts-grid">
          <div class="tts-left">
            <div class="tts-block"><div class="tts-label">— laden —</div></div>
          </div>
          <div class="tts-right">
            <div class="tts-preview-wrap">
              <div class="tts-preview-frame">
                <div id="ttsPreviewInner"></div>
              </div>
              <div class="tts-preview-meta">Vorschau · skaliert von 1080×1920</div>
            </div>
          </div>
        </div>
      </div>
    `;

    await loadAll();
    // Default-Card-Type aus Config
    if(!restoreFromUrl()){
      _currentType = cfg('defaults', 'default_card_type', 'team_hook');
    }
    // Profile-Anzeige updaten
    $('.tts-sub').innerHTML = `Manueller Card-Generator · getrennt vom Daily-Cron · Profile: <code>${esc(ACTIVE_PROFILE)}</code>`;
    // Re-build mit Selector + Form
    $('.tts-left').innerHTML = `
      <div class="tts-block">
        <div class="tts-label">Card-Typ</div>
        ${buildTypeSelector()}
      </div>
      <div class="tts-block" id="ttsForm">— laden —</div>
    `;
    rerenderForm();

    $('#ttsType').addEventListener('change', (e) => {
      _currentType = e.target.value;
      _currentData = {};
      rerenderForm();
    });
  };

  // Auto-Init wenn Hash direkt angegeben
  document.addEventListener('DOMContentLoaded', () => {
    if(location.hash.includes('studio=')){
      setTimeout(() => { if(window.showView) window.showView('intl-studio'); }, 100);
    }
  });

})();
