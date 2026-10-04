import { chromium } from '@playwright/test';
import { readFileSync, mkdirSync, mkdtempSync, statSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const biUrl = process.env.RETAILPULSE_BI_URL || 'http://127.0.0.1:4173/retailpulse/';
const localUrl = process.env.RETAILPULSE_STREAMLIT_URL || 'http://127.0.0.1:8501';
const dataDir = process.env.RETAILPULSE_RECORD_DATA_DIR;
if (!dataDir) throw new Error('RETAILPULSE_RECORD_DATA_DIR must name the running Streamlit demo data directory.');
const seconds = Number(process.env.RETAILPULSE_WALKTHROUGH_PHASE_SECONDS || '28');
if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 45) throw new Error('Phase duration must be positive and at most 45 seconds.');
const output = resolve(process.env.RETAILPULSE_WALKTHROUGH_OUTPUT || join(root, 'docs/assets/retailpulse-walkthrough.mp4'));
const temporary = mkdtempSync(join(tmpdir(), 'retailpulse-walkthrough-'));
const e2e = JSON.parse(readFileSync(join(root, 'docs/evidence/local-e2e.json'), 'utf8'));
const cloud = JSON.parse(readFileSync(join(root, 'docs/evidence/cloud-monitor-preflight.json'), 'utf8'));
const monitor = JSON.parse(readFileSync(join(root, 'docs/evidence/local-monitoring.json'), 'utf8'));
const snapshot = JSON.parse(readFileSync(join(root, 'bi-dashboard/public/data/dashboard.json'), 'utf8'));
const current = JSON.parse(execFileSync(process.env.RETAILPULSE_PYTHON_BIN || join(root, '.venv313/bin/python'), ['-c', `
import json, sqlite3, sys
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1], 'retailpulse.db').resolve().as_uri() + '?mode=ro', uri=True) as connection:
    orders, revenue, aov = connection.execute('SELECT COUNT(*), ROUND(SUM(order_total),2), ROUND(AVG(order_total),2) FROM fact_orders').fetchone()
    events = dict(connection.execute('SELECT event_type, COUNT(*) FROM silver_events GROUP BY event_type'))
    print(json.dumps({'orders':orders, 'revenue':revenue, 'aov':aov, 'events':events, 'silver':sum(events.values())}))
`, dataDir], { encoding: 'utf8' }));
const pounds = (value) => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP'}).format(Number(value));
const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const metric = (label, value, note='') => `<article><small>${escape(label)}</small><strong>${escape(value)}</strong><p>${escape(note)}</p></article>`;
const columns = (contents) => `<div class="columns">${contents}</div>`;
const proof = (eyebrow, title, subtitle, contents) => `<!doctype html><html><head><meta charset="utf-8"><title>RetailPulse verified local evidence</title><style>
*{box-sizing:border-box}body{margin:0;background:#07111f;color:#eaf2fb;font-family:Arial,sans-serif}main{padding:38px 48px 140px}header{display:flex;justify-content:space-between;align-items:center;color:#8ea3bb;font-size:15px}header b{color:#4bd4a0;letter-spacing:1px}header span{padding:8px 12px;border:1px solid #294158;border-radius:20px}.eyebrow{color:#5caeff;font-size:13px;letter-spacing:2px;text-transform:uppercase;margin:38px 0 10px}h1{font-size:37px;margin:0 0 14px}h2{font-size:20px;margin:0 0 16px}.lead{font-size:18px;line-height:1.5;color:#b4c6d8;max-width:1080px;margin-bottom:27px}.columns{display:flex;gap:18px}.columns>article,.columns>section{flex:1;min-width:0;padding:21px;background:#0e1c2d;border:1px solid #26394e;border-radius:15px}article small{display:block;font-size:14px;color:#8ea3bb}article strong{display:block;font-size:32px;margin:12px 0;color:#fff}p{font-size:16px;line-height:1.5;color:#aec1d5}.path{font-size:24px;letter-spacing:1px;line-height:1.7;color:#4bd4a0;padding:20px;border:1px solid #294158;border-radius:12px;background:#0b1726}.note{margin-top:20px;font-size:16px;color:#ffcf96}table{width:100%;border-collapse:collapse;font-size:17px;background:#0e1c2d;border-radius:12px;overflow:hidden}td,th{text-align:left;padding:13px 18px;border-bottom:1px solid #26394e}th{color:#5caeff;font-weight:normal}pre{white-space:pre-wrap;font-size:16px;line-height:1.55;color:#d4e9fc;margin:0}footer{margin-top:20px;font-size:13px;color:#8ea3bb}
</style></head><body><main><header><b>RETAILPULSE / VERIFIED FIELD NOTES</b><span>Cloud refresh pending · local release</span></header><div class="eyebrow">${escape(eyebrow)}</div><h1>${escape(title)}</h1><div class="lead">${escape(subtitle)}</div>${contents}</main></body></html>`;
const pages = {
  intro: proof('Portfolio walkthrough', 'Retail data, from events to trusted decisions.', 'A five-minute silent tour of the actual dashboards and recorded verification evidence. Archived Azure business data and the current local demo are distinct datasets.',
    `<div class="path">Producer → Bronze → validated Silver → Gold marts → BI</div>`+columns(metric('Saved Azure archive', pounds(snapshot.kpis.revenue), 'Exported '+snapshot.metadata.generatedAt.slice(0,10)+' · historical 2010–2011 sales')+metric('Current local demo', pounds(current.revenue), current.orders+' orders · '+current.silver+' Silver events')+metric('Release boundary', 'Local verified', 'Azure target Disabled · cloud alert delivery unverified'))),
  scenarios: proof('Local pipeline evidence', 'Replay protection, quarantine, and late data.', 'These counts come from the recorded isolated end-to-end baseline. A later monitoring scenario added more valid demo events; the Streamlit dashboard shows that current dataset.',
    `<table><thead><tr><th>Scenario</th><th>Read</th><th>Silver written</th><th>Duplicates</th><th>Rejected / late</th></tr></thead><tbody>${e2e.batches.map((row)=>`<tr><td>${escape(row.scenario)}</td><td>${row.records_read}</td><td>${row.records_written}</td><td>${row.records_duplicate}</td><td>${row.records_rejected} / ${row.records_late}</td></tr>`).join('')}</tbody></table><p class="note">Baseline: ${e2e.counts.bronze_events} Bronze / ${e2e.counts.silver_events} Silver / ${e2e.counts.quarantine} quarantine. Current local Silver: ${current.silver}.</p><footer>Source: docs/evidence/local-e2e.json · verified ${escape(e2e.verified_at)}</footer>`),
  dbt: proof('Gold transformation evidence', 'The same totals survive rebuilds.', 'The local analytics run executes dbt against DuckDB and verifies incremental reruns against a full refresh. Monetary totals follow the Gold penny-rounding rule.',
    columns(metric('Clean dbt build',e2e.dbt.clean.nodes_passed+' nodes passed')+metric('Incremental build',e2e.dbt.incremental.nodes_passed+' nodes passed')+metric('Full refresh',e2e.dbt.full_refresh.nodes_passed+' nodes passed'))+
    columns(`<section><h2>Executed checks</h2><p>Unchanged rerun: ${e2e.dbt.unchanged_rerun ? 'verified' : 'unverified'}<br>Full-refresh equivalence: ${e2e.dbt.full_refresh_equivalent ? 'verified' : 'unverified'}</p></section><section><h2>Gold unit-price rule</h2><pre>price.quantize(Decimal("0.01"),\n               rounding=ROUND_HALF_UP)\nquantity × rounded_unit_price\n\n2 × raw £1.005 → Gold £2.02</pre></section>`)+`<footer>Source: docs/evidence/local-e2e.json · dashboard rounding regression exercised separately</footer>`),
  monitoring: proof('Monitoring and incident evidence', 'A real local alert fired, then recovered.', 'Prometheus scraped the producer and pipeline metrics, Grafana was healthy, and the duplicate-rate rule fired during the controlled replay scenario.',
    columns(metric('Prometheus targets',monitor.targets.every((row)=>row.health==='up')?'UP':'Review',monitor.targets.map((row)=>row.job+': '+row.health).join(' · '))+metric('Grafana health',monitor.grafana_health,monitor.grafana_dashboard)+metric('Recovery',monitor.resolved_after_recovery?'Resolved':'Pending',monitor.resolved_at || ''))+
    `<div class="path">${escape(monitor.firing_alerts.join(', '))} → recovery → resolved</div><p>Incident analysis source: ${escape(e2e.incident.source)}. The report cites observed duplicate rate and recommends producer idempotency and retained event-ID deduplication.</p><footer>Sources: local-monitoring.json and local-e2e.json · all metrics shown are recorded local evidence</footer>`),
  closure: proof('Honest release boundary', 'Available portfolio UI. Bounded cloud refresh.', 'Public browser visits only read saved JSON. New Azure extraction and cloud alert delivery remain pending while the subscription is disabled.',
    columns(metric('Azure target',cloud.target.provisioning_state,'Read-only preflight · no refresh performed')+metric('Cloud alert rule',cloud.rule.status,cloud.notifications.delivery_status+' delivery · '+cloud.end_to_end_test+' end-to-end test')+metric('Refresh cleanup','Confirm STOPPED','Bounded retries/polling · failure is visible'))+
    `<div class="path">Archived Azure BI + current local operations + reproducible evidence</div><p class="note">The dashboards, browser tests, and local pipeline are demonstrated here. This recording does not claim a fresh cloud run or verified cloud notifications.</p><footer>Source: cloud-monitor-preflight.json · checked ${escape(cloud.checked_at)}</footer>`),
};
const browser = await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined});
const context = await browser.newContext({viewport:{width:1280,height:720},deviceScaleFactor:1,timezoneId:'UTC',recordVideo:{dir:temporary,size:{width:1280,height:720}}});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => { if(message.type()==='error') errors.push(message.text()); });
const caption = async (index, title, body) => page.evaluate(({index,title,body})=>{
  document.querySelector('#recording-caption')?.remove();
  const overlay=document.createElement('aside');overlay.id='recording-caption';
  overlay.style.cssText='position:fixed;z-index:2147483647;bottom:0;left:0;width:100%;padding:16px 34px 19px;background:rgba(3,12,23,.97);border-top:2px solid #4bd4a0;color:#eef7ff;font-family:Arial,sans-serif;pointer-events:none;box-sizing:border-box;';
  const heading=document.createElement('strong');heading.textContent=String(index).padStart(2,'0')+'/11 · '+title;heading.style.cssText='display:block;font-size:18px;color:#4bd4a0;margin-bottom:8px';
  const text=document.createElement('div');text.textContent=body;text.style.cssText='font-size:19px;line-height:1.4;max-width:1180px';overlay.append(heading,text);document.body.append(overlay);
}, {index,title,body});
const pause = (duration=seconds) => new Promise(resolve => setTimeout(resolve,duration*1000));
const showProof = (name) => page.setContent(pages[name], {waitUntil:'load'});
const scrollMain = async (top) => page.locator('[data-testid="stMain"]').evaluate((node,top)=>node.scrollTo({top,behavior:'smooth'}),top);
const phases = [
  ['Scope and architecture','This is a recorded local release. The public Azure snapshot is archived; the current Streamlit demo uses a separate local dataset.',async()=>{await showProof('intro');await page.screenshot({path:join(root,'docs/assets/retailpulse-walkthrough-poster.png')});}],
  ['Overview · saved Azure archive','£91,970.02 across 1,796 orders. Exported 15 Aug 2026; sales cover 2010–2011. Purchase/view ratio is independent event sampling, not buyer conversion.',async()=>{await page.goto(biUrl);await page.getByRole('heading',{name:'Commerce, without the noise.'}).waitFor();},async()=>page.evaluate(()=>window.scrollTo({top:260,behavior:'smooth'}))],
  ['Commerce · historic business window','Daily revenue, market mix, product value, and anonymous customer rankings all come from the saved aggregate snapshot.',async()=>{await page.getByRole('tab',{name:'Commerce',exact:true}).click();await page.evaluate(()=>window.scrollTo({top:290,behavior:'smooth'}));},async()=>page.evaluate(()=>window.scrollTo({top:790,behavior:'smooth'}))],
  ['Freshness · measured at export','The stream ran as a bounded demo. Inventory status and the 5/5 trust checks describe export time; they do not assert current cloud health.',async()=>{await page.getByRole('tab',{name:'Freshness',exact:true}).click();await page.evaluate(()=>window.scrollTo({top:280,behavior:'smooth'}));},async()=>page.evaluate(()=>window.scrollTo({top:600,behavior:'smooth'}))],
  ['Current local demo · separate dataset',`${pounds(current.revenue)} / ${current.orders} orders / ${current.events.product_view} view events / ${current.events.purchase} purchase events. Local business dates and run timestamps are shown explicitly.`,async()=>{await page.goto(localUrl);await page.getByRole('heading',{name:'RetailPulse Operations & Commerce',exact:true}).waitFor();await page.locator('[data-testid="stVegaLiteChart"]').first().waitFor();}],
  ['Local commerce · consistent money','Top-product revenue uses Gold unit-price rounding before multiplying quantity. The two-times-£1.005 fixture reconciles at £2.02.',async()=>scrollMain(470),async()=>scrollMain(820)],
  ['Local operations · inventory and run ledger','Inventory updates and pipeline classifications are visible here. Empty reprocessing reads zero new records; previous accepted data remains available.',async()=>scrollMain(1070),async()=>scrollMain(1550)],
  ['Evidence · controlled failure scenarios','The isolated baseline exercised normal, duplicate, malformed, late-data, and spike traffic. Quarantine and deduplication counts are recorded, not inferred.',async()=>showProof('scenarios')],
  ['Evidence · dbt reproducibility','Recorded clean, incremental, and full-refresh builds passed. Unchanged reruns and full-refresh equivalence were explicitly checked.',async()=>showProof('dbt')],
  ['Evidence · local monitoring recovery','Recorded Prometheus targets were UP, Grafana was healthy, and RetailPulseDuplicateRate fired and resolved after recovery. Incident analysis used Ollama.',async()=>showProof('monitoring')],
  ['Cloud scope · ready to review, refresh pending','Azure target is Disabled; the cloud alert rule is missing and delivery remains unverified. A new attended refresh must reconcile data and confirm STOPPED.',async()=>showProof('closure')],
];
try {
  mkdirSync(resolve(output,'..'),{recursive:true});
  for (let index=0;index<phases.length;index++) {
    const [title,body,prepare,midpoint]=phases[index];
    await prepare();await caption(index+1,title,body);
    console.log(`Phase ${index+1}/11: ${title}`);
    await pause(seconds/2);
    if(midpoint) await midpoint();
    await pause(seconds/2);
  }
  if(errors.length) throw new Error('Browser recording had errors: '+JSON.stringify(errors));
  await context.close();
  const webm=await page.video().path();
  execFileSync(process.env.FFMPEG_BIN || 'ffmpeg',['-hide_banner','-loglevel','error','-y','-i',webm,'-vf','fps=8','-c:v','libx264','-preset','medium','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart','-an',output],{stdio:'inherit'});
  const media=JSON.parse(execFileSync(process.env.FFPROBE_BIN || 'ffprobe',['-v','error','-show_entries','format=duration,size:stream=codec_name,width,height,r_frame_rate','-of','json',output],{encoding:'utf8'}));
  if(statSync(output).size>20*1024*1024) throw new Error('Walkthrough exceeds the 20 MiB artifact limit.');
  if(seconds>=28 && (Number(media.format.duration)<300 || Number(media.format.duration)>360)) throw new Error('Full walkthrough must last between five and six minutes.');
  console.log(JSON.stringify({output,webm,phases:phases.length,plannedDurationSeconds:phases.length*seconds,media,aggregateCurrentLocal:current}));
} finally {
  await browser.close();
}
