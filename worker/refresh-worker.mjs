/**
 * HouseLens protected one-tap refresh bridge.
 * Deploy on Cloudflare Workers (free tier). Never place a GitHub token in Pages.
 * Settings (Worker secrets): GITHUB_TOKEN, REFRESH_ACCESS_CODE.
 * Public config: your Worker URL goes in web/refresh-config.js.
 */
const ORIGIN = 'https://kristina-abrahamyan.github.io';
const OWNER = 'kristina-abrahamyan';
const REPO = 'houselens';
const WORKFLOW = 'refresh.yml';
const API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`;
const COOLDOWN_MS = 10 * 60 * 1000;

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-HouseLens-Access',
    'Access-Control-Max-Age': '600',
    'Cache-Control': 'no-store',
    'Vary': 'Origin',
    'Content-Type': 'application/json; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
  };
}
function json(payload, status, origin) {
  return new Response(JSON.stringify(payload), {status, headers:corsHeaders(origin)});
}
function fixedTimeEqual(a,b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const u = new TextEncoder().encode(a),v = new TextEncoder().encode(b);
  let diff = u.length ^ v.length;
  for(let i=0;i<Math.max(u.length,v.length);i++)diff |= (u[i]||0) ^ (v[i]||0);
  return diff === 0;
}
async function github(path, env, method='GET', body=null) {
  const res=await fetch(path, {
    method,
    headers:{
      'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
      'Accept':'application/vnd.github+json',
      'X-GitHub-Api-Version':'2022-11-28',
      'User-Agent':'HouseLens-refresh-bridge',
      ...(body===null?{}:{'Content-Type':'application/json'}),
    },
    ...(body===null?{}:{body:JSON.stringify(body)}),
  });
  if (!res.ok) throw new Error(`GitHub API rejected the request (HTTP ${res.status}). Check that your fine-grained token has Actions: Read and write permission for houselens.`);
  return res.status===204 ? null : res.json();
}

async function handle(request, env) {
  const origin = request.headers.get('Origin') || '';
  // CORS is not authentication; a private access code is also required.
  if (origin !== ORIGIN) return json({error:'This endpoint only accepts the HouseLens website.'},403,ORIGIN);
  const url=new URL(request.url);
  if (request.method==='OPTIONS')return new Response(null,{status:204,headers:corsHeaders(ORIGIN)});
  if (!['/refresh','/status'].includes(url.pathname))return json({error:'Not found'},404,ORIGIN);
  if (!env.GITHUB_TOKEN || !env.REFRESH_ACCESS_CODE || env.REFRESH_ACCESS_CODE.length<16)
    return json({error:'The protected refresh service has not been configured correctly.'},503,ORIGIN);
  if (!fixedTimeEqual(request.headers.get('X-HouseLens-Access'),env.REFRESH_ACCESS_CODE))
    return json({error:'Incorrect refresh access code.'},401,ORIGIN);
  if (request.method==='POST' && url.pathname==='/refresh') {
    let input;
    try { input=await request.json(); } catch{return json({error:'Invalid request.'},400,ORIGIN);}
    if (!input || typeof input.listings!=='boolean')return json({error:'Invalid refresh options.'},400,ORIGIN);
    try {
      const info=await github(`${API}/runs?per_page=5`,env);
      const runs=info?.workflow_runs || [];
      const inProgress=runs.find(r=>['queued','in_progress','waiting','requested','pending'].includes(r.status));
      if (inProgress) return json({error:'An update is already running. Check the latest published data shortly.',runUrl:inProgress.html_url},409,ORIGIN);
      const recent=runs.find(r=>r.event==='workflow_dispatch' && Date.now()-Date.parse(r.created_at)<COOLDOWN_MS);
      if (recent) return json({error:'A manual refresh was requested recently. Please allow ten minutes before requesting another.',runUrl:recent.html_url},429,ORIGIN);
      const dispatched=await github(`${API}/dispatches`,env,'POST',{
        ref:'main', inputs:{refresh_listings:String(input.listings)},
      });
      return json({accepted:true,runId:dispatched?.workflow_run_id||null,runUrl:dispatched?.html_url||null,message:'New data collection requested. It will appear after GitHub finishes publishing.'},202,ORIGIN);
    } catch(error) {return json({error:error.message || 'Could not contact GitHub.'},502,ORIGIN);}
  }
  if (request.method==='GET' && url.pathname==='/status') {
    const runId=url.searchParams.get('runId');
    if (runId!==null && !/^[1-9][0-9]{0,15}$/.test(runId))
      return json({error:'Invalid workflow run identifier.'},400,ORIGIN);
    try {
      const r=runId
        ? await github(`https://api.github.com/repos/${OWNER}/${REPO}/actions/runs/${runId}`,env)
        : (await github(`${API}/runs?per_page=10`,env))?.workflow_runs?.find(run=>run.event==='workflow_dispatch');
      if(!r)return json({status:'none'},200,ORIGIN);
      return json({status:r.status,conclusion:r.conclusion,createdAt:r.created_at,runId:r.id,runUrl:r.html_url},200,ORIGIN);
    } catch(error){return json({error:error.message || 'Could not get workflow status.'},502,ORIGIN);}
  }
  return json({error:'Method not allowed'},405,ORIGIN);
}
export default { async fetch(request,env){return handle(request,env);} };
export { handle, fixedTimeEqual };
