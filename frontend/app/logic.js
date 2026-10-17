
// Homerun UI logic. The markup, styling and screen flow are the design's (frontend/design/Homerun.html);
// this file only swaps its mock data for the backend: /api/ui/* (chat, match, feedback, finance,
// compare, interest, handoff, hub/viewings/photos), /api/health and /api/metrics.
// renderVals() returns exactly the keys the template already binds to.
const DEFAULT_TOWNS=['Bishan','Tampines','Queenstown','Jurong West','Punggol'];
let TOWNS=DEFAULT_TOWNS.slice();let NEARBY={};let POPULAR=DEFAULT_TOWNS.slice();
const EXAMPLE="3-bedroom under $900k near an MRT, in Bishan, Tampines or Queenstown. Short commute to Raffles Place matters more than size.";
const HERO="3-bed under $900k near an MRT in Bishan or Tampines. Short commute beats space.";
const TOK=[['3-bed','3+ bedrooms',1],['under $900k','≤ SGD 900k',1],['near an MRT','near MRT',0],['Bishan or Tampines','Bishan · Tampines',1],['Short commute','short commute',0],['beats space','space: low',0]];
const SOFT=[{k:'commute',label:'Short commute'},{k:'mrt',label:'Near MRT'},{k:'area',label:'More space'},{k:'price',label:'Under budget'}];
const k$=n=>'$'+Math.round(n/1000).toLocaleString('en-SG')+'k';
const full$=n=>'$'+Math.round(n).toLocaleString('en-SG');
const cl=x=>Math.max(0,Math.min(1,x));
const pad=n=>String(n).padStart(2,'0');
const NUM=['zero','one','two','three','four','five'];
const TONE={mint:'var(--g-mint)',butter:'var(--g-butter)',soft:'var(--soft)'};
const EMPTY={id:'',name:'—',town:'',cat:'HDB',type:'',beds:null,price:0,area:null,tenure:null,lease:null,floor:null,mrt:null,mrt_name:null,commute:null,coords:null,val:null,agent:{st:'missing'},source_url:null,fetched_at:null};
const WD=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// ---- backend client ---------------------------------------------------------------------------
const API_BASE=(()=>{try{const q=new URLSearchParams(location.search).get('api');if(q){localStorage.setItem('homerun_api',q);}return (q||localStorage.getItem('homerun_api')||'').replace(/\/$/,'');}catch(e){return '';}})();
const api={
  async req(method,path,body){
    const t0=performance.now();let r;
    try{r=await fetch(API_BASE+'/api'+path,{method,headers:body?{'content-type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});}catch(err){devcall(method,'/api'+path,performance.now()-t0,0);throw err;}
    devcall(method,'/api'+path,performance.now()-t0,r.status);
    if(r.status===204)return null;
    const j=await r.json().catch(()=>null);
    if(!r.ok){const e=new Error((j&&j.error&&j.error.message)||('HTTP '+r.status));e.status=r.status;e.code=j&&j.error&&j.error.code;throw e;}
    return j;
  },
  get(p){return api.req('GET',p);},post(p,b){return api.req('POST',p,b);},patch(p,b){return api.req('PATCH',p,b);},del(p){return api.req('DELETE',p);}
};
const SID=(()=>{try{let s=localStorage.getItem('homerun_sid');if(!s){s=(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random().toString(16).slice(2));localStorage.setItem('homerun_sid',s);}return s;}catch(e){return 'anon-'+Date.now();}})();
const ph=l=>{const u=(l&&(l.thumb||(l.photos&&l.photos[0])))||'';return {hasPhoto:!!u,photo:u};};
const utc=iso=>iso?new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso)?iso:iso+'Z'):null;
const hhmm=iso=>{const d=utc(iso);return d?pad(d.getHours())+':'+pad(d.getMinutes()):'—';};
const sayWhen=iso=>{const d=utc(iso);return d?WD[d.getDay()]+' '+pad(d.getHours())+':'+pad(d.getMinutes()):'';};
const timeAgo=iso=>{const d=utc(iso);if(!d)return 'never';const h=(Date.now()-d.getTime())/36e5;return h<1?'under 1h ago':Math.round(h)+'h ago';};

// ---- dev telemetry: every API call and voice event lands here; the Dev Mode pane draws it ----------
const DEV={calls:[],events:[]};
const AGENT_LABEL={buyer_intelligence:'buyer-intelligence',market_intelligence:'market-intelligence',valuation:'valuation',affordability_risk:'affordability',matching_decision:'matching',rules:'rule-based parse','gemini-live':'gemini-live voice'};
DEV.feed=[];const AGENT_AT={};
const devagent=(agent,ms,status,via)=>{AGENT_AT[agent]=Date.now();DEV.feed.push({t:Date.now(),agent,ms,status:status||'ok',via});if(DEV.feed.length>30)DEV.feed.shift();};
const devlog=(kind,text)=>{DEV.events.push({t:Date.now(),kind,text});if(DEV.events.length>60)DEV.events.shift();};
const devcall=(method,path,ms,status)=>{DEV.calls.push({t:Date.now(),method,path:path.split('?')[0],ms:Math.round(ms),status});if(DEV.calls.length>40)DEV.calls.shift();};

// ---- Gemini Live voice client: mic -> 16 kHz PCM16 up, 24 kHz PCM16 audio back, JSON events on the side ----
const MIC_RATE=16000,PLAY_RATE=24000,CHUNK=480;
const WORKLET_SRC=`class Capture extends AudioWorkletProcessor{constructor(){super();this.ratio=sampleRate/${MIC_RATE};this.pos=0;this.out=new Int16Array(${CHUNK});this.n=0;}
process(inputs){const ch=inputs[0]&&inputs[0][0];if(!ch)return true;while(this.pos<ch.length){const i=Math.floor(this.pos);const a=ch[i];const b=i+1<ch.length?ch[i+1]:a;const v=Math.max(-1,Math.min(1,a+(b-a)*(this.pos-i)));this.out[this.n++]=v<0?v*0x8000:v*0x7fff;if(this.n===${CHUNK}){this.port.postMessage(this.out.buffer);this.out=new Int16Array(${CHUNK});this.n=0;}this.pos+=this.ratio;}this.pos-=ch.length;return true;}}
registerProcessor('capture',Capture);`;
class VoiceClient{
  constructor(url,onEvent,onClose){this.url=url;this.onEvent=onEvent;this.onClose=onClose;this.ws=null;this.micCtx=null;this.playCtx=null;this.stream=null;this.sources=new Set();this.nextStart=0;this.closed=false;}
  async start(){
    const AC=window.AudioContext||window.webkitAudioContext;
    this.playCtx=new AC({sampleRate:PLAY_RATE,latencyHint:'interactive'});try{this.playCtx.resume();}catch(e){}
    const sock=new Promise((res,rej)=>{const ws=new WebSocket(this.url);ws.binaryType='arraybuffer';ws.onopen=()=>res();ws.onerror=()=>rej(new Error('Couldn’t connect to the voice service.'));
      ws.onmessage=m=>this.onMsg(m);ws.onclose=()=>{if(!this.closed)this.onClose();};this.ws=ws;});
    const results=await Promise.allSettled([sock,this.startMic()]);
    const bad=results.find(r=>r.status==='rejected');if(bad){this.stop();throw bad.reason;}
  }
  async startMic(){
    if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia)throw new Error('This browser can’t use the microphone here (needs https or localhost).');
    try{this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});}
    catch(e){throw new Error('Microphone access was blocked. Allow it and tap the orb again.');}
    if(this.closed)return;
    const ctx=this.micCtx=new (window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'});try{ctx.resume();}catch(e){}
    const url=URL.createObjectURL(new Blob([WORKLET_SRC],{type:'application/javascript'}));
    try{await ctx.audioWorklet.addModule(url);}finally{URL.revokeObjectURL(url);}
    if(this.closed)return;
    const src=ctx.createMediaStreamSource(this.stream);const node=new AudioWorkletNode(ctx,'capture');
    node.port.onmessage=e=>{if(this.ws&&this.ws.readyState===1)this.ws.send(e.data);};
    src.connect(node);
  }
  onMsg(m){
    if(m.data instanceof ArrayBuffer){this.enqueue(m.data);return;}
    let ev;try{ev=JSON.parse(m.data);}catch(e){return;}
    if(ev.type==='interrupted')this.flush();
    this.onEvent(ev);
  }
  enqueue(data){
    const ctx=this.playCtx;if(!ctx||this.closed)return;
    const pcm=new Int16Array(data,0,Math.floor(data.byteLength/2));const buf=ctx.createBuffer(1,pcm.length,PLAY_RATE);const ch=buf.getChannelData(0);
    for(let i=0;i<pcm.length;i++)ch[i]=pcm[i]/0x8000;
    const src=ctx.createBufferSource();src.buffer=buf;src.connect(ctx.destination);
    const at=Math.max(ctx.currentTime+0.03,this.nextStart);src.start(at);this.nextStart=at+buf.duration;
    this.sources.add(src);src.onended=()=>this.sources.delete(src);
  }
  flush(){this.sources.forEach(s=>{s.onended=null;try{s.stop();}catch(e){}});this.sources.clear();this.nextStart=0;}
  playbackRemainingMs(){return this.playCtx?Math.max(0,(this.nextStart-this.playCtx.currentTime)*1000):0;}
  isAssistantSpeaking(){return this.playbackRemainingMs()>0;}
  stop(){
    if(this.closed)return;this.closed=true;
    try{if(this.ws&&this.ws.readyState===1)this.ws.send(JSON.stringify({type:'end'}));this.ws&&this.ws.close();}catch(e){}
    this.flush();
    try{this.stream&&this.stream.getTracks().forEach(t=>t.stop());}catch(e){}
    try{this.micCtx&&this.micCtx.close();}catch(e){}try{this.playCtx&&this.playCtx.close();}catch(e){}
  }
}

