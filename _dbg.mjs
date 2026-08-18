import { readFileSync } from 'node:fs'; import { JSDOM } from 'jsdom';
const ROOT=new URL('./',import.meta.url);
function iso(ms=0){return new Date(Date.now()+ms).toISOString();}
const dom=new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',{url:'https://x.com/',runScripts:'outside-only'});
const w=dom.window; w._bfNoAutoRefresh=true;
w.eval(readFileSync(new URL('betfair-radar.js',ROOT),'utf8'));
w._bfState.data={matches:[]};
w._bfState.consensus={games:[
 {matchId:'A',home:'Alpha',away:'Beta',league:'Test Liga',live:true,kickoff:iso(-1800e3),moneySide:'home',moneyName:'Alpha',moneyOdd:1.58,moneyDir:'in',totVol:111000,pinn:{home:0.68,draw:0.2,away:0.12,fav:'home'},poly:{sharePct:60}},
 {matchId:'B',home:'Gamma',away:'Delta',league:'Test Liga',live:false,kickoff:iso(5400e3),moneySide:'home',moneyName:'Gamma',moneyOdd:1.20,moneyDir:'out',totVol:25000,pinn:{home:0.82,draw:0.12,away:0.06,fav:'home'},poly:{sharePct:40}},
]};
w._bfState.loading=false; w._bfState.view='terminal';
const h=w.document.getElementById('betfairRadarPanel').innerHTML;
console.log('len',h.length);
console.log('idx Alpha',h.indexOf('Alpha'),'idx Gamma',h.indexOf('Gamma'));
console.log('has board title', h.includes('handelbare Kanten'));
const m=h.match(/[+\-]\d+\.\d%/g); console.log('pcts',m&&m.slice(0,6));
