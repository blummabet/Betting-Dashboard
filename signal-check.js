/* signal-check.js — „Analyse"-Tab (Signal-Check) im Dashboard (06.07.2026, Lucas).
   Liest das vorgerechnete signal_check.json (signal_check.py --batch) und lässt den Nutzer
   Spiel + Tipp wählen → zeigt die Signal-Bilanz. STRIKT isoliert: reines Content-Feature,
   nie ein BET/ABWÄGEN-Verdict, unabhängig von Picks/Tracking. */
var _signalCheckLoaded = false;
var _scData = null;

var _SC_ICONS = {
  "die Formkurve":"📈","die Spieler-Ratings":"📋","die xG-Werte":"⚡","die Chancenqualität":"🎨",
  "die Reisebelastung":"✈️","die Höhenlage":"⛰️","die Aufstellung":"🧩","Ausfälle/Sperren":"🩹",
  "der Tabellendruck":"🎯","die Anreizlage":"🎲","der Ligadruck":"🔥","der Direktvergleich":"⚔️",
  "das externe Prognosemodell":"🤖","das Wetter":"🌡️","die aktuelle Serie":"🔗","die Torjäger-Form":"🥅",
  "der Trainerwechsel":"🔄","Kader-Abgänge":"📦","die Termindichte":"🗓️","die Pinnacle-Bewegung":"📊",
  "der Steam-Move":"💨","die Frische der Bewegung":"🌬️","das Smart Money":"🐋","der Polymarket-Fluss":"🌊",
  "der Public-Bias":"👥"
};

function _scStyles() {
  if (document.getElementById('scStyles')) return;
  var css = `
  #signalCheckPanel .sc-wrap{max-width:900px;margin:0 auto;}
  #signalCheckPanel .sc-crown{display:inline-block;padding:6px 14px;border:1px solid rgba(125,211,252,.22);
    border-radius:999px;font-size:11px;letter-spacing:3px;color:#7dd3fc;margin-bottom:12px;}
  #signalCheckPanel h2.sc-h{font-size:26px;font-weight:800;margin:0 0 6px;letter-spacing:-.5px;color:#f0f4f8;}
  #signalCheckPanel .sc-sub{color:#8b949e;font-size:14px;margin:0 0 22px;}
  #signalCheckPanel .sc-controls{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px;}
  #signalCheckPanel .sc-controls select{background:#14204a;color:#f0f4f8;border:1.5px solid rgba(125,211,252,.22);
    border-radius:12px;padding:11px 14px;font-size:15px;font-weight:600;flex:1;min-width:200px;cursor:pointer;}
  #signalCheckPanel .sc-match{background:rgba(125,211,252,.06);border:1.5px solid rgba(125,211,252,.22);
    border-radius:18px;padding:20px 24px;margin-bottom:20px;}
  #signalCheckPanel .sc-mline{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
  #signalCheckPanel .sc-teams{font-size:22px;font-weight:700;color:#f0f4f8;}
  #signalCheckPanel .sc-teams .vs{color:#8b949e;font-size:14px;font-weight:500;}
  #signalCheckPanel .sc-meta{color:#8b949e;font-size:13px;}
  #signalCheckPanel .sc-pickrow{margin-top:16px;padding-top:16px;border-top:1px solid rgba(125,211,252,.22);
    display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;}
  #signalCheckPanel .sc-plabel{font-size:11px;letter-spacing:2px;color:#7dd3fc;font-weight:700;}
  #signalCheckPanel .sc-pmkt{font-size:22px;font-weight:800;color:#fbbf24;margin-top:2px;}
  #signalCheckPanel .sc-tally{text-align:right;}
  #signalCheckPanel .sc-tally .big{font-size:28px;font-weight:800;color:#7dd3fc;}
  #signalCheckPanel .sc-tally .small{font-size:12px;color:#8b949e;}
  #signalCheckPanel .sc-reason{background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.3);
    border-radius:14px;padding:13px 16px;font-size:15px;margin-bottom:22px;color:#f0f4f8;}
  #signalCheckPanel .sc-gh{font-size:12px;letter-spacing:2px;color:#8b949e;font-weight:700;margin:0 0 10px;text-transform:uppercase;}
  #signalCheckPanel .sc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:20px;}
  #signalCheckPanel .sc-card{background:rgba(125,211,252,.06);border:1px solid rgba(125,211,252,.22);
    border-radius:14px;padding:13px 15px;}
  #signalCheckPanel .sc-card.pos{border-color:rgba(74,222,128,.35);background:rgba(74,222,128,.06);}
  #signalCheckPanel .sc-card.neg{border-color:rgba(248,113,113,.35);background:rgba(248,113,113,.06);}
  #signalCheckPanel .sc-card.silent{opacity:.4;}
  #signalCheckPanel .sc-card .top{display:flex;align-items:center;gap:8px;}
  #signalCheckPanel .sc-card .ico{font-size:19px;}
  #signalCheckPanel .sc-card .nm{font-size:13px;font-weight:700;color:#f0f4f8;}
  #signalCheckPanel .sc-card .mk{margin-left:auto;font-size:15px;font-weight:800;}
  #signalCheckPanel .sc-card.pos .mk{color:#4ade80;}
  #signalCheckPanel .sc-card.neg .mk{color:#f87171;}
  #signalCheckPanel .sc-card .desc{font-size:11px;color:#8b949e;line-height:1.4;margin-top:3px;}
  #signalCheckPanel .sc-disc{color:#8b949e;font-size:12px;text-align:center;margin-top:8px;
    border-top:1px solid rgba(125,211,252,.22);padding-top:14px;}`;
  var st = document.createElement('style');
  st.id = 'scStyles'; st.textContent = css;
  document.head.appendChild(st);
}

