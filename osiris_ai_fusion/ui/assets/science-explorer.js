(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {mode:"scientists", query:"", results:[], selected:null, info:null, graph:null};
  const els = {
    modes:$("modes"), form:$("searchForm"), query:$("query"), ingest:$("ingestBtn"),
    results:$("results"), resultsTitle:$("resultsTitle"), count:$("resultCount"), stats:$("stats"),
    sourceStrip:$("sourceStrip"), detailTitle:$("detailTitle"), detailSource:$("detailSource"),
    detailSummary:$("detailSummary"), detailMeta:$("detailMeta"), detailJson:$("detailJson"),
    graph:$("graph"), graphNote:$("graphNote"), rebuild:$("rebuildGraph"), refresh:$("refreshGraph"),
    sourceCards:$("sourceCards"), apiStatus:$("apiStatus"), accessBtn:$("accessBtn"),
    accessDialog:$("accessDialog"), apiKeyInput:$("apiKeyInput"), saveAccess:$("saveAccess")
  };
  const SVG_NS = "http://www.w3.org/2000/svg";

  function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);}
  function key(){return sessionStorage.getItem("fusion_api_key")||"";}
  function headers(extra={}){return key()?{"X-API-Key":key(),...extra}:extra;}
  async function json(url, options={}){
    const response=await fetch(url,{cache:"no-store",...options,headers:{...headers(),...(options.headers||{})}});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(typeof payload.detail==="string"?payload.detail:`HTTP ${response.status}`);
    return payload;
  }
  function fmt(v){if(v===null||v===undefined||v==="")return "—";if(typeof v==="object")return JSON.stringify(v);return String(v);}
  function modeLabel(){return ({scientists:"Scientist search",works:"Scholarly works",gene:"Gene / DNA reference",protein:"Protein knowledge",variant:"Public variant assertions"})[state.mode];}
  function endpoint(q){const e=encodeURIComponent(q);return ({scientists:`/science/scientists/search?q=${e}&limit=30`,works:`/science/works/search?q=${e}&limit=30`,gene:`/science/genes/${e}`,protein:`/science/proteins/search?gene=${e}&limit=30`,variant:`/science/variants/search?q=${e}&limit=30`})[state.mode];}
  function ingestKind(){return state.mode==="gene"?"gene":state.mode==="protein"?"protein":state.mode==="variant"?"variant":state.mode;}
  function flatten(payload){
    if(state.mode==="scientists") return [...(payload.openalex||[]),...(payload.wikidata_candidates||[])];
    if(state.mode==="works") return payload.works||[];
    if(state.mode==="gene") return payload.records||[];
    if(state.mode==="protein") return payload.proteins||[];
    if(state.mode==="variant") return payload.variants||[];
    return [];
  }
  function summary(row){
    const bits=[];
    if(row.orcid) bits.push(row.orcid);
    if(row.publication_year) bits.push(row.publication_year);
    if(row.works_count!==undefined) bits.push(`${row.works_count} works`);
    if(row.cited_by_count!==undefined) bits.push(`${row.cited_by_count} citations`);
    if(row.assembly_name) bits.push(row.assembly_name);
    if(row.seq_region_name) bits.push(`chr ${row.seq_region_name}`);
    if(row.genes?.length) bits.push(`genes: ${row.genes.map(g=>typeof g==="string"?g:(g.symbol||g.name||"")).filter(Boolean).slice(0,4).join(", ")}`);
    if(row.description) bits.push(row.description);
    return bits.filter(Boolean).join(" · ")||row.entity_type||"record";
  }
  function renderResults(){
    els.resultsTitle.textContent=modeLabel(); els.count.textContent=String(state.results.length);
    if(!state.results.length){els.results.className="results empty";els.results.textContent="Sonuç bulunamadı.";return;}
    els.results.className="results";
    els.results.innerHTML=state.results.map((row,i)=>`<button class="result${state.selected===row?" active":""}" data-index="${i}" type="button"><div class="result-head"><strong>${esc(row.name||row.external_id||"Unnamed")}</strong><span class="source-tag">${esc(row.source_id||"source")}</span></div><small>${esc(summary(row))}</small></button>`).join("");
    els.results.querySelectorAll("button[data-index]").forEach(btn=>btn.addEventListener("click",()=>select(Number(btn.dataset.index))));
  }
  function select(index){
    const row=state.results[index];if(!row)return;state.selected=row;renderResults();
    els.detailTitle.textContent=row.name||row.external_id||"Entity";els.detailSource.textContent=row.source_id||"source";
    els.detailSummary.textContent=summary(row);
    const rows=[
      ["Entity",row.entity_type],["Canonical key",row.canonical_key],["External ID",row.external_id],
      ["ORCID",row.orcid],["DOI",row.doi],["Assembly",row.assembly_name],["Region",row.seq_region_name],
      ["Reviewed",row.reviewed===undefined?null:String(row.reviewed)],["Medical boundary",row.medical_use]
    ].filter(([,v])=>v!==undefined&&v!==null&&v!=="");
    els.detailMeta.innerHTML=rows.map(([k,v])=>`<div class="meta-row"><span>${esc(k)}</span><span>${esc(fmt(v))}</span></div>`).join("");
    els.detailJson.textContent=JSON.stringify(row,null,2);
  }
  function renderInfo(){
    if(!state.info)return;
    const counts=state.info.counts||{};const entityCount=Object.values(counts).reduce((a,b)=>a+Number(b||0),0);
    const edgeCount=state.graph?.edge_count||0;
    els.stats.innerHTML=`<div><strong>${entityCount}</strong><span>ENTITIES</span></div><div><strong>${edgeCount}</strong><span>EDGES</span></div><div><strong>${(state.info.sources||[]).length}</strong><span>SOURCES</span></div>`;
    els.sourceStrip.innerHTML=(state.info.sources||[]).map(s=>`<span>${esc(s.id)}</span>`).join("");
    els.sourceCards.innerHTML=(state.info.sources||[]).map(s=>`<article class="source-card"><h3>${esc(s.id)}</h3><p>${esc(s.domain)} · ${esc(s.mode)}</p><div class="license">${esc(s.license)} · ${esc(s.commercial_use)}</div></article>`).join("");
  }
  async function search(event){
    event?.preventDefault();const q=els.query.value.trim();if(!q)return;state.query=q;els.results.className="results empty";els.results.textContent="Live kaynaklar aranıyor…";
    try{const payload=await json(endpoint(q));state.results=flatten(payload);state.selected=null;renderResults();els.ingest.disabled=!state.results.length;}
    catch(error){state.results=[];renderResults();els.results.textContent=`Arama başarısız: ${error.message||error}`;els.ingest.disabled=true;}
  }
  async function ingest(){
    if(!state.query)return;els.ingest.disabled=true;els.ingest.textContent="INGESTING…";
    try{
      const payload=await json("/science/ingest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:ingestKind(),query:state.query,limit:50})});
      await json("/science/graph/rebuild?limit=100000",{method:"POST"});
      els.graphNote.textContent=`${payload.stored||0} entity stored · graph rebuilt.`;await bootInfo();await loadGraph();
    }catch(error){els.graphNote.textContent=`Ingest başarısız: ${error.message||error}`;}finally{els.ingest.disabled=false;els.ingest.textContent="INGEST QUERY";}
  }
  function nodeColor(type){if(type==="scientist")return "#64e8ff";if(type==="work")return "#a48cff";if(type==="gene")return "#72f1b8";if(type==="protein")return "#ffc16b";if(type==="variant")return "#ff7bd5";return "#8ea4b9";}
  function svg(name,attrs={}){const el=document.createElementNS(SVG_NS,name);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));return el;}
  function renderGraph(){
    const data=state.graph||{nodes:[],edges:[]};const nodes=(data.nodes||[]).slice(0,120);const map=new Map(nodes.map(n=>[n.canonical_key,n]));
    (data.edges||[]).slice(0,400).forEach(e=>{if(!map.has(e.source_key))map.set(e.source_key,{canonical_key:e.source_key,name:e.metadata?.author_name||e.metadata?.gene_symbol||e.source_key,entity_type:"reference"});if(!map.has(e.target_key))map.set(e.target_key,{canonical_key:e.target_key,name:e.metadata?.institution_name||e.metadata?.topic_name||e.target_key,entity_type:"reference"});});
    const all=[...map.values()].slice(0,160);const pos=new Map();const cx=700,cy=310,rings=[130,225,290];
    all.forEach((n,i)=>{const ring=rings[i%rings.length],angle=(Math.PI*2*i/Math.max(1,all.length))+((i%3)*.55);pos.set(n.canonical_key,{x:cx+Math.cos(angle)*ring,y:cy+Math.sin(angle)*ring});});
    els.graph.innerHTML="";const eg=svg("g");(data.edges||[]).slice(0,400).forEach(e=>{const a=pos.get(e.source_key),b=pos.get(e.target_key);if(!a||!b)return;const line=svg("line",{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:"edge"});const t=svg("title");t.textContent=e.relation;line.appendChild(t);eg.appendChild(line);});els.graph.appendChild(eg);
    const ng=svg("g");all.forEach(n=>{const p=pos.get(n.canonical_key);const g=svg("g",{class:"node",tabindex:"0"});const c=svg("circle",{cx:p.x,cy:p.y,r:9,fill:nodeColor(n.entity_type)});const text=svg("text",{x:p.x+13,y:p.y+4});text.textContent=String(n.name||n.canonical_key).slice(0,25);const title=svg("title");title.textContent=n.canonical_key;g.append(c,text,title);ng.appendChild(g);});els.graph.appendChild(ng);
    els.graphNote.textContent=`${data.node_count||0} stored nodes · ${data.edge_count||0} stored edges · first ${all.length} rendered.`;
  }
  async function loadGraph(){if(!key())return;try{state.graph=await json("/science/graph?entity_limit=1000&edge_limit=5000");renderGraph();renderInfo();}catch(error){els.graphNote.textContent=`Graph yüklenemedi: ${error.message||error}`;}}
  async function bootInfo(){if(!key()){els.apiStatus.textContent="AUTH REQUIRED";return;}try{state.info=await json("/science");els.apiStatus.textContent="CONNECTED";els.apiStatus.className="badge";renderInfo();}catch(error){els.apiStatus.textContent="AUTH ERROR";els.graphNote.textContent=error.message||error;}}
  function setMode(mode){state.mode=mode;state.results=[];state.selected=null;els.modes.querySelectorAll("button[data-mode]").forEach(b=>b.classList.toggle("active",b.dataset.mode===mode));els.resultsTitle.textContent=modeLabel();els.results.className="results empty";els.results.textContent="Bir sorgu çalıştır.";els.count.textContent="0";els.ingest.disabled=true;}
  function wire(){
    els.modes.querySelectorAll("button[data-mode]").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.mode)));
    els.form.addEventListener("submit",search);els.ingest.addEventListener("click",ingest);els.refresh.addEventListener("click",loadGraph);
    els.rebuild.addEventListener("click",async()=>{try{const r=await json("/science/graph/rebuild?limit=100000",{method:"POST"});els.graphNote.textContent=`${r.edges_written||0} edges rebuilt.`;await loadGraph();}catch(e){els.graphNote.textContent=e.message||e;}});
    els.accessBtn.addEventListener("click",()=>{els.apiKeyInput.value=key();els.accessDialog.showModal();});
    els.saveAccess.addEventListener("click",()=>{const v=els.apiKeyInput.value.trim();if(v)sessionStorage.setItem("fusion_api_key",v);else sessionStorage.removeItem("fusion_api_key");setTimeout(async()=>{await bootInfo();await loadGraph();},0);});
  }
  async function boot(){wire();await bootInfo();await loadGraph();if(!key())els.accessDialog.showModal();}
  boot();
})();