// ---- Dev Mode: a toggle (bottom-left) and a side pane that draws live agent / orchestration / model telemetry ----
class DevMode{
  constructor(getData){
    this.getData=getData;this.sig='';
    try{this.on=localStorage.getItem('homerun_dev')==='1';}catch(e){this.on=false;}
    const st=document.createElement('style');st.textContent=`
      @keyframes hrDraw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
      @keyframes hrGrow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
      @keyframes hrFlow{to{stroke-dashoffset:-14}}
      @keyframes hrRing{from{transform:scale(1);opacity:.9}to{transform:scale(3);opacity:0}}
      @keyframes hrFlash{0%{background:var(--hr-c,#9d9);box-shadow:0 0 14px var(--hr-c,#9d9)}100%{background:transparent;box-shadow:none}}
      @keyframes hrPulse{0%,100%{opacity:1}50%{opacity:.35}}
      .hr-draw{stroke-dasharray:1;stroke-dashoffset:1;animation:hrDraw .9s ease-out forwards}
      .hr-grow{transform-origin:left center;animation:hrGrow .7s cubic-bezier(.2,.8,.2,1) both}
      body{transition:margin-right .3s cubic-bezier(.2,.8,.2,1)}
      #hr-dev-pane{position:fixed;top:0;right:0;bottom:0;width:360px;z-index:9998;background:var(--tile,#fff);color:var(--ink,#111);border-left:1.5px solid var(--line,#ddd);overflow-y:auto;padding:16px 16px 70px;font:12px/1.4 'JetBrains Mono',ui-monospace,monospace;transform:translateX(100%);transition:transform .3s cubic-bezier(.2,.8,.2,1)}
      #hr-dev-pane.open{transform:none}
      #hr-dev-pane h4{margin:18px 0 8px;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted,#888);font-weight:600}
      #hr-dev-pane .card{background:var(--soft,#f3f3f3);border-radius:14px;padding:10px 12px}
      #hr-dev-pane .row{display:flex;justify-content:space-between;gap:10px;padding:3px 0}
      #hr-dev-pane .row span:first-child{color:var(--muted,#888)}
      #hr-dev-toggle{position:fixed;left:14px;bottom:14px;z-index:9999;display:flex;align-items:center;gap:8px;border:1.5px solid var(--line,#ddd);background:var(--tile,#fff);color:var(--ink,#111);border-radius:999px;padding:6px 10px 6px 8px;font:600 11px 'JetBrains Mono',ui-monospace,monospace;cursor:pointer;box-shadow:0 4px 18px rgb(0 0 0/.12)}
      #hr-dev-toggle i{display:block;width:26px;height:15px;border-radius:999px;background:var(--line,#ccc);position:relative;transition:background .2s}
      #hr-dev-toggle i:after{content:'';position:absolute;top:2px;left:2px;width:11px;height:11px;border-radius:50%;background:var(--tile,#fff);transition:left .2s}
      #hr-dev-toggle.on i{background:var(--mint,#4c9)}#hr-dev-toggle.on i:after{left:13px}`;
    document.head.appendChild(st);this.st=st;
    this.btn=document.createElement('button');this.btn.id='hr-dev-toggle';this.btn.type='button';this.btn.setAttribute('aria-label','Toggle Dev Mode');this.btn.innerHTML='<i></i>Dev Mode';
    this.btn.onclick=()=>this.set(!this.on);
    this.pane=document.createElement('aside');this.pane.id='hr-dev-pane';this.pane.setAttribute('aria-label','Dev Mode');
    document.body.appendChild(this.pane);document.body.appendChild(this.btn);
    this.apply();this.timer=setInterval(()=>this.tick(),1000);
  }
  set(v){this.on=v;try{localStorage.setItem('homerun_dev',v?'1':'0');}catch(e){}this.sig='';this.apply();}
  apply(){this.btn.classList.toggle('on',this.on);this.pane.classList.toggle('open',this.on);document.body.style.marginRight=this.on?'360px':'';if(this.on)this.tick();}
  destroy(){clearInterval(this.timer);document.body.style.marginRight='';[this.st,this.btn,this.pane].forEach(n=>n&&n.remove());}
  tick(){if(!this.on)return;let d;try{d=this.getData();}catch(e){return;}const sig=JSON.stringify(d);if(sig===this.sig)return;this.sig=sig;this.pane.innerHTML=this.render(d);}
  render(d){
    const esc=x=>String(x==null?'—':x).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    const G='var(--mint,#3b9)',Y='var(--butter,#db3)',R='var(--rose,#d56)',DIM='var(--muted,#999)',INK='var(--ink,#111)';
    // 1. orchestration graph: request -> agents; each agent has its own colour, edges flow when it is running, nodes glow after a call
    const AG=[['buyer_intelligence','buyer-intel',0],['market_intelligence','market',1],['valuation','valuation',2],['affordability_risk','affordability',3],['matching_decision','matching',4]];
    const COL={buyer_intelligence:'#b9a2ff',market_intelligence:'#6ec1ff',valuation:'#5be3a8',affordability_risk:'#ffd166',matching_decision:'#ff8fa3',rules:'#9aa0a6','gemini-live':'#c792ff'};
    const by=d.agents||{},fresh=d.fresh||{};
    const nodes=AG.map(([k,label,i])=>{const x=by[k];return {k,label,i,x,fresh:!!fresh[k],color:COL[k]};});
    const W=328,H=158,bx=a=>38+a*(W-76)/4;
    let svg=`<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Agent orchestration graph" style="overflow:visible">`;
    svg+=`<text x="${bx(0)}" y="12" fill="${DIM}" font-size="9" text-anchor="middle">chat</text><text x="${(bx(1)+bx(3))/2}" y="12" fill="${DIM}" font-size="9" text-anchor="middle">match pipeline →</text><text x="${bx(4)}" y="12" fill="${DIM}" font-size="9" text-anchor="middle">rank</text>`;
    nodes.forEach(n=>{n.y=n.i%2?100:60;n.x0=bx(n.i);});
    nodes.slice(1).forEach((n,j)=>{const a=nodes[j];const hot=n.fresh||a.fresh;const dpath=`M${a.x0} ${a.y} C ${(a.x0+n.x0)/2} ${a.y}, ${(a.x0+n.x0)/2} ${n.y}, ${n.x0} ${n.y}`;
      svg+=`<path d="${dpath}" fill="none" stroke="${DIM}" stroke-opacity=".25" stroke-width="2"/>`;
      svg+=`<path d="${dpath}" fill="none" stroke="${hot?n.color:DIM}" stroke-width="${hot?3:1.6}" stroke-linecap="round" stroke-dasharray="${hot?'5 9':'2 10'}" style="animation:hrFlow ${hot?'.55s':'3s'} linear infinite;${hot?`filter:drop-shadow(0 0 5px ${n.color})`:''}" opacity="${hot?1:.5}"/>`;});
    nodes.forEach(n=>{const on=!!n.x,glow=n.fresh;
      svg+=`<g>${glow?`<circle cx="${n.x0}" cy="${n.y}" r="9" fill="none" stroke="${n.color}" stroke-width="2" style="transform-origin:${n.x0}px ${n.y}px;animation:hrRing 1.1s ease-out infinite"/><circle cx="${n.x0}" cy="${n.y}" r="9" fill="none" stroke="${n.color}" stroke-width="2" style="transform-origin:${n.x0}px ${n.y}px;animation:hrRing 1.1s .55s ease-out infinite"/>`:''}<circle cx="${n.x0}" cy="${n.y}" r="${glow?11:9}" fill="${n.color}" opacity="${on?1:.35}" style="${glow?`filter:drop-shadow(0 0 9px ${n.color}) drop-shadow(0 0 3px ${n.color});transition:all .3s`:''}"/>${on&&n.x.status!=='ok'?`<text x="${n.x0}" y="${n.y+3.5}" font-size="11" font-weight="700" fill="#111" text-anchor="middle">!</text>`:''}<text x="${n.x0}" y="${n.y+(n.i%2?26:-17)}" font-size="9.5" fill="${glow?n.color:INK}" font-weight="${glow?700:400}" text-anchor="middle">${n.label}</text><text x="${n.x0}" y="${n.y+(n.i%2?37:-6.5)}" font-size="8.5" fill="${DIM}" text-anchor="middle">${on?Math.round(n.x.elapsed_ms)+'ms':'idle'}</text></g>`;});
    svg+='</svg>';
    // 2. agent latency bars
    const maxMs=Math.max(1,...nodes.map(n=>n.x?n.x.elapsed_ms:0));
    const nodesC=nodes;const bars=nodes.map((n,j)=>`<div style="display:grid;grid-template-columns:84px 1fr 48px;gap:8px;align-items:center;padding:3px 0"><span style="color:${DIM}">${n.label}</span><span style="height:9px;border-radius:5px;background:color-mix(in oklch,${INK} 8%,transparent);overflow:hidden"><span class="hr-grow" style="display:block;height:100%;width:${n.x?Math.max(3,n.x.elapsed_ms/maxMs*100):0}%;background:${n.color};animation-delay:${j*0.08}s;${n.fresh?`box-shadow:0 0 10px ${n.color}`:''}"></span></span><span style="text-align:right">${n.x?Math.round(n.x.elapsed_ms)+'ms':'—'}</span></div>`).join('');
    const feed=(d.feed||[]).map(f=>`<div style="--hr-c:${COL[f.agent]||DIM};display:grid;grid-template-columns:8px 1fr auto;gap:8px;align-items:center;padding:5px 8px;border-radius:9px;${f.fresh?'animation:hrFlash 1.6s ease-out both':''}"><i style="display:block;width:8px;height:8px;border-radius:50%;background:${COL[f.agent]||DIM};box-shadow:0 0 ${f.fresh?10:0}px ${COL[f.agent]||DIM}"></i><span><b style="font-weight:600">${esc(f.label)}</b> <span style="color:${DIM}">${esc(f.via)}</span></span><span style="color:${f.status&&f.status!=='ok'?Y:DIM}">${f.ms!=null?Math.round(f.ms)+'ms':''} · ${esc(f.age)}</span></div>`).join('')||`<div style="color:${DIM};padding:6px 8px">no agent calls yet — describe a home or open the profile</div>`;
    // 3. API calls timeline: latency line over the last calls
    const calls=d.calls||[];const mx=Math.max(50,...calls.map(c=>c.ms));
    const pts=calls.map((c,i)=>[8+(calls.length>1?i*(W-16)/(calls.length-1):0),64-(c.ms/mx)*52]);
    const line=pts.length>1?`<path class="hr-draw" pathLength="1" d="M${pts.map(p=>p.map(v=>v.toFixed(1)).join(' ')).join(' L')}" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linejoin="round"/>`:'';
    const dots=pts.map((p,i)=>`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.6" fill="${calls[i].status>=400||calls[i].status===0?R:G}"/>`).join('');
    const spark=`<svg viewBox="0 0 ${W} 72" width="100%" role="img" aria-label="API latency over the last calls"><line x1="8" x2="${W-8}" y1="64" y2="64" stroke="${DIM}" stroke-opacity=".4"/>${line}${dots}<text x="${W-8}" y="10" text-anchor="end" font-size="8.5" fill="${DIM}">peak ${mx}ms</text></svg>`;
    const recent=calls.slice(-6).reverse().map(c=>`<div class="row"><span>${esc(c.method)} ${esc(c.path.replace(/^\/api/,''))}</span><span style="color:${c.status>=400||c.status===0?R:INK}">${c.status||'ERR'} · ${c.ms}ms</span></div>`).join('')||`<div style="color:${DIM}">no calls yet</div>`;
    // 4. AI models
    const m=d.models||{},h=d.health||{},mt=d.metrics||{};
    const vs=d.voice||{};
    const row=(k,v,c)=>`<div class="row"><span>${k}</span><span style="color:${c||INK};text-align:right">${esc(v)}</span></div>`;
    const dot=c=>`<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${c};margin-right:6px"></span>`;
    const models=`<div class="card">${row('chat model',m.chat)}${row('fallback',m.chat_fallback)}${row('last chat turn',d.lastLlm==null?'—':d.lastLlm?'Gemini':'template')}${row('voice model',m.voice||'not configured',m.voice?INK:R)}${row('voice',m.voice_name)}</div>
      <div class="card" style="margin-top:8px">${row('voice session',vs.state||'idle',vs.state&&vs.state!=='idle'?G:DIM)}${(vs.events||[]).slice(-5).map(e=>`<div style="color:${DIM}">${dot(e.text.startsWith('failed')?R:G)}${esc(e.text)}</div>`).join('')}</div>
      <div class="card" style="margin-top:8px">${row('valuation',h.valuation_model_version?h.valuation_model_version+(h.valuation_model_is_trained?'':' (baseline)'):'—')}${row('host',h.architecture)}${row('listings',h.listing_catalog_size)}</div>`;
    const sys=`<div class="card">${row('requests',mt.request_count)}${row('p50',mt.p50_latency_ms!=null?Math.round(mt.p50_latency_ms)+'ms':'—')}${row('p95',mt.p95_latency_ms!=null&&mt.request_count>=20?Math.round(mt.p95_latency_ms)+'ms':'n<20')}${row('errors',mt.error_count)}</div>`;
    return `<div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:14px;font-family:inherit">Dev Mode</b><span style="color:${DIM}">${d.apiDown?dot(R)+'offline':dot(G)+'live'}</span></div>
      <h4>Agent orchestration${d.runId?' · run '+esc(d.runId)+'':''}</h4><div class="card">${svg}</div>
      <h4>Live agent calls</h4><div class="card" style="padding:6px">${feed}</div>
      <h4>Agent latency</h4><div class="card">${bars}</div>
      <h4>API calls (last ${calls.length})</h4><div class="card">${spark}${recent}</div>
      <h4>AI models</h4>${models}
      <h4>Server</h4>${sys}`;
  }
}

// ---- real map: Leaflet + OpenStreetMap tiles, listings pinned from their geocodes, search by condo / HDB name ----
let _leaflet=null;
const loadLeaflet=()=>{if(window.L)return Promise.resolve(window.L);if(_leaflet)return _leaflet;
  _leaflet=new Promise((res,rej)=>{const css=document.createElement('link');css.rel='stylesheet';css.href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css';document.head.appendChild(css);
    const js=document.createElement('script');js.src='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js';js.onload=()=>res(window.L);js.onerror=()=>{_leaflet=null;rej(new Error('map library failed to load'));};document.head.appendChild(js);});
  return _leaflet;};