function initSignalCheck() {
  var panel = document.getElementById('signalCheckPanel');
  if (!panel) return;
  _scStyles();
  if (_signalCheckLoaded) return;
  _signalCheckLoaded = true;
  panel.innerHTML = '<p style="color:#8b949e;text-align:center;padding:40px">🔎 Lade Signal-Analyse…</p>';
  fetch('signal_check.json?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (d) { _scData = d; _scBuild(panel); });
}

function _scBuild(panel) {
  if (!_scData || !(_scData.games || []).length) {
    panel.innerHTML = '<p style="color:#8b949e;text-align:center;padding:40px">Keine Analyse-Daten verfügbar.</p>';
    return;
  }
  var markets = (_scData._meta && _scData._meta.markets) || [];
  var gOpts = _scData.games.map(function (g, i) {
    return '<option value="' + i + '">' + (g.homeFlag || '') + ' ' + g.home + ' – ' + g.away +
           ' ' + (g.awayFlag || '') + '  ·  ' + g.round + '</option>';
  }).join('');
  var mOpts = markets.map(function (m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
  panel.innerHTML =
    '<div class="sc-wrap">' +
    '<div class="sc-crown">SIGNAL-CHECK</div>' +
    '<h2 class="sc-h">Was sagen unsere Signale zu diesem Tipp?</h2>' +
    '<p class="sc-sub">Spiel und Tipp wählen — die Engine feuert alle Signale dagegen. Reine Analyse, kein Wettaufruf.</p>' +
    '<div class="sc-controls"><select id="scGame">' + gOpts + '</select>' +
    '<select id="scMarket">' + mOpts + '</select></div>' +
    '<div id="scView"></div></div>';
  document.getElementById('scGame').addEventListener('change', _scRender);
  document.getElementById('scMarket').addEventListener('change', _scRender);
  _scRender();
}

function _scCard(s, dir) {
  var ico = _SC_ICONS[s.label] || '•';
  var mk = dir === 'pos' ? '✅' : dir === 'neg' ? '❌' : '⚪';
  return '<div class="sc-card ' + dir + '"><div class="top"><span class="ico">' + ico + '</span>' +
         '<span class="nm">' + s.label + '</span><span class="mk">' + mk + '</span></div>' +
         (s.evidence ? '<div class="desc">' + s.evidence + '</div>' : '') + '</div>';
}

function _scRender() {
  var gi = document.getElementById('scGame').value;
  var mkt = document.getElementById('scMarket').value;
  var g = _scData.games[gi];
  var m = g && g.markets[mkt];
  var view = document.getElementById('scView');
  if (!m) { view.innerHTML = '<p style="color:#8b949e">Für diesen Markt liegt keine Analyse vor.</p>'; return; }
  var dec = (m.score && m.score.decisive) || 0;
  var conf = (m.score && m.score.confirm) || 0;
  var html =
    '<div class="sc-match"><div class="sc-mline">' +
    '<div class="sc-teams">' + (g.homeFlag || '') + ' ' + g.home + ' <span class="vs">vs</span> ' +
    (g.awayFlag || '') + ' ' + g.away + '</div>' +
    '<div class="sc-meta">' + g.round + (g.date ? ' · ' + g.date : '') + '</div></div>' +
    '<div class="sc-pickrow"><div><div class="sc-plabel">GEPRÜFTER TIPP</div>' +
    '<div class="sc-pmkt">' + (m.tip || mkt) + '</div></div>' +
    '<div class="sc-tally"><div class="big">' + conf + '/' + dec + '</div>' +
    '<div class="small">klare Signale dafür</div></div></div></div>';
  html += '<div class="sc-reason">' + (m.reason || '') + '</div>';
  var fired = (m.confirm || []).map(function (s) { return _scCard(s, 'pos'); }).join('') +
              (m.contradict || []).map(function (s) { return _scCard(s, 'neg'); }).join('') +
              (m.neutral || []).map(function (s) { return _scCard(s, 'silent'); }).join('');
  html += '<p class="sc-gh">Signale, die feuern</p><div class="sc-grid">' + (fired || '<span style="color:#8b949e">—</span>') + '</div>';
  var sil = (m.silent || []).map(function (s) {
    return '<div class="sc-card silent"><div class="top"><span class="ico">' + (_SC_ICONS[s.label] || '•') +
           '</span><span class="nm">' + s.label + '</span><span class="mk">⚪</span></div></div>';
  }).join('');
  if (sil) html += '<p class="sc-gh">Stumm — kein Signal (z.B. kein Markt-Move)</p><div class="sc-grid">' + sil + '</div>';
  var disc = (_scData._meta && _scData._meta.disclaimer) || 'Reine Signal-Analyse — kein Wettaufruf.';
  html += '<div class="sc-disc">' + disc + '</div>';
  view.innerHTML = html;
}
