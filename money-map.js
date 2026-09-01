/* money-map.js — Money Map Tab (11.08.2026, Lucas): pro Fussballspiel die Betfair- + Poly-GELD-Blasen
   (Groesse = Geld, Position = Seite) auf einer Team-vs-Team-Achse mit zwei Spuren, plus Pinnacle als
   scharfer Tick. Sub-Menue: Map (Bubble-Cards) | Tracking (Trefferquote je Verdikt). Liest money_map.json
   + money_map_record.json (vom Runner, betfair_consensus.py). Reine Anzeige. */
(function(){
  var _mmView='map', _mmFilter='all', _mm={map:null,rec:null}, _mmStyled=false;

  function _mmStyle(){
    if(_mmStyled) return; _mmStyled=true;
    var css=[
'#moneyMapPanel{color:#e6ebf5}',
'#moneyMapPanel .mm-loading,#moneyMapPanel .mm-empty{text-align:center;color:#76819c;padding:44px 16px;line-height:1.7}',
'.mm-head{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:4px}',
'.mm-ic{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;font-size:16px;background:rgba(57,135,229,.14);border:1px solid rgba(57,135,229,.32)}',
'.mm-head h1{font-size:19px;font-weight:800;margin:0;letter-spacing:-.01em}',
'.mm-sub{flex-basis:100%;color:#8a95ad;font-size:12.5px;line-height:1.5;margin-top:2px;max-width:820px}',
'.mm-nav{display:flex;gap:6px;margin:14px 0 16px}',
'.mm-filt{display:flex;gap:6px;margin:0 0 14px;align-items:center}',
'.mm-filt .mm-fl{font-size:11px;color:#6b7480;font-weight:700;margin-right:2px}',
'.mm-fb{background:#151b24;border:1px solid #242c38;color:#9aa4b1;font:inherit;font-size:11.5px;font-weight:700;padding:5px 12px;border-radius:8px;cursor:pointer}',
'.mm-fb.on{background:rgba(57,135,229,.16);border-color:rgba(57,135,229,.42);color:#8fc0ff}',
'.mm-nb{background:#151b24;border:1px solid #242c38;color:#9aa4b1;font:inherit;font-size:12.5px;font-weight:700;padding:7px 15px;border-radius:9px;cursor:pointer}',
'.mm-nb.on{background:rgba(234,185,56,.14);border-color:rgba(234,185,56,.4);color:#f2c14e}',
'.mm-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}',
'@media(max-width:760px){.mm-grid{grid-template-columns:1fr}}',
'.mm-card{position:relative;background:linear-gradient(180deg,#161d27,#131922);border:1px solid #242c38;border-radius:15px;padding:14px 16px 15px;overflow:hidden}',
'.mm-card.mm-kon{border-color:rgba(46,160,67,.4);box-shadow:0 0 0 1px rgba(46,160,67,.10),0 8px 28px -18px rgba(46,160,67,.6)}',
'.mm-card.mm-div{border-color:rgba(201,133,0,.45);box-shadow:0 0 0 1px rgba(201,133,0,.12),0 8px 28px -18px rgba(201,133,0,.55)}',
'.mm-ch{display:flex;align-items:center;gap:8px;margin-bottom:2px}',
'.mm-t{font-size:14.5px;font-weight:800;letter-spacing:-.01em}.mm-vs{color:#6b7480}',
'.mm-lg{margin-left:auto;font-size:11px;color:#6b7480;font-weight:600}',
'.mm-pill{font-size:9px;font-weight:800;letter-spacing:.4px;padding:2px 7px;border-radius:6px;text-transform:uppercase}',
'.mm-pill.mm-pre{color:#8fc0ff;border:1px solid rgba(57,135,229,.4)}',
'.mm-pill.mm-live{color:#ff7a70;border:1px solid rgba(229,83,75,.5)}',
'.mm-axis{position:relative;height:132px;margin:12px 2px 4px}',
'.mm-ends{position:absolute;top:0;left:0;right:0;display:flex;justify-content:space-between;font-size:12px;font-weight:700;color:#9aa4b1}',
'.mm-lane{position:absolute;left:16%;right:6%;height:2px;border-radius:2px;background:linear-gradient(90deg,rgba(154,164,177,.08),rgba(154,164,177,.24),rgba(154,164,177,.08))}',
'.mm-lane.mm-lbf{top:56px}.mm-lane.mm-lpoly{top:96px}',
'.mm-ll{position:absolute;left:0;transform:translateY(-50%);font-size:10px;font-weight:800}',
'.mm-ll.mm-lbf{top:56px;color:#eab938}.mm-ll.mm-lpoly{top:96px;color:#22a06b}',
'.mm-pinn{position:absolute;top:40px;transform:translateX(-50%);text-align:center;z-index:1}',
'.mm-pinn i{display:block;width:2px;height:74px;background:linear-gradient(180deg,#3987e5,rgba(57,135,229,.25));margin:0 auto;border-radius:2px;box-shadow:0 0 10px rgba(57,135,229,.6)}',
'.mm-pinn .mm-d{width:9px;height:9px;background:#3987e5;transform:rotate(45deg);margin:-3px auto 0;border-radius:2px}',
'.mm-pl{position:absolute;top:-15px;left:50%;transform:translateX(-50%);font-size:8.5px;color:#8fc0ff;font-weight:700;white-space:nowrap}',
'.mm-col{position:absolute;top:52px;height:48px;width:3px;transform:translateX(-50%);border-radius:3px;background:linear-gradient(180deg,rgba(46,160,67,0),rgba(46,160,67,.35),rgba(46,160,67,0));z-index:0}',
'.mm-bub{position:absolute;transform:translate(-50%,-50%);border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:800;color:#0a0e14;box-shadow:0 4px 14px -4px rgba(0,0,0,.7);border:2px solid rgba(255,255,255,.16);z-index:2}',
'.mm-bub.mm-bf{background:radial-gradient(circle at 35% 30%,#f6d477,#eab938)}',
'.mm-bub.mm-poly{background:radial-gradient(circle at 35% 30%,#54cf9a,#22a06b);color:#04140d}',
'.mm-bub.mm-poly-est{border-style:dashed;border-color:rgba(84,207,154,.7);opacity:.9}',
'.mm-foot{display:flex;align-items:center;gap:8px;margin-top:10px;padding-top:11px;border-top:1px solid #242c38}',
'.mm-verd{font-size:12.5px;font-weight:800}.mm-verd.k{color:#4ade80}.mm-verd.d{color:#e3b341}.mm-verd.p{color:#9aa4b1}',
'.mm-vsub{font-size:11.5px;color:#6b7480}',
'.mm-odds{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 2px 0;font-size:11.5px;font-weight:700;color:#c2ccd8;font-variant-numeric:tabular-nums}',
'.mm-odds .mm-om{color:#6b7480;font-weight:600;letter-spacing:.02em}',
'.mm-odds .mm-oc{color:#4ade80}',
'.mm-odds b{color:#8fc0ff;font-weight:800;margin-right:3px}',
'.mm-src{margin-left:auto;font-size:10.5px;font-weight:800;color:#6b7480;background:#1b2430;border:1px solid #242c38;border-radius:20px;padding:3px 9px}',
'.mm-trk-intro{color:#8a95ad;font-size:12.5px;line-height:1.55;max-width:760px;margin-bottom:14px}',
'.mm-tbl{width:100%;border-collapse:collapse;max-width:640px}',
'.mm-tbl th{text-align:left;font-size:11px;color:#6b7480;font-weight:700;padding:6px 10px;border-bottom:1px solid #242c38}',
'.mm-tbl td{font-size:13px;padding:9px 10px;border-bottom:1px solid #1b2430}',
'.mm-cn{text-align:right;font-variant-numeric:tabular-nums}.mm-mut{color:#8a95ad}',
'.mm-trk-foot{margin-top:12px;color:#6b7480;font-size:11.5px}'
].join('\n');
    var s=document.createElement('style'); s.textContent=css; document.head.appendChild(s);
  }

  function _esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c];});}
  function _usd(v){v=+v||0;if(v>=1e6)return '$'+(v/1e6).toFixed(2)+'M';if(v>=1e3)return '$'+(v/1e3).toFixed(v>=1e4?0:1)+'K';return '$'+Math.round(v);}
  function _eur(v){v=+v||0;if(v>=1e6)return '€'+(v/1e6).toFixed(2)+'M';if(v>=1e3)return '€'+(v/1e3).toFixed(v>=1e4?0:1)+'K';return '€'+Math.round(v);}
  function _clamp(v,a,b){return v<a?a:v>b?b:v;}
  function _dia(m){return Math.max(30,Math.min(72,20+Math.sqrt(+m||0)/8));}
  function _posShare(side,sharePct){ if(side==='draw'||side==null)return 50; var d=(side==='away')?1:-1; return _clamp(50+d*((+sharePct||33)-33)*0.9,7,93); }
  function _posPinn(pn){ if(!pn)return null; var h=+pn.home||0,a=+pn.away||0; return _clamp(50+(a-h)*90,7,93); }
  function _fair(p){ p=+p||0; return p>0?(1/p).toFixed(2):'—'; }   // de-viggte Wahrscheinlichkeit → faire Quote

  function _mmAgeH(){ var g=_mm.map&&_mm.map.generatedAt; if(!g) return null; var t=Date.parse(g); return isNaN(t)?null:Math.max(0,(Date.now()-t)/3.6e6); }
  function _mmCard(r){
    var bf=r.betfair,poly=r.poly,pn=r.pinn;
    var kon=r.verdict==='konsens',div=r.verdict==='uneinig',strong=!!r.mmStrong,konS=kon&&strong,divS=div&&strong;
    var live=r.live?'<span class="mm-pill mm-live">● Live</span>':'<span class="mm-pill mm-pre">Pre</span>';
    var bfPos=bf?_posShare(bf.side,bf.sharePct):null, pPos=poly?_posShare(poly.side,poly.sharePct):null, pnPos=_posPinn(pn);
    var bub='';
    if(bf&&poly&&bfPos!=null&&pPos!=null&&Math.abs(bfPos-pPos)<8) bub+='<div class="mm-col" style="left:'+((bfPos+pPos)/2)+'%"></div>';
    if(pn&&pnPos!=null){ var pf=pn.fav, pp=Math.round((+pn[pf]||0)*100); bub+='<div class="mm-pinn" style="left:'+pnPos+'%"><span class="mm-pl">Pinnacle '+pp+'%</span><i></i><div class="mm-d"></div></div>'; }
    if(bf&&bfPos!=null){ var d=_dia(bf.eur); bub+='<div class="mm-bub mm-bf" style="left:'+bfPos+'%;top:56px;width:'+d+'px;height:'+d+'px">'+_eur(bf.eur)+'</div>'; }
    if(poly&&pPos!=null){ var d2=_dia(poly.usd); var _est=(poly.src==='upcoming')?' mm-poly-est':''; bub+='<div class="mm-bub mm-poly'+_est+'" title="'+((poly.src==='upcoming')?'Poly-Preis (vor Anpfiff, keine Geld-Verteilung)':'Poly-Geld')+'" style="left:'+pPos+'%;top:96px;width:'+d2+'px;height:'+d2+'px">'+_usd(poly.usd)+'</div>'; }
    var vtxt=kon?(strong?'✅ Konsens':'✅ knapp einig'):(div?(strong?'⚠️ Divergenz':'◽ knapp — Münzwurf'):(r.verdict==='teil'?'➖ teils einig':'—'));
    var vsub=kon?(strong?('einig auf '+_esc((bf&&bf.name)||'')):'beide knapp — schwaches Signal'):(divS?'Geld & scharfe Linie klar uneinig':(div?'beide nahe 50/50 — kein klares Signal':''));
    return '<div class="mm-card'+(konS?' mm-kon':(divS?' mm-div':''))+'">'
      +'<div class="mm-ch"><span>⚽</span><span class="mm-t">'+_esc(r.home)+' <span class="mm-vs">vs</span> '+_esc(r.away)+'</span>'+live+'<span class="mm-lg">'+_esc(r.league||'')+'</span></div>'
      +'<div class="mm-axis"><div class="mm-ends"><span>'+_esc(r.home)+'</span><span>'+_esc(r.away)+'</span></div>'
        +'<div class="mm-lane mm-lbf"></div><div class="mm-ll mm-lbf">Betfair</div>'
        +'<div class="mm-lane mm-lpoly"></div><div class="mm-ll mm-lpoly"'+(poly?'':' style="opacity:.4"')+'>Poly'+(poly?(poly.src==='scan'?' · Preis (dünn)':(poly.src==='upcoming'?' · früh':'')):' · kein Markt')+'</div>'
        +bub+'</div>'
      +(pn?('<div class="mm-odds"><span class="mm-om">Faire Quote · Pinnacle</span>'
        +'<span class="'+((bf&&bf.side==='home')?'mm-oc':'')+'"><b>1</b> '+_fair(pn.home)+'</span>'
        +'<span class="'+((bf&&bf.side==='draw')?'mm-oc':'')+'"><b>X</b> '+_fair(pn.draw)+'</span>'
        +'<span class="'+((bf&&bf.side==='away')?'mm-oc':'')+'"><b>2</b> '+_fair(pn.away)+'</span></div>'):'')
      +'<div class="mm-foot"><span class="mm-verd '+(konS?'k':(divS?'d':'p'))+'">'+vtxt+'</span><span class="mm-vsub">'+vsub+'</span><span class="mm-src"'+(r.polyGeld===false?' title="Poly liefert hier nur einen d\u00fcnnen Preis, kein Geld \u2014 z\u00e4hlt deshalb nicht als Quelle"':'')+'>'+(r.nSources||0)+' / 3'+(r.polyGeld===false?' \u00b7 Poly nur Preis':'')+'</span></div>'
      +'</div>';
  }

  function _mmTracking(rec){
    if(!rec||!rec.byVerdict||!Object.keys(rec.byVerdict).length)
      return '<div class="mm-empty">Noch keine abgerechneten Fälle. Das Tracking füllt sich, sobald Konsens-Spiele fertig sind.</div>';
    var lab={konsens:'✅ Konsens',teil:'➖ teils einig',uneinig:'⚠️ Divergenz'};
    var P=function(x){return x!=null?Math.round(x*100)+'%':'—';};
    var C=function(x){return x!=null?(x>=0.55?'#3fb950':x<0.45?'#f85149':'#e3b341'):'#8b949e';};
    // 01.09.2026 (Lucas: „was macht das besser als die Money Map?"). Beim Vergleich mit der
    // Konjunktion fiel auf: diese Tabelle zeigte NUR Trefferquoten. „81% bei stark" klingt
    // grossartig und sagt nichts ueber Geld — das Geld liegt auf Favoriten, eine hohe
    // Trefferquote ist dort der Normalfall. Seit 01.09. schreibt der Ledger die Quote der
    // Geld-Seite mit (Einstieg + letzte), also steht hier die RENDITE daneben — immer mit
    // Untergrenze, nie als nackter Punktschaetzer.
    // Alt-Zeilen tragen keine Quote: `nRoi` sagt, auf wie vielen Zeilen die Rendite wirklich
    // steht. Ohne diese Zahl saehe ein ROI aus 4 Zeilen aus wie einer aus 900.
    var R=function(x){return x!=null?((x>=0?'+':'')+Math.round(x*100)+'%'):'—';};
    var RC=function(lb){return lb==null?'#8b949e':(lb>0?'#3fb950':'#e3b341');};
    var geld=function(b){
      if(!b.nRoi) return '<td class="mm-cn mm-mut" title="Zeilen von vor dem 01.09.2026 tragen keine Quote — sie zaehlen in die Trefferquote, aber nicht in die Rendite.">sammelt</td>';
      return '<td class="mm-cn" style="color:'+RC(b.roiLb)+';font-weight:800" title="Rendite zum Einstiegspreis, mit einseitiger 95%-Untergrenze. Gruen erst, wenn die Untergrenze ueber null liegt.">'
        +R(b.roi)+' <span class="mm-mut" style="font-size:10px;font-weight:600">UG '+R(b.roiLb)+' · n'+b.nRoi+'</span></td>';
    };
    var rows=['konsens','teil','uneinig'].filter(function(k){return rec.byVerdict[k];}).map(function(k){
      var b=rec.byVerdict[k];
      return '<tr><td>'+lab[k]+'</td><td class="mm-cn">'+b.n+'</td>'
        +'<td class="mm-cn" style="color:'+C(b.hitRate)+';font-weight:800">'+P(b.hitRate)+'</td>'
        +geld(b)
        +'<td class="mm-cn" style="color:'+C(b.polyHitRate)+'">'+P(b.polyHitRate)+(b.polyN?' <span class="mm-mut" style="font-size:10px">n'+b.polyN+'</span>':'')+'</td>'
        +'<td class="mm-cn mm-mut">'+P(b.pinnHitRate)+'</td></tr>';
    }).join('');
    var dv=rec.divergence||{}, duel='';
    if(dv.n){
      var lead=(dv.betfairRate!=null&&dv.polyRate!=null)?(dv.betfairRate>dv.polyRate?'💷 Betfair-Geld':dv.polyRate>dv.betfairRate?'🔵 Poly':'Gleichstand'):null;
      duel='<div style="background:linear-gradient(180deg,#171e28,#141a23);border:1px solid #263041;border-radius:12px;padding:13px 15px;margin:0 0 16px">'
        +'<div style="font-size:12.5px;color:#c9d3e0;margin-bottom:10px">⚔️ <b>Bei Divergenz</b> — wer trifft, wenn Betfair-Geld &amp; Poly sich <b>uneinig</b> sind? <span class="mm-mut">('+dv.n+' Fälle)</span></div>'
        +'<div style="display:flex;gap:26px;align-items:baseline">'
        +'<div><div class="mm-mut" style="font-size:11px">💷 Betfair-Geld</div><div style="font-size:21px;font-weight:800;color:'+C(dv.betfairRate)+'">'+P(dv.betfairRate)+' <span class="mm-mut" style="font-size:11px;font-weight:600">'+(dv.betfairWins||0)+'/'+(dv.n||0)+'</span></div></div>'
        +'<div><div class="mm-mut" style="font-size:11px">🔵 Poly</div><div style="font-size:21px;font-weight:800;color:'+C(dv.polyRate)+'">'+P(dv.polyRate)+' <span class="mm-mut" style="font-size:11px;font-weight:600">'+(dv.polyWins||0)+'/'+(dv.polyN||0)+'</span></div></div>'
        +'</div>'
        +(lead&&lead!=='Gleichstand'?'<div style="font-size:11.5px;color:#8a95ad;margin-top:9px">→ <b style="color:#c9d3e0">'+lead+'</b> liegt bei Divergenz vorn'+(dv.n<8?' · <span style="color:#e3b341">noch kleine Stichprobe</span>':'')+'</div>':'')
        +'</div>';
    }
    var lgs=rec.byLeague||{}, lgK=Object.keys(lgs).slice(0,12);
    var lgRows=lgK.map(function(lg){var L=lgs[lg];
      return '<tr><td>'+_esc(lg)+'</td><td class="mm-cn">'+L.n+'</td><td class="mm-cn" style="color:'+C(L.hitRate)+';font-weight:700">'+P(L.hitRate)+'</td></tr>';}).join('');
    var lgSec=lgRows?('<div style="font-size:12px;font-weight:700;color:#9aa4b1;margin:20px 0 8px">🏆 Nach Liga <span class="mm-mut" style="font-weight:400">— folgt man dem Betfair-Geld</span></div>'
      +'<table class="mm-tbl"><thead><tr><th>Liga</th><th class="mm-cn">n</th><th class="mm-cn">Geld trifft</th></tr></thead><tbody>'+lgRows+'</tbody></table>'):'';
    var bs=rec.byStrength||{}, bsSec='';
    if((bs.strong&&bs.strong.n)||(bs.weak&&bs.weak.n)){
      var srow=function(lab,o){return (o&&o.n)?'<tr><td>'+lab+'</td><td class="mm-cn">'+o.n+'</td><td class="mm-cn" style="color:'+C(o.hitRate)+';font-weight:700">'+P(o.hitRate)+'</td></tr>':'';};
      bsSec='<div style="font-size:12px;font-weight:700;color:#9aa4b1;margin:20px 0 8px">💪 Signal-Stärke <span class="mm-mut" style="font-weight:400">— beide Geld-Seiten ≥ 55 % = stark</span></div>'
        +'<table class="mm-tbl"><thead><tr><th>Stärke</th><th class="mm-cn">n</th><th class="mm-cn">Geld trifft</th></tr></thead><tbody>'
        +srow('🔥 Stark',bs.strong)+srow('· Schwach',bs.weak)+'</tbody></table>';
    }
    var gms=(rec.recent||[]).slice(0,25).map(function(e){
      var vb=e.verdict==='konsens'?'✅':e.verdict==='uneinig'?'⚠️':'➖';
      var sc=(e.ftScore&&e.ftScore.length===2)?e.ftScore[0]+':'+e.ftScore[1]:'';
      var res=e.moneyWin?'<span style="color:#3fb950">✓</span>':'<span style="color:#f85149">✗</span>';
      var duelTag='';
      if(e.verdict==='uneinig')
        duelTag=(e.moneyWin?'<b style="color:#3fb950">Betfair ✓</b>':e.polyWin?'<b style="color:#58a6ff">Poly ✓</b>':'<span class="mm-mut">beide daneben</span>');
      return '<div style="display:flex;align-items:baseline;gap:8px;padding:7px 2px;border-bottom:1px solid #1b2430;font-size:12.5px">'
        +'<span>'+vb+'</span><span style="flex:1;color:#c9d3e0">'+_esc((e.home||'')+' – '+(e.away||''))+'</span>'
        +'<span class="mm-mut" style="font-size:11px">'+_esc(e.moneyName||e.moneySide||'')+'</span>'
        +'<span style="min-width:46px;text-align:right">'+res+' '+sc+'</span></div>'
        +(duelTag?'<div style="font-size:11px;margin:-2px 0 5px 24px">'+duelTag+'</div>':'');
    }).join('');
    var gmSec=gms?('<div style="font-size:12px;font-weight:700;color:#9aa4b1;margin:20px 0 8px">🕐 Letzte Spiele <span class="mm-mut" style="font-weight:400">('+(rec.recent||[]).length+')</span></div><div>'+gms+'</div>'):'';
    var g=rec.global||{};
    return '<div class="mm-trk-intro">Folgt man der <b>Betfair-Geld-Seite</b>: schlägt <b>Konsens</b> die uneinigen Fälle? <b>Poly</b> = Trefferquote der Poly-Seite, <b>Pinn</b> = die des scharfen Favoriten (wo ein Odds-Anker da ist).<br><b>„trifft" ist nicht „zahlt":</b> das Geld liegt auf Favoriten, eine hohe Trefferquote ist dort normal. Erst die <b>Rendite</b> (zum Einstiegspreis, mit Untergrenze) sagt, ob Folgen sich lohnt — sie sammelt seit 01.09.2026.</div>'
      +duel
      +'<table class="mm-tbl"><thead><tr><th>Verdikt</th><th class="mm-cn">n</th><th class="mm-cn">trifft</th><th class="mm-cn">Rendite</th><th class="mm-cn">Poly</th><th class="mm-cn">Pinn</th></tr></thead><tbody>'+rows+'</tbody></table>'
      +bsSec+lgSec+gmSec
      +'<div class="mm-trk-foot">Gesamt: '+(g.n||0)+' abgerechnet · '+(rec.pending||0)+' offen · Poly-Seite = die von Polymarket favorisierte Seite</div>';
  }

  function _mmRender(){
    var p=document.getElementById('moneyMapPanel'); if(!p) return;
    var head='<div class="mm-head"><span class="mm-ic">🔗</span><h1>Money Map</h1>'
      +'<span class="mm-sub">Betfair · Poly · Pinnacle — wo das Geld liegt und ob die scharfe Linie mitzieht. Nur Fußball.</span></div>';
    var nav='<div class="mm-nav"><button class="mm-nb'+(_mmView==='map'?' on':'')+'" onclick="_mmSet(\'map\')">🗺️ Map</button>'
      +'<button class="mm-nb'+(_mmView==='tracking'?' on':'')+'" onclick="_mmSet(\'tracking\')">📈 Tracking</button></div>';
    var body;
    if(_mmView==='tracking'){ body=_mmTracking(_mm.rec); }
    else {
      var allRows=(_mm.map&&_mm.map.rows)||[];
      var nLive=allRows.filter(function(r){return r.live;}).length, nPre=allRows.length-nLive;
      var chip=function(f,lab,n){return '<button class="mm-fb'+(_mmFilter===f?' on':'')+'" onclick="_mmSetF(\''+f+'\')">'+lab+' <span style="opacity:.6">'+n+'</span></button>';};
      var filt='<div class="mm-filt"><span class="mm-fl">Zeige</span>'+chip('all','Alle',allRows.length)+chip('pre','Pre',nPre)+chip('live','● Live',nLive)+'</div>';
      var rows=allRows.filter(function(r){return _mmFilter==='all'?true:_mmFilter==='live'?!!r.live:!r.live;});
      var grid=rows.length?'<div class="mm-grid">'+rows.map(_mmCard).join('')+'</div>'
        :'<div class="mm-empty">'+(_mmFilter==='live'?'Gerade kein Live-Spiel mit Geld.':_mmFilter==='pre'?'Gerade kein Vor-Spiel mit Geld.':'Gerade kein Fußballspiel mit genug Geld. Füllt sich, sobald auf Betfair oder Poly Volumen aufläuft.')+'</div>';
      body=filt+grid;
    }
    var _ageH=_mmAgeH(), _stale=(_ageH!=null&&_ageH>3);
    var banner=_stale?'<div style="background:rgba(201,133,0,.12);border:1px solid rgba(201,133,0,.4);color:#e3b341;border-radius:9px;padding:9px 12px;margin:0 0 12px;font-size:12.5px">⚠️ Daten veraltet — Stand vor '+(_ageH>=24?Math.round(_ageH/24)+' Tg':Math.round(_ageH)+'h')+'. Der Runner steht evtl.; „● Live“ kann beendete Spiele zeigen.</div>':'';
    p.innerHTML=head+nav+banner+body;
  }
  function _mmSet(v){ if(v===_mmView) return; _mmView=v; _mmRender(); }
  function _mmSetF(f){ if(f===_mmFilter) return; _mmFilter=f; _mmRender(); }
  if(typeof window!=='undefined'){ window._mmSet=_mmSet; window._mmSetF=_mmSetF; }

  function initMoneyMap(){
    _mmStyle();
    var p=document.getElementById('moneyMapPanel'); if(!p) return;
    if(!_mm.map) p.innerHTML='<div class="mm-loading">🔗 Lade Money Map…</div>';
    var b='?t='+Date.now();
    var jf=function(u){return fetch(u+b,{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;});};
    Promise.all([jf('money_map.json'),jf('money_map_record.json')]).then(function(res){ _mm.map=res[0]; _mm.rec=res[1]; _mmRender(); });
  }
  if(typeof window!=='undefined') window.initMoneyMap=initMoneyMap;
  if(typeof window!=='undefined'){ window._mmCardHtml=_mmCard; window._mmEnsureStyle=_mmStyle; }

})();
