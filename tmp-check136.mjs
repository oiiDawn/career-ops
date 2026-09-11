import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { load } from 'js-yaml';
const t=readFileSync('reports/136-state-street-agentic-engineering-2026-09-11.md','utf8');
console.log('sha256', createHash('sha256').update(t).digest('hex'));
console.log('headings', [...t.matchAll(/^## (.+)$/gm)].map(m=>m[1]));
const f=t.match(/## Machine Summary\s*\n+```(?:yaml|yml)\s*\n([\s\S]*?)\n```/);
const s=f?load(f[1]):null;
console.log('model', s?.scoring_model, 'score', s?.score, 'jd_src', s?.jd_source);
for(const src of s?.sources||[]){
  const h=createHash('sha256').update(readFileSync(src.path)).digest('hex');
  console.log(src.id, h===src.sha256?'OK':'MISMATCH', src.path);
}
const w=s?.sources.find(x=>x.id==='profile')?null:null;
// verify attractiveness vs recompute
const pr=load(readFileSync(s.sources.find(x=>x.id==='profile').path));
const W=pr.attractiveness.weights; let lo=0,up=0,cov=0;
for(const k of ['direction','compensation','team','company']){const sc=s.dimensions[k].score; lo+=W[k]*(sc??1); up+=W[k]*(sc??5); if(sc!==null)cov+=W[k];}
console.log('computed', lo.toFixed(2), up.toFixed(2), (cov*100).toFixed(4)+'%');
console.log('yaml-attr', JSON.stringify(s.attractiveness));
const label=`**入职吸引力：** ${lo.toFixed(2)}–${up.toFixed(2)}/5；证据覆盖率：${Number((cov*100).toFixed(4))}%`;
const lines=t.split('\n').filter(l=>l.includes('入职吸引力：'));
console.log('label-lines', lines.length, JSON.stringify(lines[0]));
console.log('label-match', lines.length===1 && lines[0]===label);
