// Coupon manuel du testeur : méthode « la cote d'abord » (voir docs/AUDIT_COUPON_MANUEL_METHODE.md)
import fs from 'node:fs'; import { get, post } from './api.mjs';
const PLACE = process.argv.includes('--place'); const STAKE = 2000;
const EXCLUDE = /^(UCL|UEL|UECL|CL|EL|ECL|WC|WCQ|EURO|NL|CAN|AFCON|FRIENDLY|INT)/i;
const now = Date.now(), lo = now + 2*3600e3, hi = now + 36*3600e3;
const up = (await get('/predictions/upcoming')).j;
const comps = {}; up.forEach(x=>comps[x.match.competition]=(comps[x.match.competition]||0)+1); console.log('compétitions', JSON.stringify(comps));
const L = up.map(x=>x.match).filter(m=>m.status==='scheduled' && !m.api_status?.match(/H|ET|P|FT/) && Date.parse(m.kickoff_at)>lo && Date.parse(m.kickoff_at)<hi && !EXCLUDE.test(m.competition));
const pw = ps => { let a=0.5,b=3; for(let i=0;i<60;i++){const k=(a+b)/2, s=ps.reduce((t,p)=>t+p**k,0); s>1? a=k : b=k;} const k=(a+b)/2; return ps.map(p=>p**k); }; // méthode puissance
const cands = [];
for (const m of L) {
  const off = (await get(`/matches/${m.id}/offer`)).j || [];
  const g = (mk, ln) => off.filter(o=>o.market===mk && (ln==null || String(o.line)===ln));
  const x12 = g('1X2'); const ou = g('OU','2.5');
  const fair = {};
  if (x12.length===3) { const f = pw(x12.map(o=>1/o.odds)); x12.forEach((o,i)=>fair['1X2|'+o.selection]=f[i]);
    fair['DC|1X']=fair['1X2|home']+fair['1X2|draw']; fair['DC|X2']=fair['1X2|draw']+fair['1X2|away']; fair['DC|12']=fair['1X2|home']+fair['1X2|away']; }
  if (ou.length===2) { const f = pw(ou.map(o=>1/o.odds)); ou.forEach((o,i)=>fair['OU|'+o.selection]=f[i]); }
  for (const o of off) { const k = o.market+'|'+o.selection; if (!(k in fair)) continue; if (o.market==='OU' && String(o.line)!=='2.5') continue;
    const odds=+o.odds, pm=fair[k], pe=o.model_probability;
    if (odds<1.25||odds>1.70||pm<0.60||pe==null||pe<pm-0.03||pe>pm+0.10) continue;
    cands.push({ m, o, odds, pm, pe, ev: pm*odds-1 }); }
}
cands.sort((a,b)=>b.pm-a.pm);
cands.slice(0,15).forEach(c=>console.log(`${c.m.competition} ${c.m.kickoff_at.slice(5,16)} ${c.m.home_team.name}-${c.m.away_team.name} ${c.o.market}${c.o.line?' '+c.o.line:''} ${c.o.selection} @${c.odds} marché ${(c.pm*100).toFixed(0)}% moteur ${(c.pe*100).toFixed(0)}%`));
// 2 ou 3 sélections, un match chacune, championnats différents si possible, cote totale 1,80 à 3,00
const pick=[]; const used=new Set(), usedC=new Set();
for (const pass of [true,false]) for (const c of cands) { if (pick.length>=3) break; const tot=pick.reduce((t,p)=>t*p.odds,1);
  if (used.has(c.m.id) || (pass && usedC.has(c.m.competition)) || tot*c.odds>3.0) continue; pick.push(c); used.add(c.m.id); usedC.add(c.m.competition); }
const tot = pick.reduce((t,p)=>t*p.odds,1), pr = pick.reduce((t,p)=>t*p.pm,1);
console.log(`\nCOUPON ${pick.length} sélections, cote ${tot.toFixed(2)}, chance (marché) ${(pr*100).toFixed(0)} %`);
pick.forEach(c=>console.log(` - ${c.m.home_team.name}-${c.m.away_team.name} ${c.o.market} ${c.o.selection} @${c.odds}`));
if (pick.length<2 || tot<1.80) { console.log('Pas de coupon : pas assez de sélections sûres aujourd\'hui (règle : on ne force pas).'); process.exit(0); }
if (PLACE) { const r = await post('/bets', { stake: STAKE, selections: pick.map(c=>({ match_id:c.m.id, market:c.o.market, line:c.o.line??'', selection:c.o.selection, odds:c.o.odds })) });
  console.log('PLACÉ', r.status, r.j?.id, r.j?.total_odds, r.j?.potential_payout, JSON.stringify(r.j).slice(0,150));
  fs.appendFileSync('coupons_manuels.jsonl', JSON.stringify({ at:new Date().toISOString(), bet:r.j?.id, tot, pr, sel:pick.map(c=>({m:c.m.id, t:`${c.m.home_team.name}-${c.m.away_team.name}`, k:c.o.market+'|'+c.o.selection, odds:c.odds, pm:c.pm, pe:c.pe}))})+'\n'); }