const escH=x=>String(x==null?'':x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
class MapView{
  constructor(L,host,owner){
    this.L=L;this.host=host;this.owner=owner;this.pinSig='';this.pinLayer=null;this.findLayer=null;this.seq=0;
    host.innerHTML='';
    const canvas=this.canvas=document.createElement('div');canvas.style.cssText='position:absolute;inset:0';host.appendChild(canvas);
    const ui=document.createElement('div');ui.style.cssText='position:absolute;top:14px;left:14px;right:14px;z-index:1000;max-width:420px;font:14px system-ui,sans-serif';
    ui.innerHTML='<input type="search" placeholder="Search a condo or HDB name…" aria-label="Search the map by condo or HDB name" style="width:100%;box-sizing:border-box;border:0;border-radius:999px;padding:12px 18px;font-size:14.5px;background:var(--tile,#fff);color:var(--ink,#111);box-shadow:0 4px 18px rgb(0 0 0/.18);outline:none"><div class="hr-res" style="display:none;margin-top:8px;border-radius:20px;background:var(--tile,#fff);color:var(--ink,#111);box-shadow:0 8px 28px rgb(0 0 0/.22);overflow:hidden;max-height:300px;overflow-y:auto"></div>';
    host.appendChild(ui);this.ui=ui;this.input=ui.querySelector('input');this.res=ui.querySelector('.hr-res');
    ['mousedown','dblclick','wheel','touchstart','pointerdown'].forEach(ev=>ui.addEventListener(ev,e=>e.stopPropagation()));
    this.input.addEventListener('input',()=>{clearTimeout(this.st);const q=this.input.value.trim();if(q.length<2){this.res.style.display='none';return;}this.st=setTimeout(()=>this.search(q),280);});
    this.input.addEventListener('keydown',e=>{if(e.key==='Escape'){this.res.style.display='none';this.input.blur();}});
    this.map=L.map(canvas,{zoomControl:true,attributionControl:true}).setView([1.3521,103.8198],11);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors · search: OneMap'}).addTo(this.map);
    this.pinLayer=L.layerGroup().addTo(this.map);this.findLayer=L.layerGroup().addTo(this.map);
    setTimeout(()=>this.map.invalidateSize(),50);
  }
  destroy(){try{clearTimeout(this.st);this.map.remove();}catch(e){}}
  pill(html,bg,fg){return this.L.divIcon({className:'',html:`<div style="transform:translate(-50%,-100%);white-space:nowrap;background:${bg};color:${fg};border-radius:999px;padding:6px 11px;font:600 12.5px system-ui,sans-serif;box-shadow:0 3px 10px rgb(0 0 0/.3);border:2px solid #fff;cursor:pointer">${html}</div>`,iconSize:[0,0]});}
  setPins(pins){
    const sig=JSON.stringify(pins);if(sig===this.pinSig)return;this.pinSig=sig;this.pinLayer.clearLayers();
    const pts=[];
    pins.forEach(p=>{const m=this.L.marker([p.lat,p.lon],{icon:this.pill('#'+p.rank+' · '+p.price,'#1b1b22','#fff'),title:p.name}).addTo(this.pinLayer);m.on('click',()=>this.owner.openFromMap(p.id));pts.push([p.lat,p.lon]);});
    if(pts.length&&!this.fitted){this.fitted=true;this.map.fitBounds(pts,{padding:[60,60],maxZoom:15});}
  }
  async search(q){
    const seq=++this.seq;let d;
    try{d=await api.get('/ui/search?q='+encodeURIComponent(q));}catch(e){this.showRes([],[],'Search unavailable');return;}
    if(seq!==this.seq)return;this.owner.mergeInv(d.listings);this.showRes(d.listings,d.places);
  }
  showRes(listings,places,msg){
    const rows=[];
    listings.forEach((l,i)=>rows.push(`<button data-k="l${i}" style="${this.rowCss()}"><b>${escH(l.name)}</b><span style="opacity:.65;font-size:12.5px">${escH(l.type||'')} · ${escH(l.town||'')} · $${Math.round(l.price/1000).toLocaleString('en-SG')}k · for sale</span></button>`));
    places.forEach((p,i)=>rows.push(`<button data-k="p${i}" style="${this.rowCss()}"><b>${escH(p.name||p.address)}</b><span style="opacity:.65;font-size:12.5px">${escH(p.address)} · place</span></button>`));
    this.res.innerHTML=rows.join('')||`<div style="padding:14px 18px;opacity:.65">${escH(msg||'No matches')}</div>`;this.res.style.display='block';
    this.res.querySelectorAll('button').forEach(b=>b.onclick=()=>{const k=b.dataset.k;this.res.style.display='none';if(k[0]==='l')this.focusListing(listings[+k.slice(1)]);else this.focusPlace(places[+k.slice(1)]);});
  }
  rowCss(){return 'display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;border:0;border-top:1px solid var(--line,#eee);background:transparent;color:inherit;padding:11px 18px;cursor:pointer;font:inherit';}
  focusListing(l){
    this.findLayer.clearLayers();
    const m=this.L.marker([l.lat,l.lon],{icon:this.pill(escH(l.name)+' · $'+Math.round(l.price/1000)+'k','oklch(0.75 0.14 160)','#0b2a1c')}).addTo(this.findLayer);
    m.on('click',()=>this.owner.openFromMap(l.id));this.map.flyTo([l.lat,l.lon],17,{duration:1.1});
    this.owner.mergeInv([l]);
  }
  focusPlace(p){
    this.findLayer.clearLayers();
    this.L.marker([p.lat,p.lon],{icon:this.pill(escH(p.name||p.address),'oklch(0.8 0.1 290)','#1b1033')}).addTo(this.findLayer);
    this.map.flyTo([p.lat,p.lon],17,{duration:1.1});
  }
}

// ---- compare viewed homes side by side: viewing time, checklist, your notes and photo observations ----
const CHK_LIST=[['a','Check water pressure & taps'],['b','Note light at this hour'],['c','Ask about remaining lease'],['d','Look for damp or cracks'],['e','Time the walk to MRT'],['f','Photograph the floor plan']];
class ViewCompare{
  constructor(owner){this.o=owner;this.sel=[];this.root=null;this.key=e=>{if(e.key==='Escape')this.close();};}
  open(){
    const vs=this.o.vlist();
    const score=v=>(v.notes&&v.notes.trim()?2:0)+((v.photos||[]).some(p=>p.obs)?1:0)+(v.check&&Object.values(v.check).some(Boolean)?1:0);
    this.sel=[...vs].sort((a,b)=>score(b)-score(a)||b.at-a.at).slice(0,3).map(v=>v.id);
    if(!this.root){this.root=document.createElement('div');this.root.id='hr-vcmp';this.root.setAttribute('role','dialog');this.root.setAttribute('aria-label','Compare viewings');document.body.appendChild(this.root);}
    window.addEventListener('keydown',this.key);this.draw();
  }
  close(){window.removeEventListener('keydown',this.key);if(this.root){this.root.remove();this.root=null;}}
  toggle(id){const i=this.sel.indexOf(id);if(i>=0)this.sel.splice(i,1);else if(this.sel.length<3)this.sel.push(id);this.draw();}
  draw(){
    if(!this.root)return;const o=this.o,vs=[...o.vlist()].sort((a,b)=>a.at-b.at);
    const e=escH,fmt=t=>{const d=new Date(t);return WD[d.getDay()]+' '+d.getDate()+' '+MO[d.getMonth()]+', '+pad(d.getHours())+':'+pad(d.getMinutes());};
    const chosen=this.sel.map(id=>vs.find(v=>v.id===id)).filter(Boolean);
    const cols=chosen.map(v=>{const h=o.get(v.home),ps=v.photos||[],good=[],bad=[];ps.forEach(p=>{if(p.obs){(p.obs.good||[]).forEach(t=>good.push({t,room:p.obs.room}));(p.obs.bad||[]).forEach(t=>bad.push({t,room:p.obs.room}));}});
      const done=CHK_LIST.filter(c=>v.check&&v.check[c[0]]);return {v,h,ps,good,bad,done,net:good.length-bad.length};});
    const best=cols.length>1?cols.reduce((a,b)=>b.net>a.net?b:a):null;const tie=best&&cols.filter(c=>c.net===best.net).length>1;
    const chip=v=>{const on=this.sel.includes(v.id),h=o.get(v.home);return `<button data-id="${e(v.id)}" style="border:0;border-radius:999px;padding:9px 14px;cursor:pointer;font:500 13.5px system-ui,sans-serif;background:${on?'var(--ink)':'var(--soft)'};color:${on?'var(--bg)':'var(--ink)'};opacity:${on||this.sel.length<3?1:.45}">${e(h.name.replace('Blk ',''))} · ${e(fmt(v.at))}</button>`;};
    const label=(t)=>`<div style="font:600 10.5px 'JetBrains Mono',monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:16px 0 6px">${t}</div>`;
    const colHtml=cols.map((c,i)=>{const u=(c.h.thumb||(c.h.photos&&c.h.photos[0]))||'';const isBest=best&&!tie&&c===best;
      return `<div style="flex:1 1 280px;min-width:0;border-radius:28px;background:var(--tile);padding:10px 10px 18px;${isBest?'box-shadow:0 0 0 2.5px var(--mint)':''}">
        <div style="position:relative;height:150px;border-radius:20px;overflow:hidden;background:var(--soft)">${u?`<img src="${e(u)}" alt="" referrerpolicy="no-referrer" style="width:100%;height:100%;object-fit:cover">`:''}<span style="position:absolute;top:10px;left:10px;width:34px;height:34px;border-radius:50%;background:var(--ink);color:var(--bg);display:grid;place-items:center;font-weight:700">${'ABC'[i]}</span>${isBest?`<span style="position:absolute;top:10px;right:10px;padding:5px 10px;border-radius:999px;background:var(--g-mint,#bfe);color:var(--on,#111);font:600 11px system-ui">best notes</span>`:''}</div>
        <div style="padding:12px 10px 0"><div style="font:700 26px system-ui;letter-spacing:-.04em">${full$(c.h.price||0)}</div><div style="font:500 14px system-ui">${e(c.h.name)}</div><div style="font:12.5px system-ui;color:var(--muted);margin-top:2px">${e(c.h.town||'')} · viewing ${e(fmt(c.v.at))}</div>
        <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap"><span style="padding:5px 10px;border-radius:999px;background:var(--g-mint,#cfe);color:var(--on,#111);font:600 12px system-ui">+${c.good.length} good</span><span style="padding:5px 10px;border-radius:999px;background:var(--g-rose,#fcd);color:var(--on,#111);font:600 12px system-ui">−${c.bad.length} concerns</span><span style="padding:5px 10px;border-radius:999px;background:var(--soft);font:600 12px system-ui">${c.done.length}/${CHK_LIST.length} checked</span></div>
        ${label('your notes')}<div style="white-space:pre-wrap;font:14.5px/1.5 system-ui;${c.v.notes&&c.v.notes.trim()?'':'color:var(--muted);font-style:italic'}">${e(c.v.notes&&c.v.notes.trim()?c.v.notes:'No notes taken')}</div>
        ${label('checklist')}${CHK_LIST.map(([k,t])=>{const on=c.v.check&&c.v.check[k];return `<div style="display:flex;gap:8px;font:13.5px system-ui;padding:3px 0;opacity:${on?1:.5}"><span>${on?'✓':'○'}</span><span style="${on?'':'text-decoration:none'}">${e(t)}</span></div>`;}).join('')}
        ${label('from your photos')}${[...c.good.map(g=>`<div style="display:flex;gap:8px;font:13.5px system-ui;padding:4px 8px;margin:2px 0;border-radius:10px;background:var(--g-mint,#dfe);color:var(--on,#111)"><b>+</b><span>${e(g.t)}${g.room?` <span style="opacity:.6">· ${e(g.room)}</span>`:''}</span></div>`),...c.bad.map(g=>`<div style="display:flex;gap:8px;font:13.5px system-ui;padding:4px 8px;margin:2px 0;border-radius:10px;background:var(--g-rose,#fde);color:var(--on,#111)"><b>−</b><span>${e(g.t)}${g.room?` <span style="opacity:.6">· ${e(g.room)}</span>`:''}</span></div>`)].join('')||`<div style="font:italic 13.5px system-ui;color:var(--muted)">No photo observations</div>`}
        ${c.ps.length?`<div style="display:flex;gap:6px;margin-top:10px;overflow-x:auto">${c.ps.map(p=>`<img src="${e(p.url)}" alt="" style="width:64px;height:64px;object-fit:cover;border-radius:12px;flex:none">`).join('')}</div>`:''}
        </div></div>`;}).join('');
    this.root.innerHTML=`<div style="position:fixed;inset:0;z-index:10000;background:oklch(0.15 0.02 280 / .55);backdrop-filter:blur(6px);display:flex;justify-content:center;align-items:flex-start;overflow-y:auto;padding:4vh 16px" data-bg="1"><div style="width:min(1200px,100%);background:var(--bg);color:var(--ink);border-radius:36px;padding:clamp(18px,3vw,34px);box-shadow:0 30px 80px rgb(0 0 0/.35)">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"><h2 style="margin:0;font:700 clamp(28px,3.4vw,44px) system-ui;letter-spacing:-.045em">Compare viewings</h2><button data-close="1" aria-label="Close" style="border:0;background:var(--soft);color:var(--ink);width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:18px">✕</button></div>
      <div style="font:14px system-ui;color:var(--muted);margin:6px 0 14px">Pick up to three viewings. Notes, checklists and photo observations line up side by side.</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${vs.map(chip).join('')||''}</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:18px">${chosen.length>=2?colHtml:`<div style="flex:1;border-radius:28px;background:var(--tile);padding:34px;font:16px system-ui;color:var(--muted)">${vs.length<2?'Plan at least two viewings, then add notes and photos to compare them here.':'Pick at least two viewings above.'}</div>`}</div>
    </div></div>`;
    this.root.querySelectorAll('button[data-id]').forEach(b=>b.onclick=()=>this.toggle(b.dataset.id));
    const cb=this.root.querySelector('[data-close]');if(cb)cb.onclick=()=>this.close();
    const bg=this.root.querySelector('[data-bg]');if(bg)bg.onclick=ev=>{if(ev.target===bg)this.close();};
  }
}

class Component extends DCLogic {
  state={calM:0,drag2:false,viewings:[],selV:null,dayF:null,add:null,pal:false,pq:'',pi:0,enq:[],deckIdx:0,drag:0,dragging:false,fly:0,passedM:{},mode:'chat',vstate:'idle',vtext:'',screen:null,theme:null,evidence:false,mn:false,chat:0,draft:'',ti:0,budget:900000,budgetInput:'900,000',types:{HDB:true,Condo:true},towns:{Bishan:true,Tampines:true,Queenstown:true},minBed:3,w:{commute:8,mrt:5,area:3,price:3},view:'list',exp:null,cmp:[],like:{},sel:null,interestId:null,dp:25,rate:3,ten:25,checks:0,fields:{name:true,email:true,phone:false,message:true},consent:false,outcome:'submitted',fbPick:null,fbTags:{},banner:null,showExcluded:false,
    convo:[],quick:[],askText:'',vline:null,vchips:[],lastLlm:null,inv:{},match:null,apiDown:false,heard:null,chips:[],askReply:'',doneReply:'',noAsk:false,chatWarn:[],traces:{},cfg:null,health:null,metrics:null,fin:null,pidx:{},cmpData:null,interestData:null,outcomeData:null,visionOk:true};
  componentDidMount(){
    this.applyTheme(this.props.defaultTheme||'light');
    const s=this.props.startScreen;if(s&&s!=='landing')this.go(s);
    let hold=0;
    this.tt=setInterval(()=>{if(this.cur()!=='landing')return;const t=this.state.ti;if(t<HERO.length){this.setState({ti:t+1});return;}if(++hold>90){hold=0;this.setState({ti:0});}},42);
    this.kd=e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();this.openPal();return;}
      const tg=(e.target.tagName||'').toLowerCase();if(tg==='input'||tg==='textarea'||e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key.toLowerCase();
      if(this.state.add&&k==='escape'){this.setState({add:null});return;}
      if(k==='/'){e.preventDefault();this.openPal();return;}
      if(k==='m'){this.go('hub');return;}
      if(k==='v'){this.openAdd();return;}
      if(k==='t')this.toggleTheme({clientX:innerWidth-60,clientY:30});else if(k==='e'){this.setState({evidence:!this.state.evidence});this.loadSystem();}else if(k==='escape')this.setState({evidence:false});
      else if(this.cur()==='results'&&(e.key==='ArrowRight'||e.key==='ArrowLeft'))this.swipe(e.key==='ArrowRight'?1:-1);
      else if(this.cur()==='feedback'&&'abn'.includes(k)&&k.length===1)this.setState({fbPick:{a:0,b:1,n:2}[k]});};
    window.addEventListener('keydown',this.kd);
    this.dev=new DevMode(()=>this.devData());
    this.mapTimer=setInterval(()=>this.tickMap(),500);
    this.sysTimer=setInterval(()=>{if(this.dev&&this.dev.on)this.loadSystem(true);},5000);
    this.boot();
  }
  componentWillUnmount(){this.stopVoice();clearInterval(this.tt);clearInterval(this.sysTimer);clearInterval(this.mapTimer);try{this.cvc&&this.cvc.close();}catch(e){}try{this.mv&&this.mv.destroy();}catch(e){}try{this.dev&&this.dev.destroy();}catch(e){}(this.timers||[]).forEach(clearTimeout);window.removeEventListener('keydown',this.kd);}
  componentDidUpdate(pp){if(pp.defaultTheme!==this.props.defaultTheme)this.applyTheme(this.props.defaultTheme||'light');if(pp.startScreen!==this.props.startScreen&&this.props.startScreen)this.go(this.props.startScreen);}
  devData(){const now=Date.now(),bucket=t=>{const d=now-t;return d<4000?'now':d<15000?'seconds ago':d<60000?'<1m ago':Math.round(d/60000)+'m ago';};const fresh={};Object.keys(AGENT_AT).forEach(k=>{if(now-AGENT_AT[k]<4000)fresh[k]=1;});
    const feed=DEV.feed.slice(-8).reverse().map(f=>({agent:f.agent,label:AGENT_LABEL[f.agent]||f.agent,via:f.via,ms:f.ms==null?null:Math.round(f.ms),status:f.status,age:bucket(f.t),fresh:now-f.t<3000}));
    const s=this.state,TR=s.traces||{},by={};[...(TR.chat||[]),...(TR.match||[]),...(TR.finance||[])].forEach(x=>{by[x.agent_name]={status:x.status,elapsed_ms:x.elapsed_ms};});
    return {agents:by,fresh,feed,calls:DEV.calls.slice(-30).map(c=>({method:c.method,path:c.path,ms:c.ms,status:c.status})),models:(s.cfg&&s.cfg.models)||{},health:s.health&&{valuation_model_version:s.health.valuation_model_version,valuation_model_is_trained:s.health.valuation_model_is_trained,architecture:s.health.architecture,listing_catalog_size:s.health.listing_catalog_size},
      metrics:s.metrics&&{request_count:s.metrics.request_count,error_count:s.metrics.error_count,p50_latency_ms:s.metrics.p50_latency_ms,p95_latency_ms:s.metrics.p95_latency_ms},lastLlm:s.lastLlm,voice:{state:s.vstate,events:DEV.events.filter(e=>e.kind==='voice').slice(-6).map(e=>({text:e.text}))},apiDown:s.apiDown,runId:s.match?String(s.match.run_id).slice(0,8):''};}
  openCmpV(){this.setState({pal:false});if(!this.cvc)this.cvc=new ViewCompare(this);this.cvc.open();}
  openFromMap(id){this.setState({sel:id});this.go('detail');}
  tickMap(){
    const el=document.getElementById('hr-map');
    if(!el){if(this.mv){this.mv.destroy();this.mv=null;}return;}
    if(this.mv&&this.mv.host!==el){this.mv.destroy();this.mv=null;}
    if(!this.mv){if(this.mapLoading)return;this.mapLoading=true;
      loadLeaflet().then(L=>{this.mapLoading=false;const cur=document.getElementById('hr-map');if(cur&&!this.mv)this.mv=new MapView(L,cur,this);}).catch(()=>{this.mapLoading=false;el.innerHTML='<div style="padding:24px;color:var(--muted)">The map couldn’t load. Check your connection.</div>';});return;}
    this.mv.setPins(this.ranked().map((r,i)=>({id:r.l.id,rank:pad(i+1),price:k$(r.l.price),name:r.l.name,lat:r.l.lat,lon:r.l.lon})).filter(p=>p.lat!=null));
  }
  // ---- backend plumbing ----
  async boot(){
    try{
      const cfg=await api.get('/ui/config');
      if(cfg.towns&&cfg.towns.length)TOWNS=cfg.towns.slice();NEARBY=cfg.nearby||{};if(cfg.popular_towns&&cfg.popular_towns.length)POPULAR=cfg.popular_towns.slice();
      this.setState({cfg,apiDown:false});
    }catch(e){this.setState({apiDown:true});}
    this.loadSystem();this.runMatch();this.loadHub();
  }
  fail(e,what){const msg=(e&&e.message)||'request failed';this.setState({banner:what+': '+msg});}
  mergeInv(list){if(!list||!list.length)return;this.setState(st=>{const inv={...st.inv};list.forEach(l=>{if(l&&l.id)inv[l.id]=l;});return {inv};});}
  profile(){const s=this.state;return {budget:s.budget,types:['HDB','Condo'].filter(x=>s.types[x]),towns:TOWNS.filter(x=>s.towns[x]),min_bed:s.minBed,weights:s.w};}
  setProfile(patch){this.setState(patch);this.scheduleMatch();}
  scheduleMatch(){clearTimeout(this.mt);this.mt=setTimeout(()=>this.runMatch(),350);}
  async runMatch(){
    const seq=this.mseq=(this.mseq||0)+1;
    try{
      const m=await api.post('/ui/match',{session_id:SID,profile:this.profile(),limit:5});
      if(seq!==this.mseq)return;
      this.applyMatch(m);
    }catch(e){if(seq===this.mseq)this.setState({apiDown:true});}
  }
  applyMatch(m){
    const prev=(this.state.match&&this.state.match.ranked_ids)||[];
    const same=prev.join()===m.ranked_ids.join();
    this.setState(st=>{const inv={...st.inv};m.ranked.forEach(r=>{inv[r.listing.id]=r.listing;});
      (m.trace||[]).forEach(x=>devagent(x.agent_name,x.elapsed_ms,x.status,'match'));
      return {match:m,inv,apiDown:false,traces:{...st.traces,match:m.trace},deckIdx:same?st.deckIdx:0,passedM:same?st.passedM:{}};});
  }
  async loadSystem(quiet){
    try{const [health,metrics]=await Promise.all([api.get('/health'),api.get('/metrics')]);this.setState({health,metrics});}catch(e){if(!quiet)this.setState({apiDown:true});}
  }
  async loadHub(){
    try{const h=await api.get('/ui/hub?session_id='+encodeURIComponent(SID));
      this.mergeInv(Object.values(h.listings||{}));
      this.setState({viewings:h.viewings||[],enq:h.enquiries||[],visionOk:h.vision_available!==false});
    }catch(e){}
  }
  async loadFinance(){
    const l=this.get(this.selId());if(!l.id)return;const s=this.state;const key=[l.id,s.dp,s.rate,s.ten].join('|');
    try{const f=await api.post('/ui/finance',{listing_id:l.id,down_payment_pct:s.dp,annual_rate_pct:s.rate,years:s.ten});
      (f.trace||[]).forEach(x=>devagent(x.agent_name,x.elapsed_ms,x.status,'finance'));
      this.setState(st=>({fin:{key,monthly:f.monthly,loan:f.loan},traces:{...st.traces,finance:f.trace}}));}catch(e){}
  }
  scheduleFin(){clearTimeout(this.ft);this.ft=setTimeout(()=>this.loadFinance(),300);}
  cmpIds(){const s=this.state;const rk=this.ranked();let ids=(s.cmp.length>=2?s.cmp:rk.slice(0,2).map(r=>r.l.id));if(ids.length<2){const all=Object.keys(s.inv);ids=[...new Set([...ids,...all])].slice(0,2);}return ids;}
  async loadCompare(){
    const s=this.state;const ids=this.cmpIds();if(ids.length<2)return;const key=[ids.join(','),s.dp,s.rate,s.ten].join('|');
    try{const c=await api.post('/ui/compare',{ids,down_payment_pct:s.dp,annual_rate_pct:s.rate,years:s.ten});
      this.mergeInv(c.listings);this.setState({cmpData:{key,...c}});}catch(e){this.fail(e,'Compare unavailable');}
  }
  async loadInterest(){
    const id=this.state.interestId||this.selId();if(!id)return;
    try{const d=await api.post('/ui/interest',{session_id:SID,listing_id:id});this.setState({interestData:d});}catch(e){this.setState({interestData:{error:e.message}});}
  }
  // ---- navigation ----
  cur(){return this.state.screen||'landing';}
  theme(){return this.state.theme||this.props.defaultTheme||'light';}
  applyTheme(t){document.documentElement.dataset.theme=t;this.setState({theme:t});}
  later(fn,ms){(this.timers=this.timers||[]).push(setTimeout(fn,ms));}
  go(s){if(s!=='chat'&&this.vc){this.stopVoice();this.setState({vstate:'idle'});}this.setState({screen:s});window.scrollTo({top:0});
    // setState is batched: let the selection made just before go() land, then load for it
    if(s==='interest'){this.setState({checks:0,interestData:null});this.later(()=>this.loadInterest(),30);this.later(()=>this.setState({checks:1}),1000);this.later(()=>this.setState({checks:2}),2000);}
    if(s==='detail'){this.later(()=>this.loadFinance(),30);}
    if(s==='compare'){this.later(()=>this.loadCompare(),30);}
    if(s==='hub'||s==='notes'){this.later(()=>this.loadHub(),30);}
    if(s==='prefs'||s==='results'){this.later(()=>this.runMatch(),30);}}
  toggleTheme(e){
    const next=this.theme()==='dark'?'light':'dark';const x=e.clientX||innerWidth-60,y=e.clientY||30;
    const apply=()=>{document.documentElement.dataset.theme=next;this.setState({theme:next});};
    if(!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches){apply();return;}
    const t=document.startViewTransition(apply);
    t.ready.then(()=>{const r=Math.hypot(Math.max(x,innerWidth-x),Math.max(y,innerHeight-y));document.documentElement.animate({clipPath:[`circle(0px at ${x}px ${y}px)`,`circle(${r}px at ${x}px ${y}px)`]},{duration:700,easing:'cubic-bezier(.7,0,.2,1)',pseudoElement:'::view-transition-new(root)'});}).catch(()=>{});
  }
  // ---- chat: typed messages, one question at a time until budget / bedrooms / type / town are all answered ----
  mergeMust(a,b){const cls=x=>/^≤|^no budget/.test(x)?'b':/bedrooms$/.test(x)?'r':/^(HDB|Condo)( \+ (HDB|Condo))?$/.test(x)?'t':'w';const nb=new Set(b.map(cls));return [...a.filter(x=>!nb.has(cls(x))),...b].filter((x,i,arr)=>arr.indexOf(x)===i);}
  applyChat(r){
    const p=r.profile||{};const towns={};TOWNS.forEach(t=>towns[t]=(p.towns||[]).includes(t));
    const types={HDB:(p.types||[]).includes('HDB'),Condo:(p.types||[]).includes('Condo')};
    const prevH=this.state.heard||{must:[],nice:[],ask:[],unknown:[]};
    const uniq=(a,b)=>[...a,...b.filter(x=>!a.includes(x))];
    const heard={must:this.mergeMust(prevH.must,r.heard.must||[]),nice:uniq(prevH.nice,r.heard.nice||[]),ask:r.heard.ask||[],unknown:r.heard.unknown||[]};
    const asking=r.stage==='ask';
    if(r.trace&&r.trace.length)r.trace.forEach(x=>devagent(x.agent_name,x.elapsed_ms,x.status,'chat · '+(r.used_llm?'Gemini':'template')));else devagent('rules',null,'ok','chat · no model call');
    this.pinned=new Set();
    this.setState(st=>({budget:p.budget||st.budget,budgetInput:(p.budget||st.budget).toLocaleString('en-SG'),minBed:p.min_bed!=null?p.min_bed:st.minBed,w:p.weights||st.w,towns,types,
      heard,chips:r.chips||[],chat:asking?2:3,quick:r.quick_replies||[],askText:asking?r.reply:'',lastLlm:!!r.used_llm,
      convo:[...st.convo,{text:r.reply,ask:asking,done:!asking}],chatWarn:r.warnings||[],
      traces:{...st.traces,chat:(r.trace&&r.trace.length)?r.trace:(st.traces.chat||[])}}));
    this.scheduleMatch();
  }
  send(text){const t=(text??this.state.draft).trim();if(!t||this.state.chat===1)return;const first=!(this.state.convo||[]).length;
    this.setState(st=>({chat:1,convo:[...(st.convo||[]),{u:1,text:t}],draft:'',quick:[],...(first?{heard:null,chips:[]}:{})}));
    api.post('/ui/chat',{session_id:SID,message:t,profile:this.profile(),restart:first}).then(r=>this.applyChat(r))
      .catch(e=>this.setState(st=>({chat:2,convo:[...st.convo,{text:'Sorry, I couldn’t reach the server. Try again?'}],chatWarn:['Chat unavailable: '+e.message]})));}
  // ---- voice: Gemini Live through the backend socket (/api/voice/ws); the browser only streams mic audio and plays the reply ----
  voiceUrl(){return (API_BASE||location.origin).replace(/^http/,'ws')+'/api/voice/ws';}
  stopVoice(){clearInterval(this.vpoll);clearTimeout(this.vdrain);const vc=this.vc;this.vc=null;try{vc&&vc.stop();}catch(e){}}
  async startVoice(){
    if(this.vc)return;
    this.setState({vstate:'connecting',vline:null,vchips:[],chat:0,chatWarn:[]});
    devlog('voice','connecting');
    const vc=new VoiceClient(this.voiceUrl(),e=>this.onVoiceEvent(e),()=>this.onVoiceClosed());this.vc=vc;
    try{await vc.start();}catch(err){this.vc=null;devlog('voice','failed: '+(err.message||err));this.setState({vstate:'idle',vline:{role:'assistant',text:err.message||'Voice is unavailable right now.'},chatWarn:[err.message||'Voice unavailable']});}
  }
  onVoiceEvent(e){
    devlog('voice',e.type+(e.type==='transcript'?' · '+e.role:''));
    if(e.type==='ready'){this.setState({vstate:'listening'});clearInterval(this.vpoll);
      this.vpoll=setInterval(()=>{const vc=this.vc;if(!vc)return;const want=vc.isAssistantSpeaking()?'speaking':'listening';const cur=this.state.vstate;if((cur==='listening'||cur==='speaking')&&cur!==want)this.setState({vstate:want});},150);}
    else if(e.type==='transcript'){this.setState(st=>{const l=st.vline,same=l&&l.role===e.role;return {vline:{role:e.role,text:(same?l.text:'')+e.text}};});}
    else if(e.type==='state'){devagent('gemini-live',null,'ok','save_preferences');this.applyVoicePrefs(e);}
    else if(e.type==='complete'){this.applyVoicePrefs(e);this.vcomplete=true;this.setState({chat:3,doneReply:'Perfect. Check your profile, then I’ll rank.'});}
    else if(e.type==='error'){this.stopVoice();this.setState({vstate:'idle',vline:{role:'assistant',text:e.message},chatWarn:[e.message]});}
  }
  onVoiceClosed(){
    // after "complete" the socket closes while the recap is still playing: let it finish before tearing down
    if(this.vcomplete){const vc=this.vc;const wait=()=>{if(vc&&vc.playbackRemainingMs()>0){this.vdrain=setTimeout(wait,200);}else{this.vcomplete=false;this.stopVoice();this.setState({vstate:'idle'});}};wait();return;}
    this.stopVoice();if(this.state.vstate!=='idle')this.setState({vstate:'idle'});
  }
  applyVoicePrefs(e){
    const a=e.answered||{},must=[],warn=[];const patch={};
    if(a.budget){const b=e.no_budget_limit?5000000:e.max_price_sgd;patch.budget=b;patch.budgetInput=b.toLocaleString('en-SG');must.push(e.no_budget_limit?'no budget cap':'≤ '+k$(b));}
    if(a.bedrooms&&e.bedrooms.length){patch.minBed=Math.min(...e.bedrooms);must.push(patch.minBed+'+ bedrooms');}
    if(a.property_type){const t={HDB:e.property_types.includes('HDB'),Condo:e.property_types.includes('CONDO')||e.property_types.includes('EC')};if(t.HDB||t.Condo){patch.types=t;must.push(['HDB','Condo'].filter(x=>t[x]).join(' + '));}}
    if(a.town){const tw={};if(e.anywhere){TOWNS.forEach(x=>tw[x]=true);must.push('any town');}else{const found=TOWNS.filter(x=>e.towns.some(y=>y.toUpperCase()===x.toUpperCase()));TOWNS.forEach(x=>tw[x]=found.includes(x));must.push(...found);
      e.towns.filter(y=>!TOWNS.some(x=>x.toUpperCase()===y.toUpperCase())).forEach(y=>warn.push(y.charAt(0)+y.slice(1).toLowerCase()+' isn’t in this version’s town list ('+TOWNS.join(', ')+').'));}patch.towns=tw;}
    const LBL={budget:'budget?',bedrooms:'how many bedrooms?',property_type:'HDB, condo or both?',town:'which area?'};
    const miss=Object.keys(LBL).filter(x=>!a[x]);
    const vchips=[...must.map(label=>({label,cat:'must'})),...(miss.length?[{label:LBL[miss[0]],cat:'ask'}]:[])];
    if(patch.towns)this.pinned=new Set();
    this.setState(st=>({...patch,vchips,heard:{must,nice:[],ask:miss.length?[LBL[miss[0]]]:[],unknown:[]},chatWarn:warn.length?warn:st.chatWarn}));
    this.scheduleMatch();
  }
  toggleVoice(){const v=this.state.vstate;if(v==='idle')this.startVoice();else{this.stopVoice();this.setState({vstate:'idle'});}}
  // ---- results deck ----
  swipe(dir){const rk=this.ranked();const c=rk[this.state.deckIdx];if(!c||this.state.fly)return;this.setState({fly:dir,dragging:false});
    this.later(()=>{const id=c.l.id;this.setState(st=>({deckIdx:st.deckIdx+1,fly:0,drag:0,like:{...st.like,[id]:dir>0},passedM:{...st.passedM,[id]:dir<0}}));},320);}
  // ---- viewings (server-backed) ----
  vlist(){return this.state.viewings||[];}
  setV(fn){this.setState(st=>({viewings:fn(st.viewings||[])}));}
  vpath(vid,rest){return '/ui/viewings/'+encodeURIComponent(vid)+(rest||'')+'?session_id='+encodeURIComponent(SID);}
  patchV(vid,body,delay){clearTimeout((this.vt=this.vt||{})[vid+(body.notes!==undefined?'n':'c')]);const run=()=>api.patch(this.vpath(vid),body).catch(e=>this.fail(e,'Could not save'));
    if(delay){this.vt[vid+(body.notes!==undefined?'n':'c')]=setTimeout(run,delay);}else run();}
  openPal(){this.setState({pal:true,pq:'',pi:0});setTimeout(()=>{try{this.palRef&&this.palRef.focus();}catch(e){}},30);}
  openAdd(home,day){const rk=this.ranked();this.setState({pal:false,add:{home:home||(rk[0]&&rk[0].l.id)||Object.keys(this.state.inv)[0]||null,day:day||1,time:'11:00'}});}
  shrink(file){return new Promise((res,rej)=>{const r=new FileReader();r.onerror=rej;r.onload=()=>{const im=new Image();im.onerror=rej;im.onload=()=>{const m=1024,k=Math.min(1,m/Math.max(im.width,im.height));const c=document.createElement('canvas');c.width=Math.round(im.width*k);c.height=Math.round(im.height*k);c.getContext('2d').drawImage(im,0,0,c.width,c.height);res(c.toDataURL('image/jpeg',0.82));};im.src=r.result;};r.readAsDataURL(file);});}
  updPhoto(vid,pid,patch){this.setV(vs=>vs.map(v=>v.id!==vid?v:{...v,photos:(v.photos||[]).map(p=>p.id===pid?{...p,...patch}:p)}));}
  async addPhotos(vid,files){for(const file of Array.from(files||[])){if(!/^image\//.test(file.type))continue;let url;try{url=await this.shrink(file);}catch(e){continue;}
    try{const ph=await api.post(this.vpath(vid,'/photos'),{image_data_url:url});
      this.setV(vs=>vs.map(v=>v.id!==vid?v:{...v,photos:[...(v.photos||[]),{id:ph.id,url,status:'loading',obs:null}]}));
      this.analyze(vid,ph.id);}catch(e){this.fail(e,'Photo upload failed');}}}
  async analyze(vid,pid){this.updPhoto(vid,pid,{status:'loading'});
    try{const r=await api.post(this.vpath(vid,'/photos/'+encodeURIComponent(pid)+'/analyze'));
      this.updPhoto(vid,pid,r.status==='done'?{status:'done',obs:{room:String(r.obs.room||'').slice(0,28),good:(r.obs.good||[]).map(String),bad:(r.obs.bad||[]).map(String)}}:{status:'error'});
    }catch(e){this.updPhoto(vid,pid,{status:'error'});}}
  ics(v){const h=this.get(v.home);const d=new Date(v.at);const p=n=>String(n).padStart(2,'0');const loc=d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'T'+p(d.getHours())+p(d.getMinutes())+'00';const now=new Date();const st=now.getUTCFullYear()+p(now.getUTCMonth()+1)+p(now.getUTCDate())+'T'+p(now.getUTCHours())+p(now.getUTCMinutes())+'00Z';
    const txt=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Homerun//Viewing//EN','BEGIN:VEVENT','UID:'+v.id+'-'+h.id+'@homerun','DTSTAMP:'+st,'DTSTART:'+loc,'DURATION:PT45M','SUMMARY:Viewing - '+h.name,'LOCATION:'+h.name+'\, Singapore','DESCRIPTION:Listing '+h.id+' ('+({confirmed:'agent confirmed',requested:'awaiting agent',self:'added by you'}[v.st])+').','END:VEVENT','END:VCALENDAR'].join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([txt],{type:'text/calendar'}));a.download='viewing-'+h.id+'.ics';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);}
  // ---- ranking data (all from /api/ui/match) ----
  ranked(){const m=this.state.match;if(!m)return [];return m.ranked.map(r=>({l:r.listing,fs:r.factors.map(f=>({...f})),pen:r.penalty,score:r.score,reasons:r.reasons}));}
  get(id){return this.state.inv[id]||EMPTY;}
  selId(){const rk=this.ranked();return this.state.sel||(rk[0]&&rk[0].l.id)||null;}
  reasonsOf(r){return (r.reasons||[]).map(x=>({bg:TONE[x.tone]||'var(--soft)',text:x.text}));}
  monthly(l){const s=this.state;const P=l.price*(1-s.dp/100),r=s.rate/1200,n=s.ten*12;
    const key=[l.id,s.dp,s.rate,s.ten].join('|');if(s.fin&&s.fin.key===key)return {P:s.fin.loan,m:s.fin.monthly};
    return {P,m:r?P*r/(1-Math.pow(1+r,-n)):P/n};}
  renderVals(){
    const s=this.state,scr=this.cur(),go=k=>()=>this.go(k);
    const is={};['landing','chat','prefs','results','detail','compare','feedback','interest','contact','outcome'].forEach(k=>is[k]=scr===k);is.hub=scr==='hub';is.notes=scr==='notes';
    const SD=[['chat','02','describe'],['prefs','03','profile'],['results','04','matches'],['detail','05','home'],['compare','06','compare'],['feedback','07','refine'],['interest','08','interest'],['contact','09','contact'],['outcome','10','outcome']];
    const ai=SD.findIndex(x=>x[0]===scr);
    const steps=SD.map(([k,n,label],i)=>({n,label,active:scr===k,idle:scr!==k,go:go(k),aria:'Go to '+label,dot:i<ai?'var(--ink)':'var(--muted)'}));
    // landing
    const t=s.ti;const heard=TOK.filter(k=>t>=HERO.indexOf(k[0])+k[0].length).map(k=>({label:k[1],bg:k[2]?'var(--ink)':'color-mix(in oklch,var(--tile) 60%,transparent)',color:k[2]?'var(--bg)':'var(--ink)'}));
    const mn=s.mn?{k:'nice-to-have',t:'Wishes only rank.',x:'4px'}:{k:'must-have',t:'Deal-breakers filter.',x:'30px'};
    // chat
    const H=s.heard||{must:[],nice:[],ask:[],unknown:[]};
    const msgs=(s.convo||[]).map((m,i,arr)=>({...m,replies:!m.u&&!!m.ask&&i===arr.length-1&&s.chat===2&&(s.quick||[]).length>0,cta:!m.u&&!!m.done}));
    if(s.chat===1)msgs.push({text:'',typing:1});
    const chatMsgs=msgs.filter(m=>m.text||m.typing).map(m=>({text:m.text,typing:!!m.typing,replies:!!m.replies,cta:!!m.cta,align:m.u?'flex-end':'flex-start',bg:m.u?'var(--ink)':(m.typing?'transparent':'var(--soft)'),color:m.u?'var(--bg)':'var(--ink)'}));
    if(s.chat===1&&chatMsgs.length)chatMsgs[chatMsgs.length-1].bg='transparent';
    const must=s.chat>=2?H.must:[];
    const nice=s.chat>=2?H.nice:[];
    const quick=(s.quick||[]).map(label=>({label,pick:()=>this.send(label)}));
    // prefs
    const rk=this.ranked();const M=s.match;const C0=M?M.counts:{checked:0,eligible:0,excluded:0,ranked:0};const nE=C0.eligible;
    const elig={n:nE,total:C0.checked,numColor:nE?'var(--mint)':'var(--rose)',cta:nE?(nE>rk.length?'Show my top '+rk.length+' matches →':'Show my '+nE+' matches →'):'Loosen a must-have',dots:(M?M.dots:[]).map(d=>({id:d.id,bg:d.ok?'var(--mint)':'transparent'}))};
    const tog=on=>({bg:on?'var(--on)':'transparent',color:on?'var(--mint)':'var(--on)',bs:on?'solid':'dashed',op:on?1:0.55,mark:on?'●':'○'});
    const typeOpts=['HDB','Condo'].map(x=>({label:x,on:!!s.types[x],...tog(s.types[x]),toggle:()=>this.setProfile({types:{...s.types,[x]:!s.types[x]}})}));
    const selT=TOWNS.filter(x=>s.towns[x]);const pin=this.pinned||(this.pinned=new Set());const vis=new Set(selT);
    if(selT.length){let n=0;for(let i=0;i<6&&n<6;i++)selT.forEach(t=>{const c=(NEARBY[t]||[])[i];if(c&&!vis.has(c)&&n<6){vis.add(c);n++;}});}else POPULAR.forEach(x=>vis.add(x));
    pin.forEach(x=>vis.add(x));const shownT=TOWNS.filter(x=>vis.has(x));
    const townOpts=shownT.map(x=>({label:x,on:!!s.towns[x],...tog(s.towns[x]),toggle:()=>{this.pinned.add(x);this.setProfile({towns:{...s.towns,[x]:!s.towns[x]}});}}));
    const WORD=v=>v===0?'ignore':v<=4?'a little':v<=6?'matters':'matters a lot';
    const softOpts=SOFT.map(o=>({label:o.label,val:s.w[o.k],word:WORD(s.w[o.k]),dots:Array.from({length:5},(_,i)=>{const val=(i+1)*2,on=s.w[o.k]>=val-1;return {aria:o.label+' '+val+'/10',on,size:(16+i*4)+'px',bg:on?'var(--on)':'transparent',set:()=>this.setProfile({w:{...s.w,[o.k]:Math.round(s.w[o.k]/2)*2===val?0:val}})};}),segs:Array.from({length:10},(_,i)=>({aria:o.label+' '+(i+1),bg:i<s.w[o.k]?'var(--on)':'color-mix(in oklch,var(--on) 14%,transparent)',set:()=>this.setProfile({w:{...s.w,[o.k]:s.w[o.k]===i+1?0:i+1}})}))}));
    // results
    const n=rk.length;
    const cards=rk.map((r,i)=>{const l=r.l,ex=s.exp===l.id,on=s.cmp.includes(l.id),lk=!!s.like[l.id],big=i===0;
      return {rank:pad(i+1),delay:(i*0.07)+'s',flex:big?'1 1 100%':'1 1 380px',photoFlex:big?'1.3 1 420px':'1 1 260px',photoH:big?'300px':'190px',priceSize:big?'48px':'34px',
      price:full$(l.price),name:l.name,facts:[l.type,l.beds!=null?l.beds+' bd':null,l.area!=null?l.area+' m²':null,l.town].filter(Boolean).join(' · '),reasons:this.reasonsOf(r),score:r.score,expanded:ex,expLabel:ex?'hide':'why this rank?',
      factors:r.fs.map(f=>({label:f.label+(f.s==null?' ?':''),pct:(f.max?Math.round(f.c/f.max*100):0)+'%',pts:'+'+Math.round(f.c*100),color:f.s==null?'var(--g-butter)':'var(--acc)'})),
      hasPen:r.pen>0,penalty:'−'+Math.round(r.pen*100)+' for missing data. Unknowns never score best-case.',
      open:()=>{this.setState({sel:l.id});this.go('detail');},openLabel:'Open '+l.name,toggleExp:()=>this.setState({exp:ex?null:l.id}),
      cmpOn:on,cmpLabel:on?'✓ Comparing':'+ Compare',cmpBg:on?'var(--g-lav)':'var(--soft)',cmpColor:on?'var(--on)':'var(--ink)',
      toggleCmp:()=>this.setState({cmp:on?s.cmp.filter(x=>x!==l.id):s.cmp.length>=3?s.cmp:[...s.cmp,l.id]}),
      likeOn:lk,likeBg:lk?'var(--g-rose)':'var(--soft)',likeColor:lk?'var(--on)':'var(--muted)',like:()=>this.setState({like:{...s.like,[l.id]:!lk}})};});
    const excluded=(M?M.excluded:[]).map(x=>({name:x.name,why:x.why}));
    const di=s.deckIdx;const deckSlice=rk.slice(di,di+3);
    const deckCards=deckSlice.map((r,j)=>{const l=r.l,top=j===0;const dx=top?(s.fly?s.fly*700:s.drag):0;
      const tf=top?'translateX('+dx+'px) rotate('+(dx/22).toFixed(2)+'deg)':'translateY('+(j*18)+'px) scale('+(1-j*0.05)+')';
      return {z:10-j,hidden:!top,rank:pad(di+j+1),score:r.score,id:l.id,price:full$(l.price),name:l.name,hasPhoto:!!l.thumb,photo:l.thumb||'',photoCap:l.thumb?'':'[ listing photo ]',capColor:l.thumb?'oklch(0.97 0.005 85)':'var(--muted)',
        facts:[['type',l.type],['beds',l.beds!=null?l.beds+'':null],['area',l.area!=null?l.area+' m²':null],['MRT',l.mrt==null?null:l.mrt+' min']].map(([k,v])=>({k,...(v==null?{v:'unknown',color:'var(--muted)',fs:'italic'}:{v,color:'var(--ink)',fs:'normal'})})),
        reasons:this.reasonsOf(r),factors:r.fs.map(x=>({label:x.label+(x.s==null?' ?':''),pct:(x.max?Math.round(x.c/x.max*100):0)+'%',pts:'+'+Math.round(x.c*100),color:x.s==null?'var(--butter)':'var(--acc)'})),
        tf,op:top&&s.fly?0:1,tr:top&&s.dragging?'none':'transform .35s cubic-bezier(.2,.8,.2,1),opacity .35s',cursor:top?(s.dragging?'grabbing':'grab'):'default',
        likeOp:top?Math.max(0,Math.min(1,(s.fly>0?1:s.drag/110))):0,passOp:top?Math.max(0,Math.min(1,(s.fly<0?1:-s.drag/110))):0,
        down:top?e=>{this.dx0=e.clientX;this.setState({dragging:true});try{e.currentTarget.setPointerCapture(e.pointerId);}catch(_){}}:null,
        move:top?e=>{if(!this.state.dragging)return;const d=e.clientX-this.dx0;if(this.raf)return;this.raf=requestAnimationFrame(()=>{this.raf=null;this.setState({drag:d});});}:null,
        up:top?()=>{if(!this.state.dragging)return;const d=this.state.drag;if(Math.abs(d)>110)this.swipe(d>0?1:-1);else if(Math.abs(d)<6){this.setState({dragging:false,drag:0});this.setState({sel:l.id});this.go('detail');}else this.setState({dragging:false,drag:0});}:null};}).reverse();
    const likedL=rk.filter(r=>s.like[r.l.id]).map(r=>r.l),passedL=rk.filter(r=>s.passedM[r.l.id]).map(r=>r.l);
    const deck={has:di<rk.length,done:rk.length>0&&di>=rk.length,cards:deckCards,count:Math.min(di+1,rk.length)+' / '+rk.length,total:NUM[rk.length]||rk.length,
      pass:()=>this.swipe(-1),like:()=>this.swipe(1),open:()=>{const c=rk[di];if(c){this.setState({sel:c.l.id});this.go('detail');}},
      likedN:likedL.length,noLiked:!likedL.length,liked:likedL.map(l=>({price:k$(l.price),name:l.name,open:()=>{this.setState({sel:l.id});this.go('detail');}})),
      hasPassed:passedL.length>0,passedN:passedL.length,passed:passedL.map(l=>({name:l.name.replace('Blk ',''),undo:()=>this.setState(st=>({passedM:{...st.passedM,[l.id]:false},deckIdx:Math.min(st.deckIdx,rk.findIndex(r=>r.l.id===l.id))}))})),
      canCompare:likedL.length>=2,compareLiked:()=>{this.setState({cmp:likedL.slice(0,3).map(l=>l.id)});this.go('compare');},
      summary:likedL.length?'You liked '+likedL.length+(likedL.length===1?' home.':' homes.')+(likedL.length>=2?' Compare them side by side.':''):'Nothing liked yet — no worries.',
      restart:()=>this.setState({deckIdx:0,passedM:{}}),leftHint:Math.max(0.08,Math.min(1,s.fly<0?1:-s.drag/110)),rightHint:Math.max(0.08,Math.min(1,s.fly>0?1:s.drag/110))};
    const res={headline:n===0?'No homes':n===1?'One home':NUM[n][0].toUpperCase()+NUM[n].slice(1)+' homes',tail:n?'fit.':'fit.',
      funnel:C0.checked+' checked · '+C0.excluded+' out · '+n+' ranked'+(n&&n<5?' · no filler':''),
      dots:(M?M.dots:[]).map((d,i)=>({title:d.id+(d.ok?' · passed':' · filtered out'),bg:d.ok?'var(--g-mint)':'transparent',border:d.ok?'var(--mint)':'var(--line)',delay:(i*0.05)+'s'})),
      chips:[{label:'≤ '+k$(s.budget)},{label:['HDB','Condo'].filter(x=>s.types[x]).join(' + ')||'no type'},{label:TOWNS.filter(x=>s.towns[x]).join(' · ')||'no towns'},{label:s.minBed+'+ bd'}].map(c=>({...c,bg:'var(--ink)',color:'var(--bg)',border:'var(--ink)'})).concat(SOFT.filter(o=>s.w[o.k]>=6).map(o=>({label:o.label.toLowerCase(),bg:'transparent',color:'var(--ink)',border:'var(--ink)'}))),
      views:['list','map'].map(v=>({label:v==='list'?'cards':'map',on:s.view===v,bg:s.view===v?'var(--ink)':'transparent',color:s.view===v?'var(--bg)':'var(--ink)',pick:()=>this.setState({view:v})})),
      zero:n===0,isList:s.view==='list'&&n>0,isMap:s.view==='map'&&n>0,cards,
      pins:[],
      unplaced:rk.filter(r=>r.l.lat==null).map(r=>({name:r.l.name})),
      hasExcluded:C0.excluded>0,excluded,exclLabel:C0.excluded+' homes didn’t pass a must-have'+(C0.excluded>excluded.length?' · nearest '+excluded.length+' shown':''),exclIcon:s.showExcluded?'−':'+',
      banner:!!s.banner,bannerText:s.banner||'',tray:s.cmp.length>0,traySlots:[0,1,2].map(i=>i<s.cmp.length?'var(--g-mint)':'transparent'),trayText:s.cmp.length+' of 3',trayDisabled:s.cmp.length<2,trayOpacity:s.cmp.length<2?0.4:1};
    // detail
    const l=this.get(this.selId()),mo=this.monthly(l);
    const U=v=>v==null?{v:'unknown',color:'var(--muted)',fs:'italic'}:{v:String(v),color:'var(--ink)',fs:'normal'};
    let dv={hasVal:!!l.val,noVal:!l.val};
    if(l.val){const lo=Math.min(l.val.lo,l.price)*0.96,hi=Math.max(l.val.hi,l.price)*1.04,P=x=>((x-lo)/(hi-lo)*100).toFixed(1)+'%';const diff=(l.price-l.val.pt)/l.val.pt*100;
      dv={...dv,valPt:k$(l.val.pt),loPct:P(l.val.lo),wPct:((l.val.hi-l.val.lo)/(hi-lo)*100).toFixed(1)+'%',askPct:P(l.price),
      valNote:'Asking is '+Math.abs(diff).toFixed(1)+'% '+(diff>=0?'above':'below')+(l.price>=l.val.lo&&l.price<=l.val.hi?' — inside the likely range ('+k$(l.val.lo)+'–'+k$(l.val.hi)+').':' — outside the likely range.'),
      valComps:l.val.n==null?'Comparable resales unavailable.':l.val.n+' past '+l.town+' resales (12 mo).'+(l.val.n<15?' Few comparables.':'')};}
    const tags=[{mark:'✓',text:'under '+k$(s.budget),m:1},{mark:'✓',text:l.beds+' bedrooms',m:1},{mark:'✓',text:l.town,m:1}];
    if(l.commute==null)tags.push({mark:'?',text:'commute unknown',w:1});else if(l.commute<=25)tags.push({mark:'+',text:'~'+l.commute+' min commute'});else tags.push({mark:'−',text:'~'+l.commute+' min commute',w:1});
    if(l.mrt==null)tags.push({mark:'?',text:'MRT distance unknown',w:1});else if(l.mrt<=10)tags.push({mark:'+',text:l.mrt+' min to MRT'});else tags.push({mark:'−',text:l.mrt+' min to MRT',w:1});
    if(l.area==null)tags.push({mark:'?',text:'area unknown',w:1});else if(l.area>=90)tags.push({mark:'+',text:'roomy, '+l.area+' m²'});else tags.push({mark:'−',text:'smaller, '+l.area+' m²',w:1});
    if(l.lease&&parseInt(l.lease)<65)tags.push({mark:'−',text:'shorter lease',w:1});
    const setFin=(k,v)=>{this.setState({[k]:v});this.scheduleFin();};
    const fin=[{label:'Down payment',min:5,max:75,step:5,val:s.dp,show:s.dp+'%',set:e=>setFin('dp',+e.target.value)},{label:'Interest',min:1,max:6,step:0.1,val:s.rate,show:s.rate.toFixed(1)+'%',set:e=>setFin('rate',+e.target.value)},{label:'Tenure',min:5,max:30,step:1,val:s.ten,show:s.ten+' yrs',set:e=>setFin('ten',+e.target.value)}];
    const inCmp=s.cmp.includes(l.id);
    const gal=(l.photos&&l.photos.length)?l.photos:(l.thumb?[l.thumb]:[]);const pidx=gal.length?(s.pidx[l.id]||0)%gal.length:0;
    const d={...dv,hasPhoto:gal.length>0,photo:gal[pidx]||'',photoCap:gal.length?'photo '+(pidx+1)+' / '+gal.length+(gal.length>1?' · tap the photo for more':''):'[ listing photos ]',capColor:gal.length?'oklch(0.97 0.005 85)':'var(--muted)',nextPhoto:()=>this.setState(st=>({pidx:{...st.pidx,[l.id]:((st.pidx[l.id]||0)+1)%Math.max(1,gal.length)}})),id:l.id,town:(l.town||'').toLowerCase(),name:l.name,price:full$(l.price),fetched:hhmm(l.fetched_at),
      facts:[['type',l.type],['bedrooms',l.beds],['area',l.area!=null?l.area+' m²':null],['floor',l.floor],['tenure',l.tenure],['lease left',l.lease],['MRT',l.mrt==null?null:l.mrt+' min'],['commute',l.commute==null?null:'~'+l.commute+' min']].map(([k,v])=>({k,...U(v)})),
      tags:tags.map(x=>({...x,bg:x.m?'var(--ink)':x.w?'var(--g-butter)':'var(--g-mint)',color:x.m?'var(--bg)':'var(--on)',border:x.m?'var(--ink)':'transparent',bs:'solid'})),
      fin,monthly:full$(mo.m),loan:'Loan '+full$(mo.P)+'.',
      interest:()=>{this.setState({interestId:l.id});this.go('interest');},cmpLabel:inCmp?'✓ Comparing':'+ Compare',compare:()=>this.setState({cmp:inCmp?s.cmp.filter(x=>x!==l.id):s.cmp.length>=3?s.cmp:[...s.cmp,l.id]})};
    // compare (rows computed by the backend; formatting only here)
    const ids=this.cmpIds();const C=ids.map(id=>this.get(id));
    const CD=s.cmpData&&s.cmpData.key.startsWith(ids.join(',')+'|')?s.cmpData:null;
    const FMT={type:x=>x,beds:x=>x,area:x=>x+' m²',lease:x=>x,price:full$,estimate:x=>k$(x[0])+'–'+k$(x[1]),monthly:full$,mrt:x=>x+' min',commute:x=>'~'+x+' min'};
    const rowsB=CD?CD.rows:[];
    const cmp={headH:'256px',labels:rowsB.map(r=>r.label),
      cols:C.map((c,ci)=>({...ph(c),letter:'ABC'[ci],delay:(ci*0.07)+'s',name:c.name,price:full$(c.price),open:()=>{this.setState({sel:c.id});this.go('detail');},interest:()=>{this.setState({interestId:c.id,sel:c.id});this.go('interest');},
        cells:rowsB.map(r=>{const cell=r.cells[ci];if(!cell||cell.unknown)return {v:r.key==='estimate'?'n/a for condo':'unknown',color:'var(--muted)',fs:'italic',tag:''};return {v:(FMT[r.key]||String)(cell.v),color:'var(--ink)',fs:'normal',tag:cell.tag||''};})})),
      summary:CD?CD.summary:'Comparing…'};
    // feedback
    const A=C[0]||EMPTY,B=C[1]||C[0]||EMPTY;
    const pair=[A,B].map((p,i)=>{const on=s.fbPick===i,o=i?A:B;return {...ph(p),letter:'AB'[i],name:p.name,price:k$(p.price),on,bg:on?'var(--g-lav)':'var(--tile)',color:on?'var(--on)':'var(--ink)',tf:on?'rotate('+(i?1:-1)+'deg) scale(1.01)':'none',
      diffs:[[p.commute==null?'commute unknown':'~'+p.commute+' min commute',p.commute!=null&&(o.commute==null||p.commute<o.commute)],[p.mrt==null?'MRT unknown':p.mrt+' min MRT',p.mrt!=null&&(o.mrt==null||p.mrt<o.mrt)],[p.area==null?'area unknown':p.area+' m²',p.area!=null&&(o.area==null||p.area>o.area)]].map(([v,b])=>({v,bg:b?'var(--g-mint)':'var(--soft)'})),pick:()=>this.setState({fbPick:i})};});
    const TAGS=[['price','price'],['area','space'],['commute','commute'],['mrt','MRT']];
    const tagsF=TAGS.map(([k,label])=>{const on=!!s.fbTags[k];return {label,on,bg:on?'var(--ink)':'var(--soft)',color:on?'var(--bg)':'var(--ink)',toggle:()=>this.setState({fbTags:{...s.fbTags,[k]:!on}})};});
    const picked=Object.keys(s.fbTags).filter(k=>s.fbTags[k]);
    const nm=k=>TAGS.find(x=>x[0]===k)[1];
    const inferred=s.fbPick===2?'Neither — not enough signal. Weights stay as you set them.':picked.length?picked.map(nm).join(' + ')+' matters a bit more than you said. Nudging +2.':'Tag a reason, or we keep your weights as they are.';
    const fb={pair,tags:tagsF,chosen:s.fbPick!=null,neitherOn:s.fbPick===2,neitherBg:s.fbPick===2?'var(--ink)':'var(--tile)',neitherColor:s.fbPick===2?'var(--bg)':'var(--ink)',neither:()=>this.setState({fbPick:2}),inferred,
      refresh:()=>{api.post('/ui/feedback',{session_id:SID,profile:this.profile(),a_id:A.id,b_id:B.id,pick:s.fbPick,tags:picked}).then(r=>{
          this.setState({w:r.weights,banner:r.banner,fbPick:null,fbTags:{}});this.applyMatch(r.match);this.go('results');
        }).catch(e=>{this.setState({banner:'Feedback not applied: '+e.message,fbPick:null,fbTags:{}});this.go('results');});}};
    // interest
    const il=this.get(s.interestId||this.selId());const ID=(s.interestData&&s.interestData.still_listed)?s.interestData:null;const ag=(ID&&ID.agent)||il.agent||{st:'missing'};const agOk=ag.st==='verified';
    const listedOk=ID?ID.still_listed.ok:true;
    const ck=(i,label,out,warn)=>{const ready=s.checks>i&&!!ID;return {label,pending:!ready,mark:ready?(warn?'!':'✓'):'',out:ready?out:'checking…',bg:ready?(warn?'var(--g-butter)':'var(--g-mint)'):'var(--soft)',markColor:ready?(warn?'var(--butter)':'var(--mint)'):'var(--bg)'};};
    const it={...ph(il),name:il.name,price:full$(il.price),id:il.id,wait:s.checks<2||!ID,op:(s.checks<2||!ID)?0.35:1,
      checks:[ck(0,'Still listed',listedOk?'active · '+hhmm(ID&&ID.still_listed.as_of):'no longer listed',!listedOk),ck(1,'Agent',agOk?'verified for this listing':ag.st==='unverified'?'not verified':'none on record',!agOk)]};
    // contact
    const FD=[['name','name','Wei Ling Ong'],['email','email','weiling.o@example.com'],['phone','phone','+65 9••• ••12'],['message','message','Is this home still available to view?']];
    const fields=FD.map(([k,label,value])=>{const on=!!s.fields[k];return {label,value,on,deco:on?'none':'line-through',op:on?1:0.4,track:on?'var(--ink)':'var(--line)',x:on?'23px':'3px',toggle:()=>this.setState({fields:{...s.fields,[k]:!on}})};});
    const noChannel=!s.fields.email&&!s.fields.phone;
    const ct={id:il.id,verified:agOk,notVerified:!agOk,fields,agent:ag.name||'',
      stBg:agOk?'var(--g-mint)':'var(--g-butter)',stInk:agOk?'var(--mint)':'var(--butter)',stMark:agOk?'✓':'!',stLabel:agOk?'verified agent':ag.st==='unverified'?'unverified':'no agent',
      headline:agOk?ag.name:'Can’t connect you directly.',stText:agOk?'Confirmed on our server for '+il.id+'.':'We won’t guess a contact. Use the original listing.',
      noChannel,cant:!s.consent||noChannel,op:!s.consent||noChannel?0.3:1};
    // outcome
    const OD=s.outcomeData||{};const when=hhmm(new Date().toISOString());
    const OC={submitted:{mark:'✓',bg:'var(--g-mint)',title:'Enquiry sent.',body:'Accepted by the authorised channel at '+when+'. Read receipt not guaranteed.',dest:(ag.name||'Agent')+' · enquiry form',ref:OD.ref||'—'},
      redirected:{mark:'↗',bg:'var(--g-lav)',title:'Opened the listing.',body:'No enquiry sent. None of your details were shared.',dest:'original listing page',ref:(OD.ref||'—')+' · no lead'},
      failed:{mark:'!',bg:'var(--g-rose)',title:'Not sent.',body:OD.reason||'The channel didn’t respond. Nothing was shared.',dest:(ag.name||'Agent')+' · enquiry form',ref:(OD.ref||'—')+' · failed',retry:true}}[s.outcome];
    const oc={...OC,ink:{submitted:'var(--mint)',redirected:'var(--lav)',failed:'var(--rose)'}[s.outcome],retry:!!OC.retry,rows:[{k:'listing',v:il.name},{k:'destination',v:OC.dest},{k:'reference',v:OC.ref}],
      // the real outcome is shown; these pills reflect it and do not fake another state
      states:[['submitted','sent'],['redirected','redirect'],['failed','failed']].map(([k,label])=>({label,bg:s.outcome===k?'var(--ink)':'transparent',color:s.outcome===k?'var(--bg)':'var(--ink)',pick:()=>{}}))};
    // evidence (real traces from the last pipeline runs + live health/metrics)
    const G='oklch(0.83 0.11 160)',Y='oklch(0.91 0.1 88)',DIM='oklch(0.65 0.012 270)';
    const TR=s.traces||{};const byName={};[...(TR.chat||[]),...(TR.match||[]),...(TR.finance||[])].forEach(x=>{byName[x.agent_name]=x;});
    const evAgents=[['buyer-intelligence','buyer_intelligence'],['market-intelligence','market_intelligence'],['valuation','valuation'],['affordability','affordability_risk'],['matching','matching_decision']].map(([name,key])=>{const x=byName[key];
      if(!x)return {name,note:'not run yet',ms:'—',mark:'·',color:DIM};const ok=x.status==='ok';return {name,note:x.detail||x.model_version||x.status,ms:Math.round(x.elapsed_ms)+'ms',mark:ok?'✓':'!',color:ok?G:Y};});
    const warns=[];const addW=w=>{if(w&&!warns.includes(w))warns.push(w);};
    (M?M.warnings:[]).forEach(addW);(s.chatWarn||[]).forEach(addW);Object.values(byName).forEach(x=>(x.warnings||[]).forEach(addW));
    if(s.health&&!s.health.listing_provider_healthy)addW('listing source stale: no successful scrape in the last 2 intervals');
    if(s.apiDown)addW('backend unreachable');
    const hl=s.health,mt=s.metrics;
    const refreshed=(M&&M.refreshed_at)||(hl&&hl.listings_last_refreshed_at);
    const ev={agents:evAgents,warns,bannerTitle:'live trace',banner:M?'Run '+String(M.run_id).slice(0,8)+' · '+M.counts.checked+' listings checked · refreshed '+timeAgo(refreshed)+'.':'No pipeline run yet — describe a home or open the profile.',
      p50:mt?Math.round(mt.p50_latency_ms)+'ms':'—',p95:mt?(mt.request_count<20?'unavailable · n<20':Math.round(mt.p95_latency_ms)+'ms'):'—',errors:mt?mt.error_count+'/'+mt.request_count:'—',
      model:hl?(hl.valuation_model_version+(hl.valuation_model_is_trained?'':' (baseline)')):'—',deploy:hl?(hl.architecture==='s390x'?'IBM LinuxONE · s390x · FastAPI':hl.architecture+' · FastAPI'):'—',
      source:hl?('PropertyGuru · '+hl.listing_catalog_size+' live listings'):'—'};
    const srcLabel=s.apiDown?'offline':'live data';
    const vs=s.vstate,listening=vs==='listening'||vs==='speaking',thinking=vs==='connecting';
    const v={on:listening,idle:vs==='idle',thinking,toggle:()=>this.toggleVoice(),aria:listening||thinking?'End voice chat':'Start talking',anim:listening?'breathe 1.6s ease-in-out infinite':'none',glow:listening?0.55:thinking?0.35:0.12,
      bars:Array.from({length:18},(_,i)=>({h:(14+Math.round(26*Math.abs(Math.sin(i*1.7))))+'px',d:(i*0.055)+'s'})),play:listening?'running':'paused',barOp:listening?0.9:0.25,
      text:s.vline?s.vline.text:(thinking?'Connecting to Gemini voice…':'Tap and say what you’re looking for.'),textColor:s.vline?'var(--ink)':'var(--muted)',
      foot:vs==='speaking'?'Homi is talking · interrupt any time':listening?'listening…':thinking?'connecting…':'Gemini voice · audio is streamed live, not stored'};
    const VK=[[/(\d)[- ]?(bed|bedroom|room)/i,m=>m[1]+'+ bedrooms','must'],[/(?:\$|under |below )\s?(\d{3,4})\s?k/i,m=>'≤ $'+m[1]+'k','must'],[/bishan/i,()=>'Bishan','must'],[/tampines/i,()=>'Tampines','must'],[/queenstown/i,()=>'Queenstown','must'],[/\b(hdb|condo)\b/i,m=>m[1].toUpperCase(),'must'],[/\bmrt\b/i,()=>'near an MRT','nice'],[/raffles/i,()=>'short commute → Raffles Pl','nice'],[/\b(size|space)\b/i,()=>'space: lower priority','nice']];
    const CAT={must:{bg:'var(--g-mint)',hc:'var(--mint)',tag:'MUST-HAVE · FILTERS',tint:'color-mix(in oklch,var(--mint) 45%,transparent)'},nice:{bg:'var(--g-lav)',hc:'var(--lav)',tag:'NICE-TO-HAVE · RANKS',tint:'color-mix(in oklch,var(--lav) 45%,transparent)'},ask:{bg:'var(--g-butter)',hc:'var(--butter)',tag:'NEEDS YOU'},unk:{bg:'var(--g-rose)',hc:'var(--rose)',tag:'WON’T GUESS'}};
    const vt=(s.vline&&s.vline.role==='user')?s.vline.text:'';const hits=[];VK.forEach(([re,fn,cat])=>{const m=vt.match(re);if(m)hits.push({i:m.index,len:m[0].length,label:fn(m),cat});});hits.sort((a,b)=>a.i-b.i);
    // while listening the chips are the on-device preview; once the backend has understood, its chips replace them
    const items=(s.mode==='voice')?(s.vchips||[]).map(c=>({label:c.label,cat:c.cat})).concat(hits.filter(h=>!(s.vchips||[]).length).map(h=>({label:h.label,cat:h.cat}))):(s.chat>=2&&s.chips&&s.chips.length)?s.chips.map(c=>({label:c.label,cat:c.cat})):hits.map(h=>({label:h.label,cat:h.cat}));
    const SL={must:[['5%','6%'],['2%','20%'],['6%','34%'],['2%','48%'],['5%','62%'],['2%','76%']],nice:[['5%','10%'],['2%','28%'],['6%','46%']],ask:[['2%','62%']],unk:[['2%','78%']]};
    const cnt={must:0,nice:0,ask:0,unk:0};
    const chips=items.map((it,i)=>{const c=CAT[it.cat];const slot=SL[it.cat][Math.min(cnt[it.cat]++,SL[it.cat].length-1)];const left=it.cat==='must';return {label:it.label,tag:c.tag,bg:c.bg,hc:c.hc,y:slot[1],left:left?slot[0]:'auto',right:left?'auto':slot[0],fd:(i*0.7)+'s'};});
    const segsV=[];let p=0;hits.forEach(h=>{if(h.i<p)return;segsV.push({text:vt.slice(p,h.i),bg:'transparent',pad:'0'});segsV.push({text:vt.slice(h.i,h.i+h.len),bg:CAT[h.cat].tint,pad:'3px'});p=h.i+h.len;});segsV.push({text:vt.slice(p)||(vt?'':v.text),bg:'transparent',pad:'0'});
    const vo={chips,segs:segsV,asking:false,done:s.mode==='voice'&&s.chat>=3,
      status:vs==='speaking'?'Homi is talking…':listening?'listening…':thinking||s.chat===1?'connecting…':s.chat>=3?'got it ✓':'tap me and talk',
      bodyAnim:listening?'orbListen 1.4s ease-in-out infinite':(thinking||s.chat===1)?'orbThink 1.2s ease-in-out infinite':'orbIdle 5s ease-in-out infinite',
      glow:listening?0.85:(thinking||s.chat===1)?0.6:0.4,spin:listening?'4s':(thinking||s.chat===1)?'2s':'12s',
      eyeH:(thinking||s.chat===1)?'34%':s.chat>=3?'16%':listening?'46%':'38%',
      lookX:(thinking||s.chat===1)?'-8px':(s.look?s.look.x:0)+'px',lookY:(thinking||s.chat===1)?'-7px':listening?'-5px':(s.look?s.look.y:0)+'px',
      blush:s.chat>=3?0.85:listening?0.6:0.45,shadowAnim:listening||(thinking||s.chat===1)?'none':'shIdle 5s ease-in-out infinite',
      mw:listening?'11%':(thinking||s.chat===1)?'8%':s.chat>=3?'26%':'18%',mh:listening?'15%':(thinking||s.chat===1)?'8%':s.chat>=3?'17%':'11%',
      mr:listening?'50%':(thinking||s.chat===1)?'50%':'0 0 999px 999px',mbg:listening||(thinking||s.chat===1)?'oklch(0.17 0.03 285)':'transparent',
      mb:listening||(thinking||s.chat===1)?'0 solid transparent':'3.5px solid oklch(0.17 0.03 285)',mbt:'transparent',
      legend:[{c:'var(--mint)',label:'must-have · filters'},{c:'var(--lav)',label:'nice-to-have · ranks'},{c:'var(--butter)',label:'needs your answer'},{c:'var(--rose)',label:'not said · won’t guess'}]};
    const modes=[['chat','Chat','✎'],['voice','Voice','●']].map(([k,label,icon])=>({label,icon,on:s.mode===k,bg:s.mode===k?'var(--ink)':'transparent',color:s.mode===k?'var(--bg)':'var(--ink)',pick:()=>{if(k==='chat'){this.stopVoice();this.setState({vstate:'idle'});}this.setState({mode:k});}}));
    // hub
    const VL=[...this.vlist()].sort((a,b)=>a.at-b.at);const now=Date.now();
    const base=new Date();base.setHours(0,0,0,0);const dayKey=t=>{const d=new Date(t);d.setHours(0,0,0,0);return d.getTime();};
    const ST={confirmed:{label:'agent confirmed',bg:'var(--g-mint)',dot:'var(--mint)'},requested:{label:'awaiting agent',bg:'var(--g-butter)',dot:'var(--butter)'},self:{label:'added by you',bg:'var(--g-lav)',dot:'var(--lav)'}};
    const CHK=[['a','Check water pressure & taps'],['b','Note light at this hour'],['c','Ask about remaining lease'],['d','Look for damp or cracks'],['e','Time the walk to MRT'],['f','Photograph the floor plan']];
    const upcoming=VL.filter(v=>v.at>=now);const selV=VL.find(v=>v.id===s.selV)||upcoming[0]||VL[0];
    const fmtWhen=t=>{const d=new Date(t);const dd=dayKey(t),tk=base.getTime();const rel=dd===tk?'Today':dd===tk+864e5?'Tomorrow':WD[d.getDay()]+' '+d.getDate()+' '+MO[d.getMonth()];return rel+', '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');};
    const cd=t=>{const ms=t-now;if(ms<0)return 'done';const dd=Math.floor(ms/864e5),hh=Math.floor(ms%864e5/36e5),mm=Math.floor(ms%36e5/6e4);return 'in '+(dd?dd+'d ':'')+(dd<3?hh+'h':'')+(!dd&&hh<3?' '+mm+'m':'');};
    const prog=v=>{const n=CHK.filter(c=>v.check&&v.check[c[0]]).length;return {n,pct:Math.round(n/CHK.length*100)+'%',txt:n+'/'+CHK.length};};
    const days=Array.from({length:8},(_,i)=>{const t=base.getTime()+i*864e5;const d=new Date(t);const vs=VL.filter(v=>dayKey(v.at)===t);const on=s.dayF===t;return {wd:i===0?'today':WD[d.getDay()].toLowerCase(),d:d.getDate(),dots:vs.map(v=>ST[v.st].dot),on,bg:on?'var(--ink)':vs.length?'var(--soft)':'transparent',color:on?'var(--bg)':'var(--ink)',pick:()=>this.setState({dayF:on?null:t})};});
    const shown=s.dayF!=null?VL.filter(v=>dayKey(v.at)===s.dayF):VL;
    const likedIds=Object.keys(s.like).filter(k=>s.like[k]);const shortL=(likedIds.length?likedIds.map(id=>this.get(id)):rk.slice(0,4).map(r=>r.l));
    let hubSel=null;if(selV){const h=this.get(selV.home),pr=prog(selV);hubSel={kicker:selV.at>=now?'next viewing':'past viewing',countdown:cd(selV.at),when:fmtWhen(selV.at),name:h.name,stLabel:ST[selV.st].label,stBg:ST[selV.st].bg,
      maps:'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(h.name+', '+h.town+', Singapore'),ics:()=>this.ics(selV),goNotes:()=>this.go('notes'),open:()=>{this.setState({sel:h.id});this.go('detail');},
      remove:()=>{const id=selV.id;this.setV(vs=>vs.filter(x=>x.id!==id));this.setState({selV:null});api.del(this.vpath(id)).catch(e=>{this.fail(e,'Could not remove');this.loadHub();});},
      prog:pr.txt+' done',pct:pr.pct,notes:selV.notes||'',onNotes:e=>{const val=e.target.value;this.setV(vs=>vs.map(x=>x.id===selV.id?{...x,notes:val}:x));this.patchV(selV.id,{notes:val},600);},
      checks:CHK.map(([k,label])=>{const on=!!(selV.check&&selV.check[k]);return {label,on,box:on?'var(--on)':'transparent',mark:on?'✓':'',deco:on?'line-through':'none',op:on?0.55:1,toggle:()=>{this.setV(vs=>vs.map(x=>x.id===selV.id?{...x,check:{...x.check,[k]:!on}}:x));this.patchV(selV.id,{checks:{[k]:!on}});}};})};}
    const selHome=selV?this.get(selV.home):shortL[0]||EMPTY;const mh=this.monthly(selHome);
    const enqL=s.enq.map(x=>{const h=this.get(x.id);return {name:h.name,mark:x.kind==='submitted'?'✓':x.kind==='redirected'?'↗':'!',status:x.kind==='submitted'?'sent '+sayWhen(x.at)+' · awaiting reply':x.kind==='redirected'?'opened listing · no details shared':'not sent · nothing shared'};});
    const mB=new Date(base.getFullYear(),base.getMonth()+s.calM,1);const off=(mB.getDay()+6)%7;const dim=new Date(mB.getFullYear(),mB.getMonth()+1,0).getDate();const ncell=Math.ceil((off+dim)/7)*7;
    const MOF=['January','February','March','April','May','June','July','August','September','October','November','December'];
    const cal={month:MOF[mB.getMonth()],year:mB.getFullYear(),wds:['mon','tue','wed','thu','fri','sat','sun'],prev:()=>this.setState({calM:s.calM-1}),next:()=>this.setState({calM:s.calM+1}),today:()=>this.setState({calM:0}),
      legend:[{c:'var(--mint)',label:'agent confirmed'},{c:'var(--butter)',label:'awaiting agent'},{c:'var(--lav)',label:'added by you'}],
      cells:Array.from({length:ncell},(_,i)=>{const d=new Date(mB.getFullYear(),mB.getMonth(),1-off+i);const t=d.getTime();const inM=d.getMonth()===mB.getMonth();const isT=t===base.getTime();const offD=Math.round((t-base.getTime())/864e5);const vs=VL.filter(v=>dayKey(v.at)===t);
        return {d:d.getDate(),op:inM?1:0.35,bg:isT?'var(--soft)':'transparent',ring:isT?'inset 0 0 0 2px var(--ink)':'none',fw:isT?700:500,numBg:isT?'var(--ink)':'transparent',numColor:isT?'var(--bg)':'var(--ink)',title:offD>=1?'Plan a viewing on this day':'',
          pick:()=>{if(offD>=1)this.openAdd(null,offD);else this.setState({dayF:t});},
          evts:vs.map(v=>{const h=this.get(v.home);const dd=new Date(v.at);const n=(v.photos||[]).length;return {time:String(dd.getHours()).padStart(2,'0')+':'+String(dd.getMinutes()).padStart(2,'0'),name:h.name.replace('Blk ',''),bg:ST[v.st].bg,ring:selV&&selV.id===v.id?'0 0 0 2px var(--ink)':'none',hasPh:n>0,ph:n,pick:e=>{e.stopPropagation();this.setState({selV:v.id});}};})};})};
    let nt={noSel:true};if(selV){const h=this.get(selV.home);const ps=selV.photos||[];const good=[],bad=[];
      const photos=ps.map(p=>{const o=p.obs;if(o){o.good.forEach(t=>good.push({text:t,room:o.room||'photo'}));o.bad.forEach(t=>bad.push({text:t,room:o.room||'photo'}));}
        return {url:p.url,alt:o&&o.room?o.room:'Viewing photo',loading:p.status==='loading',err:p.status==='error',filter:p.status==='loading'?'blur(3px) saturate(.7)':'none',room:o?o.room:'',roomShow:o&&o.room?'block':'none',
          obs:o?[...o.good.map(t=>({text:t,mark:'+',bg:'var(--g-mint)'})),...o.bad.map(t=>({text:t,mark:'−',bg:'var(--g-rose)'}))]:[],
          retry:()=>this.analyze(selV.id,p.id),remove:()=>{this.setV(vs=>vs.map(v=>v.id!==selV.id?v:{...v,photos:(v.photos||[]).filter(x=>x.id!==p.id)}));api.del(this.vpath(selV.id,'/photos/'+encodeURIComponent(p.id))).catch(()=>{});}};});
      nt={noSel:false,chk:prog(selV).txt,name:h.name,when:fmtWhen(selV.at).toLowerCase(),photos,noPhotos:!photos.length,photoN:photos.length,good,bad,goodN:good.length,badN:bad.length,hasObs:good.length+bad.length>0,
        dzBg:s.drag2?'color-mix(in oklch,var(--lav) 25%,transparent)':'var(--soft)',dzBorder:s.drag2?'var(--acc)':'var(--line)',
        onFiles:e=>{const fl=e.target.files;this.addPhotos(selV.id,fl);e.target.value='';},onOver:e=>{e.preventDefault();if(!s.drag2)this.setState({drag2:true});},onLeave:()=>this.setState({drag2:false}),
        onDrop:e=>{e.preventDefault();this.setState({drag2:false});this.addPhotos(selV.id,e.dataTransfer.files);}};}
    nt.count=VL.length+(VL.length===1?' viewing':' viewings');
    nt.picks=[...VL].sort((a,b)=>a.at-b.at).map(v=>{const h=this.get(v.home),on=!!selV&&selV.id===v.id,n=(v.photos||[]).length;return {when:fmtWhen(v.at).toLowerCase()+(n?' · ◉'+n:''),name:h.name.replace('Blk ',''),on,bg:on?'var(--ink)':'var(--soft)',color:on?'var(--bg)':'var(--ink)',pick:()=>this.setState({selV:v.id})};});
    const hub={today:WD[base.getDay()].toLowerCase()+' '+base.getDate()+' '+MO[base.getMonth()].toLowerCase(),
      stats:[{n:upcoming.length,label:'upcoming viewings',go:()=>this.setState({dayF:null})},{n:likedIds.length,label:'liked',go:()=>this.go('results')},{n:s.enq.length,label:'enquiries',go:()=>{}}],
      hasSel:!!hubSel,noSel:!hubSel,sel:hubSel||{},days,filtered:s.dayF!=null,filterLabel:s.dayF!=null?'· '+WD[new Date(s.dayF).getDay()]+' '+new Date(s.dayF).getDate():'· '+VL.length,clearFilter:()=>this.setState({dayF:null}),
      empty:shown.length===0,emptyTail:s.dayF!=null?' this day':'',
      list:shown.map(v=>{const h=this.get(v.home),pr=prog(v),d=new Date(v.at),on=selV&&v.id===selV.id;return {day:fmtWhen(v.at).split(',')[0],time:String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'),name:h.name,sub:h.town+' · '+k$(h.price)+(v.at<now?' · past':''),stLabel:ST[v.st].label,stBg:ST[v.st].bg,prog:pr.txt,pct:pr.pct,bg:on?'var(--soft)':'transparent',pick:()=>this.setState({selV:v.id})};}),
      short:shortL.filter(h=>h.id).map(h=>{const has=VL.some(v=>v.home===h.id&&v.at>=now);const sc=rk.find(r=>r.l.id===h.id);return {...ph(h),name:h.name,price:k$(h.price),score:sc?sc.score+' match':'—',heart:s.like[h.id]?'♥':'',open:()=>{this.setState({sel:h.id});this.go('detail');},planLabel:has?'✓ viewing planned':'+ plan viewing',plan:()=>this.openAdd(h.id)};}),
      enq:enqL,noEnq:!enqL.length,moneyFor:selHome.name.replace('Blk ',''),monthly:full$(mh.m),moneyNote:s.dp+'% down · '+s.rate.toFixed(1)+'% · '+s.ten+' yrs.'};
    const AD=s.add;const add={open:!!AD};
    if(AD){add.close=()=>this.setState({add:null});add.homes=(shortL.filter(h=>h.id)).concat(rk.map(r=>r.l)).filter((h,i,arr)=>arr.findIndex(x=>x.id===h.id)===i).slice(0,5).map(h=>({label:h.name.replace('Blk ',''),bg:AD.home===h.id?'var(--ink)':'var(--soft)',color:AD.home===h.id?'var(--bg)':'var(--ink)',pick:()=>this.setState({add:{...AD,home:h.id}})}));
      add.days=Array.from({length:Math.max(7,AD.day)},(_,i)=>{const d=new Date(base.getTime()+(i+1)*864e5);return {wd:WD[d.getDay()].toLowerCase(),d:d.getDate(),bg:AD.day===i+1?'var(--ink)':'var(--soft)',color:AD.day===i+1?'var(--bg)':'var(--ink)',pick:()=>this.setState({add:{...AD,day:i+1}})};});
      add.times=['10:00','11:00','14:00','17:00','19:30'].map(t=>({label:t,bg:AD.time===t?'var(--ink)':'var(--soft)',color:AD.time===t?'var(--bg)':'var(--ink)',pick:()=>this.setState({add:{...AD,time:t}})}));
      add.cant=!AD.home;add.op=AD.home?1:0.4;
      add.save=()=>{const [hh,mm]=AD.time.split(':').map(Number);const t=new Date(base.getTime()+AD.day*864e5);t.setHours(hh,mm);
        api.post('/ui/viewings',{session_id:SID,listing_id:AD.home,at_ms:t.getTime(),status:'self'}).then(v=>{this.setV(vs=>[...vs,v]);this.setState({add:null,selV:v.id,dayF:null});if(this.cur()!=='hub')this.go('hub');}).catch(e=>{this.setState({add:null});this.fail(e,'Could not save viewing');});};}
    const ACT=[['★','My move — viewings & plan','M',()=>this.go('hub'),'var(--g-mint)'],['＋','Add a viewing','V',()=>this.openAdd(),'var(--g-lav)'],['◉','Viewing notes & photos','',()=>this.go('notes'),'var(--g-rose)'],['✎','Describe a home (chat)','',()=>{this.setState({mode:'chat'});this.go('chat');},'var(--soft)'],['●','Talk to Homi (voice)','',()=>{this.setState({mode:'voice'});this.go('chat');},'var(--g-lav)'],['◧','Edit profile','',()=>this.go('prefs'),'var(--soft)'],['♥','See matches','',()=>this.go('results'),'var(--g-mint)'],['⇆','Compare homes','',()=>this.go('compare'),'var(--soft)'],['◫','Compare viewings & notes','',()=>this.openCmpV(),'var(--g-rose)'],['☾','Toggle light / dark','T',()=>this.toggleTheme({clientX:innerWidth/2,clientY:120}),'var(--g-butter)'],['⌁','System evidence','E',()=>{this.setState({evidence:true});this.loadSystem();},'var(--soft)']];
    const q=(s.pq||'').toLowerCase().trim();const fl=ACT.filter(a=>!q||a[1].toLowerCase().includes(q));const pi=Math.min(s.pi,Math.max(0,fl.length-1));
    const runA=a=>{this.setState({pal:false,pq:''});a[3]();};
    const pal={open:s.pal,q:s.pq,ref:el=>{this.palRef=el;},close:()=>this.setState({pal:false}),none:!fl.length,onQ:e=>this.setState({pq:e.target.value,pi:0}),
      onKey:e=>{if(e.key==='ArrowDown'){e.preventDefault();this.setState({pi:Math.min(pi+1,fl.length-1)});}else if(e.key==='ArrowUp'){e.preventDefault();this.setState({pi:Math.max(pi-1,0)});}else if(e.key==='Enter'){e.preventDefault();if(fl[pi])runA(fl[pi]);}else if(e.key==='Escape'){this.setState({pal:false});}},
      items:fl.map((a,i)=>({icon:a[0],label:a[1],key:a[2]||'↵',iconBg:a[4],on:i===pi,bg:i===pi?'var(--soft)':'transparent',run:()=>runA(a),hover:()=>this.setState({pi:i})}))};
    const upN=upcoming.length;
    const PM=!!this.props.printMode;
    // handoff: sending an enquiry needs a verified, authorised agent contact; otherwise open the source listing
    const record=(channel,consent)=>api.post('/ui/handoff',{session_id:SID,listing_id:il.id,channel,consent,fields:Object.keys(s.fields).filter(k=>s.fields[k])});
    const finish=r=>{this.setState({outcome:r.outcome,outcomeData:r});this.go('outcome');this.loadHub();};
    return {printAttr:PM?'1':'0',heroMinH:PM?'860px':'calc(100vh - 100px)',scrMinH:PM?'0px':'calc(100vh - 240px)',cal,nt,logoLight:this.theme()==='dark'?'none':'block',logoDark:this.theme()==='dark'?'block':'none',hub,add,pal,openAdd:()=>this.openAdd(),openPalette:()=>this.openPal(),goHub:()=>this.go('hub'),openCmpV:()=>this.openCmpV(),hubBtn:{n:upN,bg:scr==='hub'?'var(--ink)':'var(--soft)',color:scr==='hub'?'var(--bg)':'var(--ink)'},
      planFromOutcome:()=>{this.go('hub');this.openAdd(il.id);},planFromDetail:()=>this.openAdd(l.id),deck,onLook:e=>{const r=e.currentTarget.getBoundingClientRect();const x=Math.max(-1,Math.min(1,(e.clientX-(r.left+r.width/2))/(r.width/2))),y=Math.max(-1,Math.min(1,(e.clientY-(r.top+r.height*0.38))/(r.height/2)));if(this.lk)return;this.lk=requestAnimationFrame(()=>{this.lk=null;this.setState({look:{x:Math.round(x*9),y:Math.round(y*6)}});});},v,vo,modes,isChat:s.mode==='chat',isVoice:s.mode==='voice',goVoice:()=>{this.setState({mode:'voice'});this.go('chat');this.later(()=>this.startVoice(),450);},is,steps,showSteps:scr!=='landing',evidence:s.evidence,toggleEvidence:()=>{this.setState({evidence:!s.evidence});this.loadSystem();},
      toggleTheme:e=>this.toggleTheme(e),isDark:this.theme()==='dark',knob:this.theme()==='dark'?'37px':'3px',sunColor:this.theme()==='dark'?'var(--bg)':'var(--ink)',moonColor:this.theme()==='dark'?'var(--ink)':'var(--bg)',
      srcLabel,srcDot:s.apiDown?'var(--rose)':'var(--mint)',srcTitle:s.apiDown?'Backend unreachable':('Live inventory: scraped PropertyGuru listings'+(refreshed?', refreshed '+timeAgo(refreshed):'')),
      typed:HERO.slice(0,t),heard,mn,toggleMN:()=>this.setState({mn:!s.mn}),
      goLanding:go('landing'),goChat:go('chat'),goPrefs:go('prefs'),goResults:()=>{this.setState({exp:null});this.go('results');},goDetail:go('detail'),goCompare:go('compare'),goFeedback:go('feedback'),goContact:go('contact'),
      example:EXAMPLE,useExample:()=>this.send(EXAMPLE),draft:s.draft,onDraft:e=>this.setState({draft:e.target.value}),onKey:e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();this.send();}},send:()=>this.send(),
      chat:{empty:s.chat===0&&!(s.convo||[]).length,askText:s.askText||'',msgs:chatMsgs,quick,must:must.map((x,i)=>({label:x,delay:(i*0.07)+'s'})),nice:nice.map((x,i)=>({label:x,delay:(0.3+i*0.07)+'s'})),noRows:s.chat<2&&!(s.convo||[]).length,ask:s.chat===2&&!!s.askText},
      budgetInput:s.budgetInput,budget:s.budget,budgetW:Math.max(4,(s.budgetInput||'').length+0.5)+'ch',onBudgetRange:e=>{const v=+e.target.value;this.setProfile({budget:v,budgetInput:v.toLocaleString('en-SG')});},budgetErr:s.budget<100000,onBudget:e=>{const v=+(e.target.value.replace(/\D/g,'')||0);this.setProfile({budget:v,budgetInput:v?v.toLocaleString('en-SG'):''});},
      typeOpts,townOpts,minBed:s.minBed,bedMinus:()=>this.setProfile({minBed:Math.max(1,s.minBed-1)}),bedPlus:()=>this.setProfile({minBed:Math.min(5,s.minBed+1)}),softOpts,elig,
      res,dismissBanner:()=>this.setState({banner:null}),showExcluded:s.showExcluded,toggleExcluded:()=>this.setState({showExcluded:!s.showExcluded}),clearCmp:()=>this.setState({cmp:[]}),
      d,cmp,fb,it,ct,consent:s.consent,toggleConsent:()=>this.setState({consent:!s.consent}),
      submit:()=>{if(ct.cant)return;record('authorized_direct_lead',true).then(finish).catch(e=>{this.setState({outcome:'failed',outcomeData:{reason:e.message}});this.go('outcome');});},
      openOriginal:()=>{if(il.source_url){try{window.open(il.source_url,'_blank','noopener');}catch(e){}}record('original_listing',false).then(finish).catch(e=>{this.setState({outcome:'failed',outcomeData:{reason:e.message}});this.go('outcome');});},
      oc,ev};
  }
}
