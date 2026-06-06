/*
 * tiktok-studio.js — Manueller Card-Generator (NICHT mit Daily-Cron geteilt)
 * ─────────────────────────────────────────────────────────────────────────
 * Strikte Trennung zu tiktok_card_templates.py:
 *   · Daily-Cron-Cards bleiben unangetastet (Output-Konsistenz für Auto-Posts)
 *   · Studio-Cards sind eigenständig — ändern hier kaputt nichts am Cron
 *
 * Output:
 *   · PNG-Download via html2canvas (lokal ohne Backend)
 *   · Share-URL mit base64-Daten in #hash (auf Handy öffnen → Card live)
 *
 * Format: 1080×1920 (TikTok 9:16), gerendert in Container 360×640 (scale 0.33)
 */

(function(){
  'use strict';

  // ─────────────────────────────────────────────────────────────────────
  // Hilfen
  // ─────────────────────────────────────────────────────────────────────
  function esc(s){ return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $$(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }

  // Lade Daten — wm2026-data.json + Player-Props (best-effort, falls vorhanden)
  let WM_DATA = null;
  let PLAYER_DATA = null;
  let POLY_DATA = null;

  async function loadData(){
    if(WM_DATA) return;
    try { WM_DATA = await (await fetch('wm2026-data.json')).json(); }
    catch(e){ console.warn('[Studio] wm2026-data fehlt:', e); WM_DATA = {}; }
    try { PLAYER_DATA = await (await fetch('wm2026-player-props.json')).json(); }
    catch(e){ PLAYER_DATA = {}; }
    try { POLY_DATA = await (await fetch('wm_poly_prices.json')).json(); }
    catch(e){ POLY_DATA = {}; }
  }

  function listTeams(){
    if(!WM_DATA || !WM_DATA.groups) return [];
    const out = [];
    for(const [gk, g] of Object.entries(WM_DATA.groups||{})){
      for(const t of (g.teams||[])){
        out.push({id:t.id, name:t.name, flag:t.flag, group:gk, elo:t.elo, story:t.story});
      }
    }
    return out.sort((a,b) => a.name.localeCompare(b.name));
  }

  function listMatches(){
    if(!WM_DATA || !WM_DATA.groups) return [];
    const teamMap = {};
    listTeams().forEach(t => teamMap[t.id] = t);
    const out = [];
    for(const [gk, g] of Object.entries(WM_DATA.groups||{})){
      for(const fx of (g.fixtures||[])){
        const home = teamMap[fx.home] || {name:fx.home, flag:'🏳'};
        const away = teamMap[fx.away] || {name:fx.away, flag:'🏳'};
        const key = `${gk}-${fx.matchday||'?'}-${fx.home}-${fx.away}`;
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

  function listPlayers(){
    if(!PLAYER_DATA || !PLAYER_DATA.players) return [];
    return Object.values(PLAYER_DATA.players).sort((a,b) => (a.name||'').localeCompare(b.name||''));
  }

  // Bester Pick für ein Match (für Match-Pick-Template)
  function bestPickForMatch(match){
    const picks = (match.picks||[]).filter(p => !p.trackingExcluded && (p.verdict==='BET'||p.verdict==='ABWÄGEN'));
    if(!picks.length) return null;
    picks.sort((a,b) => (b.edgePP||0) - (a.edgePP||0));
    return picks[0];
  }

  // ─────────────────────────────────────────────────────────────────────
  // Studio-Card-Templates — alle 1080×1920 (TikTok 9:16)
  // ─────────────────────────────────────────────────────────────────────
  const COMMON_CSS = `
    .stc { width:1080px; height:1920px; box-sizing:border-box;
           font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
           color:#fff; display:flex; flex-direction:column; position:relative;
           overflow:hidden; }
    .stc-brand { position:absolute; bottom:48px; left:0; right:0; text-align:center;
                 font-size:32px; font-weight:800; opacity:0.9; letter-spacing:2px; }
    .stc-brand small { font-size:18px; opacity:0.7; display:block; margin-top:4px; font-weight:500; letter-spacing:1px;}
  `;

  const TEMPLATES = {

    // ────────────── 1. TEAM HOOK ──────────────
    team_hook: {
      label: '🔥 Team Hook',
      desc: 'Hook-Statement + Killer-Stat über einem Team',
      fields: [
        {key:'team', type:'team', label:'Team', required:true},
        {key:'hook', type:'text', label:'Hook (große Zeile)', placeholder:'z.B. "MAROKKO IST KEIN ZUFALL"', maxLen:60},
        {key:'stat', type:'text', label:'Killer-Stat', placeholder:'z.B. "Halbfinale 2022 — als einziges afrikanisches Team in der WM-Geschichte"', maxLen:140},
        {key:'tag', type:'text', label:'Bottom-Tag', placeholder:'z.B. "WM 2026 STARTET BALD"', maxLen:30}
      ],
      autoFill: (data) => {
        if(!data.team) return data;
        const t = listTeams().find(x => x.id===data.team);
        if(!t) return data;
        if(!data.hook) data.hook = `${t.name.toUpperCase()} IST KEIN ZUFALL`;
        if(!data.stat) data.stat = t.story || `Elo ${t.elo} — vor der WM in absoluter Topform`;
        if(!data.tag) data.tag = '🌍 WM 2026 LIVE AB 11. JUNI';
        return data;
      },
      render: (data) => {
        const t = listTeams().find(x => x.id===data.team) || {flag:'🏳', name:'?'};
        return `<style>${COMMON_CSS}
          .h-bg { background:linear-gradient(135deg,#0a0e27 0%,#1a1f4e 50%,#3a1b6e 100%); padding:140px 80px 200px; }
          .h-flag { font-size:280px; line-height:1; margin-bottom:40px; filter:drop-shadow(0 20px 40px rgba(0,0,0,0.4)); }
          .h-hook { font-size:88px; font-weight:900; line-height:1.05; letter-spacing:-2px;
                    text-shadow:0 4px 24px rgba(0,0,0,0.5); margin-bottom:60px; }
          .h-stat { font-size:46px; font-weight:600; line-height:1.35; opacity:0.95;
                    background:rgba(255,255,255,0.08); padding:36px 40px; border-radius:24px;
                    border-left:8px solid #fbbf24; }
          .h-tag { position:absolute; bottom:160px; left:0; right:0; text-align:center;
                   font-size:32px; font-weight:700; color:#fbbf24; letter-spacing:3px; }
        </style>
        <div class="stc h-bg">
          <div class="h-flag">${esc(t.flag)}</div>
          <div class="h-hook">${esc(data.hook||'')}</div>
          <div class="h-stat">${esc(data.stat||'')}</div>
          <div class="h-tag">${esc(data.tag||'')}</div>
          <div class="stc-brand">COCOBET<small>cocobet.app · WM 2026</small></div>
        </div>`;
      }
    },

    // ────────────── 2. PLAYER SPOTLIGHT ──────────────
    player: {
      label: '⭐ Player Spotlight',
      desc: 'Spieler + Killer-Linie aus Player-Props',
      fields: [
        {key:'team', type:'team', label:'Team', required:true},
        {key:'player', type:'text', label:'Spieler-Name', placeholder:'z.B. "Bellingham"', required:true},
        {key:'position', type:'text', label:'Position', placeholder:'z.B. "MITTELFELD"'},
        {key:'topline', type:'text', label:'Killer-Stat', placeholder:'z.B. "11 Tore in 9 Quali-Spielen"', maxLen:80},
        {key:'subline', type:'text', label:'Sub-Stat', placeholder:'z.B. "Trifft alle 65 Minuten"', maxLen:80}
      ],
      autoFill: (data) => data,
      render: (data) => {
        const t = listTeams().find(x => x.id===data.team) || {flag:'🏳', name:'?'};
        return `<style>${COMMON_CSS}
          .p-bg { background:linear-gradient(180deg,#1a0e2e 0%,#0a0e27 100%); padding:120px 80px; }
          .p-flag { font-size:160px; line-height:1; margin-bottom:24px; }
          .p-team { font-size:38px; font-weight:700; opacity:0.7; margin-bottom:60px; letter-spacing:3px; }
          .p-name { font-size:120px; font-weight:900; line-height:1; letter-spacing:-3px; margin-bottom:24px;
                    background:linear-gradient(135deg,#fbbf24,#f59e0b); -webkit-background-clip:text; background-clip:text;
                    -webkit-text-fill-color:transparent; }
          .p-pos { font-size:36px; font-weight:600; opacity:0.8; margin-bottom:80px; letter-spacing:4px; }
          .p-stat-box { background:rgba(251,191,36,0.1); border:2px solid rgba(251,191,36,0.3);
                        border-radius:32px; padding:48px; margin-bottom:32px; }
          .p-stat-label { font-size:26px; font-weight:700; color:#fbbf24; margin-bottom:16px; letter-spacing:2px; }
          .p-stat-line { font-size:56px; font-weight:800; line-height:1.2; }
          .p-stat-sub { background:rgba(255,255,255,0.06); border-radius:24px; padding:36px 40px; }
          .p-stat-sub-line { font-size:40px; font-weight:600; line-height:1.3; }
        </style>
        <div class="stc p-bg">
          <div class="p-flag">${esc(t.flag)}</div>
          <div class="p-team">${esc((t.name||'').toUpperCase())}</div>
          <div class="p-name">${esc(data.player||'')}</div>
          <div class="p-pos">${esc((data.position||'').toUpperCase())}</div>
          <div class="p-stat-box">
            <div class="p-stat-label">⚡ KILLER-STAT</div>
            <div class="p-stat-line">${esc(data.topline||'')}</div>
          </div>
          <div class="p-stat-sub">
            <div class="p-stat-sub-line">${esc(data.subline||'')}</div>
          </div>
          <div class="stc-brand">COCOBET<small>cocobet.app · WM 2026</small></div>
        </div>`;
      }
    },

    // ────────────── 3. BIZARRE COMPARE ──────────────
    bizarre: {
      label: '🤯 Bizarre Compare',
      desc: '3 schiefe Vergleiche zu einer Quote',
      fields: [
        {key:'subject', type:'text', label:'Wer/Was', placeholder:'z.B. "Marokko ins Halbfinale"', required:true},
        {key:'quote', type:'text', label:'Quote', placeholder:'z.B. "1.85"'},
        {key:'cmp1', type:'text', label:'Vergleich 1', placeholder:'z.B. "wahrscheinlicher als dass Belgien rauskommt"', maxLen:80},
        {key:'cmp2', type:'text', label:'Vergleich 2', placeholder:'z.B. "fast so sicher wie ein Bayern-Sieg gegen Köln"', maxLen:80},
        {key:'cmp3', type:'text', label:'Vergleich 3', placeholder:'z.B. "öfter eingetroffen als Münchner Pünktlichkeit"', maxLen:80}
      ],
      autoFill: (d) => d,
      render: (data) => `<style>${COMMON_CSS}
        .b-bg { background:linear-gradient(180deg,#0a0e27 0%,#1e293b 100%); padding:120px 80px; }
        .b-hook { font-size:52px; font-weight:600; opacity:0.8; margin-bottom:24px; }
        .b-subject { font-size:84px; font-weight:900; line-height:1.05; margin-bottom:24px; letter-spacing:-1px; }
        .b-quote { display:inline-block; background:#fbbf24; color:#0a0e27; padding:24px 48px; border-radius:24px;
                   font-size:96px; font-weight:900; margin-bottom:80px; box-shadow:0 12px 32px rgba(251,191,36,0.4); }
        .b-cmp { background:rgba(255,255,255,0.06); border-left:6px solid #fbbf24; padding:32px 40px;
                 border-radius:20px; margin-bottom:28px; font-size:40px; font-weight:600; line-height:1.3; }
        .b-cmp::before { content:"→ "; color:#fbbf24; font-weight:900; }
      </style>
      <div class="stc b-bg">
        <div class="b-hook">DAS HEISST ZU SAGEN</div>
        <div class="b-subject">${esc(data.subject||'')}</div>
        ${data.quote ? `<div class="b-quote">@${esc(data.quote)}</div>` : ''}
        ${data.cmp1 ? `<div class="b-cmp">${esc(data.cmp1)}</div>` : ''}
        ${data.cmp2 ? `<div class="b-cmp">${esc(data.cmp2)}</div>` : ''}
        ${data.cmp3 ? `<div class="b-cmp">${esc(data.cmp3)}</div>` : ''}
        <div class="stc-brand">COCOBET<small>cocobet.app · Sportwetten mit Kopf</small></div>
      </div>`
    },

    // ────────────── 4. MATCH PICK ──────────────
    match_pick: {
      label: '🎯 Match Pick',
      desc: 'Bester Pick zu einem Match',
      fields: [
        {key:'match', type:'match', label:'Spiel', required:true},
        {key:'pick', type:'text', label:'Pick-Markt', placeholder:'z.B. "Über 2.5 Tore"'},
        {key:'odds', type:'text', label:'Quote', placeholder:'z.B. "1.85"'},
        {key:'edge', type:'text', label:'Edge', placeholder:'z.B. "+8pp"'},
        {key:'why', type:'text', label:'Begründung', placeholder:'z.B. "Beide Teams treffen in 7 von 8 Quali-Spielen"', maxLen:120}
      ],
      autoFill: (data) => {
        if(!data.match) return data;
        const m = listMatches().find(x => x.key===data.match);
        if(!m) return data;
        const best = bestPickForMatch(m);
        if(best){
          if(!data.pick) data.pick = best.market;
          if(!data.odds) data.odds = String(best.odds || '');
          if(!data.edge) data.edge = best.edgePP ? `+${best.edgePP}pp` : '';
          if(!data.why) data.why = best.story || best.signal || '';
        }
        return data;
      },
      render: (data) => {
        const m = listMatches().find(x => x.key===data.match) || {label:'?', date:'', time:''};
        return `<style>${COMMON_CSS}
          .m-bg { background:linear-gradient(135deg,#064e3b 0%,#022c22 100%); padding:120px 80px; }
          .m-day { font-size:32px; opacity:0.7; margin-bottom:32px; letter-spacing:3px; }
          .m-match { font-size:62px; font-weight:800; line-height:1.15; margin-bottom:100px; }
          .m-pick-label { font-size:30px; font-weight:700; color:#34d399; margin-bottom:16px; letter-spacing:3px; }
          .m-pick { font-size:88px; font-weight:900; line-height:1.05; margin-bottom:60px; letter-spacing:-1px; }
          .m-odds-row { display:flex; gap:32px; margin-bottom:60px; }
          .m-odds-box { flex:1; background:rgba(52,211,153,0.1); border:2px solid rgba(52,211,153,0.4);
                        border-radius:24px; padding:36px; text-align:center; }
          .m-odds-label { font-size:24px; font-weight:600; opacity:0.7; margin-bottom:12px; letter-spacing:2px; }
          .m-odds-val { font-size:72px; font-weight:900; color:#34d399; }
          .m-why { background:rgba(255,255,255,0.06); border-radius:24px; padding:40px;
                   font-size:38px; font-weight:600; line-height:1.35; }
        </style>
        <div class="stc m-bg">
          <div class="m-day">${esc((m.date||'') + (m.time ? ' · ' + m.time : ''))}</div>
          <div class="m-match">${esc(m.label||'')}</div>
          <div class="m-pick-label">🎯 PICK</div>
          <div class="m-pick">${esc(data.pick||'')}</div>
          <div class="m-odds-row">
            ${data.odds ? `<div class="m-odds-box"><div class="m-odds-label">QUOTE</div><div class="m-odds-val">${esc(data.odds)}</div></div>` : ''}
            ${data.edge ? `<div class="m-odds-box"><div class="m-odds-label">EDGE</div><div class="m-odds-val">${esc(data.edge)}</div></div>` : ''}
          </div>
          ${data.why ? `<div class="m-why">${esc(data.why)}</div>` : ''}
          <div class="stc-brand">COCOBET<small>cocobet.app · Picks mit Modell-Edge</small></div>
        </div>`;
      }
    },

    // ────────────── 5. DAILY KILLER STAT ──────────────
    killer_stat: {
      label: '💥 Killer Stat',
      desc: 'Team + EINE große Zahl',
      fields: [
        {key:'team', type:'team', label:'Team', required:true},
        {key:'number', type:'text', label:'Die Zahl', placeholder:'z.B. "11"', required:true},
        {key:'unit', type:'text', label:'Einheit', placeholder:'z.B. "TORE"'},
        {key:'context', type:'text', label:'Kontext', placeholder:'z.B. "In den letzten 9 Quali-Spielen"', maxLen:100},
        {key:'punchline', type:'text', label:'Punchline', placeholder:'z.B. "Mehr als Deutschland + Frankreich zusammen"', maxLen:120}
      ],
      autoFill: (d) => d,
      render: (data) => {
        const t = listTeams().find(x => x.id===data.team) || {flag:'🏳', name:'?'};
        return `<style>${COMMON_CSS}
          .k-bg { background:linear-gradient(135deg,#7c2d12 0%,#431407 100%); padding:120px 80px; text-align:center; }
          .k-flag { font-size:140px; line-height:1; margin-bottom:24px; }
          .k-team { font-size:42px; font-weight:700; opacity:0.85; margin-bottom:120px; letter-spacing:4px; }
          .k-number { font-size:360px; font-weight:900; line-height:0.9; letter-spacing:-12px; margin-bottom:20px;
                      background:linear-gradient(135deg,#fbbf24,#dc2626); -webkit-background-clip:text;
                      background-clip:text; -webkit-text-fill-color:transparent;
                      text-shadow:0 20px 60px rgba(220,38,38,0.4); }
          .k-unit { font-size:64px; font-weight:800; letter-spacing:8px; margin-bottom:80px; }
          .k-context { font-size:38px; font-weight:600; line-height:1.3; opacity:0.95; margin-bottom:40px;
                       background:rgba(255,255,255,0.08); padding:32px; border-radius:24px; }
          .k-punch { font-size:46px; font-weight:800; line-height:1.2; color:#fbbf24; padding:0 20px; }
        </style>
        <div class="stc k-bg">
          <div class="k-flag">${esc(t.flag)}</div>
          <div class="k-team">${esc((t.name||'').toUpperCase())}</div>
          <div class="k-number">${esc(data.number||'')}</div>
          <div class="k-unit">${esc((data.unit||'').toUpperCase())}</div>
          ${data.context ? `<div class="k-context">${esc(data.context)}</div>` : ''}
          ${data.punchline ? `<div class="k-punch">${esc(data.punchline)}</div>` : ''}
          <div class="stc-brand">COCOBET<small>cocobet.app · Killer-Stats täglich</small></div>
        </div>`;
      }
    },

    // ────────────── 6. QUIZ "WER GEWINNT?" ──────────────
    quiz: {
      label: '🎲 Quiz: Wer gewinnt?',
      desc: 'Match + 3 Optionen mit Polymarket-Quoten',
      fields: [
        {key:'match', type:'match', label:'Spiel', required:true},
        {key:'home_pct', type:'text', label:'% Heimsieg', placeholder:'z.B. "45"'},
        {key:'draw_pct', type:'text', label:'% Remis', placeholder:'z.B. "28"'},
        {key:'away_pct', type:'text', label:'% Auswärtssieg', placeholder:'z.B. "27"'},
        {key:'question', type:'text', label:'Bottom-Frage', placeholder:'Default: WAS TIPPST DU?', maxLen:50}
      ],
      autoFill: (data) => {
        if(!data.match) return data;
        const m = listMatches().find(x => x.key===data.match);
        if(!m) return data;
        const polyKey = `${m.home}-${m.away}`;
        const poly = (POLY_DATA && POLY_DATA.prices) ? POLY_DATA.prices[polyKey] : null;
        if(poly){
          if(!data.home_pct && poly.hw) data.home_pct = String(Math.round(poly.hw*100));
          if(!data.draw_pct && poly.dr) data.draw_pct = String(Math.round(poly.dr*100));
          if(!data.away_pct && poly.aw) data.away_pct = String(Math.round(poly.aw*100));
        }
        if(!data.question) data.question = 'WAS TIPPST DU?';
        return data;
      },
      render: (data) => {
        const m = listMatches().find(x => x.key===data.match) || {home:'?', away:'?'};
        const teams = listTeams();
        const home = teams.find(t => t.id===m.home) || {name:m.home, flag:'🏳'};
        const away = teams.find(t => t.id===m.away) || {name:m.away, flag:'🏳'};
        const homePct = data.home_pct||'?';
        const drawPct = data.draw_pct||'?';
        const awayPct = data.away_pct||'?';
        return `<style>${COMMON_CSS}
          .q-bg { background:linear-gradient(180deg,#1e1b4b 0%,#0f0a2e 100%); padding:120px 80px; }
          .q-title { text-align:center; font-size:46px; font-weight:700; margin-bottom:24px; opacity:0.85; letter-spacing:2px; }
          .q-match { text-align:center; display:flex; align-items:center; justify-content:center; gap:32px;
                     margin-bottom:80px; font-size:72px; font-weight:900; }
          .q-vs { color:#fbbf24; font-size:54px; }
          .q-opt { background:rgba(255,255,255,0.06); border-radius:32px; padding:48px;
                   margin-bottom:32px; display:flex; align-items:center; justify-content:space-between; gap:32px; }
          .q-opt-label { font-size:54px; font-weight:800; line-height:1.1; flex:1; }
          .q-opt-pct { font-size:96px; font-weight:900; color:#fbbf24; letter-spacing:-2px; }
          .q-opt-pct small { font-size:42px; opacity:0.7; }
          .q-question { text-align:center; margin-top:60px; font-size:44px; font-weight:800;
                        color:#fbbf24; letter-spacing:3px; }
        </style>
        <div class="stc q-bg">
          <div class="q-title">⚽ WM 2026 · WER GEWINNT?</div>
          <div class="q-match">
            <span>${esc(home.flag)}</span><span class="q-vs">vs</span><span>${esc(away.flag)}</span>
          </div>
          <div class="q-opt">
            <div class="q-opt-label">${esc(home.name.toUpperCase())}</div>
            <div class="q-opt-pct">${esc(homePct)}<small>%</small></div>
          </div>
          <div class="q-opt">
            <div class="q-opt-label">UNENTSCHIEDEN</div>
            <div class="q-opt-pct">${esc(drawPct)}<small>%</small></div>
          </div>
          <div class="q-opt">
            <div class="q-opt-label">${esc(away.name.toUpperCase())}</div>
            <div class="q-opt-pct">${esc(awayPct)}<small>%</small></div>
          </div>
          <div class="q-question">${esc(data.question||'WAS TIPPST DU?')}</div>
          <div class="stc-brand">COCOBET<small>cocobet.app · Quoten vom Polymarket</small></div>
        </div>`;
      }
    }
  };

  // ─────────────────────────────────────────────────────────────────────
  // UI Rendering
  // ─────────────────────────────────────────────────────────────────────
  let _currentType = 'team_hook';
  let _currentData = {};

  function buildTypeSelector(){
    const opts = Object.entries(TEMPLATES).map(([k,v]) =>
      `<option value="${k}" ${k===_currentType?'selected':''}>${v.label}</option>`
    ).join('');
    return `<select class="tts-type" id="ttsType">${opts}</select>`;
  }

  function buildFieldInput(field){
    const val = _currentData[field.key] || '';
    if(field.type==='team'){
      const teams = listTeams();
      const opts = ['<option value="">— wählen —</option>',
        ...teams.map(t => `<option value="${t.id}" ${val===t.id?'selected':''}>${t.flag} ${t.name}</option>`)
      ].join('');
      return `<select class="tts-input" data-key="${field.key}">${opts}</select>`;
    }
    if(field.type==='match'){
      const matches = listMatches();
      const opts = ['<option value="">— wählen —</option>',
        ...matches.map(m => `<option value="${m.key}" ${val===m.key?'selected':''}>${m.label} · ${m.date||''}</option>`)
      ].join('');
      return `<select class="tts-input" data-key="${field.key}">${opts}</select>`;
    }
    const maxLen = field.maxLen ? ` maxlength="${field.maxLen}"` : '';
    return `<input type="text" class="tts-input" data-key="${field.key}"
             value="${esc(val)}" placeholder="${esc(field.placeholder||'')}"${maxLen}>`;
  }

  function buildForm(){
    const tmpl = TEMPLATES[_currentType];
    if(!tmpl) return '<div class="tts-error">Unbekannter Typ</div>';
    const fields = tmpl.fields.map(f => `
      <div class="tts-field">
        <label class="tts-label">${esc(f.label)}${f.required?' <span class="tts-req">*</span>':''}</label>
        ${buildFieldInput(f)}
      </div>
    `).join('');
    return `
      <div class="tts-desc">${esc(tmpl.desc)}</div>
      ${fields}
      <div class="tts-actions">
        <button class="tts-btn tts-btn-fill" id="ttsAutoFill">✨ Auto-Fill</button>
        <button class="tts-btn tts-btn-clear" id="ttsClear">🔄 Reset</button>
      </div>
      <div class="tts-export">
        <button class="tts-btn tts-btn-png" id="ttsDownload">📸 PNG Download</button>
        <button class="tts-btn tts-btn-link" id="ttsShare">🔗 Share-Link kopieren</button>
        <button class="tts-btn tts-btn-open" id="ttsOpenNew">🪟 Vollformat öffnen</button>
      </div>
    `;
  }

  function renderPreview(){
    const tmpl = TEMPLATES[_currentType];
    if(!tmpl){ $('#ttsPreviewInner').innerHTML = '<div class="tts-error">Unbekannter Typ</div>'; return; }
    const html = tmpl.render(_currentData);
    $('#ttsPreviewInner').innerHTML = html;
  }

  function updateFromForm(){
    $$('.tts-input', $('#ttsForm')).forEach(el => {
      _currentData[el.dataset.key] = el.value;
    });
    persistToUrl();
    renderPreview();
  }

  function persistToUrl(){
    const payload = btoa(unescape(encodeURIComponent(JSON.stringify({t:_currentType,d:_currentData}))));
    history.replaceState(null,'',`#studio=${payload}`);
  }

  function restoreFromUrl(){
    const m = location.hash.match(/studio=([^&]+)/);
    if(!m) return false;
    try {
      const p = JSON.parse(decodeURIComponent(escape(atob(m[1]))));
      if(p.t && TEMPLATES[p.t]){ _currentType = p.t; _currentData = p.d||{}; return true; }
    } catch(e){ console.warn('[Studio] Bad URL hash:', e); }
    return false;
  }

  function doAutoFill(){
    const tmpl = TEMPLATES[_currentType];
    if(!tmpl) return;
    _currentData = tmpl.autoFill({..._currentData});
    rerenderForm();
  }

  function doClear(){
    _currentData = {};
    rerenderForm();
  }

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
    $('#ttsAutoFill')?.addEventListener('click', doAutoFill);
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
    return new Promise((resolve,reject) => {
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
    }).catch(() => {
      prompt('URL kopieren:', url);
    });
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
  // Init — wird von ui.js showSubView('studio') aufgerufen
  // ─────────────────────────────────────────────────────────────────────
  window.initTiktokStudio = async function initTiktokStudio(){
    const panel = $('#tiktokStudioPanel');
    if(!panel) return;
    panel.innerHTML = `
      <div class="tts-wrap">
        <div class="tts-header">
          <h2 class="tts-title">🎬 TikTok Studio</h2>
          <div class="tts-sub">Manueller Card-Generator · getrennt vom Daily-Cron</div>
        </div>
        <div class="tts-grid">
          <div class="tts-left">
            <div class="tts-block">
              <div class="tts-label">Card-Typ</div>
              ${buildTypeSelector()}
            </div>
            <div class="tts-block" id="ttsForm">— laden —</div>
          </div>
          <div class="tts-right">
            <div class="tts-preview-wrap">
              <div class="tts-preview-frame">
                <div id="ttsPreviewInner"></div>
              </div>
              <div class="tts-preview-meta">Vorschau · skaliert 0.33× von 1080×1920</div>
            </div>
          </div>
        </div>
      </div>
    `;

    await loadData();
    restoreFromUrl();
    rerenderForm();

    $('#ttsType').addEventListener('change', (e) => {
      _currentType = e.target.value;
      _currentData = {};
      rerenderForm();
    });
  };

  // Auto-Init, falls Studio-Hash direkt aufgerufen (z.B. Share-Link)
  document.addEventListener('DOMContentLoaded', () => {
    if(location.hash.includes('studio=')){
      setTimeout(() => {
        if(window.showView){ window.showView('intl-studio'); }
      }, 100);
    }
  });

})();
