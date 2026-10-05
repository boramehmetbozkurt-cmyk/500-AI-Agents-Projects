import React,{useEffect,useMemo,useRef,useState}from"react";
import{createRoot}from"react-dom/client";
import{Search,Play,RefreshCw,ShieldCheck,KeyRound,ChevronRight,ChevronDown,Server,CheckCircle2,XCircle,Paperclip,FileText,X,Globe,Plus,MessageSquare,Trash2,Activity,Download,Code2,Send,Sparkles,Menu,Settings,AlertTriangle,Clock,Hash,Wrench,Database,Lock,Cpu,Layers,BookOpen,Copy}from"lucide-react";
import{downloadFile,openapi,operations,request,starterBody,upload}from"./api";
import"./styles.css";

/* ------------------------------------------------------------------ helpers */
const methodClass=m=>"method "+m.toLowerCase();
const MODES=[["AUTO","Otomatik"],["WEB_RESEARCH","Web Araştırma"],["AI_ANALYSIS","Analiz"]];
const STEP_TR={understanding_question:"Soru anlaşılıyor",tool_selection:"Araç seçimi",planning:"Planlama",reading_attachments:"Dosyalar okunuyor",searching_sources:"Kaynaklar aranıyor",collecting_evidence:"Kanıt toplanıyor",generating_answer:"Cevap üretiliyor",checking_claims:"İddialar kontrol ediliyor",assurance:"Çıktı güvencesi"};
const STATUS_TR={PASS:"DOĞRULANDI",REVIEW:"İNCELEME GEREKLİ",BLOCKED:"ENGELLENDİ",ERROR:"HATA"};
const TOOL_TR={web_search:"Web araması",file_context:"Dosya bağlamı",model_provider:"Model sağlayıcı"};
const EXAMPLES=[
 {t:"Türkiye'nin başkenti neresidir?",d:"Web araştırması · kaynak doğrulama",m:"AUTO"},
 {t:"Python programlama dili kim tarafından ve ne zaman geliştirildi?",d:"Olgusal soru · çoklu kaynak",m:"WEB_RESEARCH"},
 {t:"Ekteki belgenin ana bulgularını özetle.",d:"Önce bir dosya ekleyin · dosya bağlamı",m:"AUTO"},
 {t:"Kuantum bilgisayarlar klasik şifrelemeyi nasıl tehdit ediyor?",d:"Araştırma · kanıt zinciri",m:"WEB_RESEARCH"},
];
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2,7);
const host=u=>{try{return new URL(u).hostname.replace(/^www\./,"")}catch{return u}};
const short=h=>h?String(h).slice(0,10)+"…"+String(h).slice(-6):"—";
function friendlyError(error){
 const status=error?.status;const detail=error?.data?.detail??error?.data?.error_code??error?.message??"bilinmeyen_hata";
 if(status===401)return"Kimlik doğrulama başarısız.";
 if(status===409&&String(detail).includes("release"))return"Dahili sürüm yapılandırması uyuşmuyor.";
 if(status===409&&String(detail).includes("replay"))return"Tekrar (replay) algılandı. İsteği yeniden çalıştırın.";
 if(status===429)return"İstek sınırı aşıldı. Lütfen biraz bekleyin.";
 if(status===503)return"Arka uç veya gerekli sağlayıcı kullanılamıyor.";
 return typeof detail==="string"?detail:JSON.stringify(detail);
}
function loadChats(){try{return JSON.parse(localStorage.getItem("orbythra-chats")||"[]")}catch{return[]}}
function saveChats(c){try{localStorage.setItem("orbythra-chats",JSON.stringify(c.slice(0,60)))}catch{}}
function downloadJson(name,data){const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}

/* Simple markdown-like rendering: paragraphs, **bold**, `code`, lists, [n] citations */
function Inline({text,onCite}){
 const parts=String(text).split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g);
 return <>{parts.map((p,i)=>{
  if(/^\*\*[^*]+\*\*$/.test(p))return <b key={i}>{p.slice(2,-2)}</b>;
  if(/^`[^`]+`$/.test(p))return <code key={i}>{p.slice(1,-1)}</code>;
  if(/^\[\d+\]$/.test(p))return <button className="cite" key={i} onClick={()=>onCite?.(Number(p.slice(1,-1)))}>{p.slice(1,-1)}</button>;
  return <React.Fragment key={i}>{p}</React.Fragment>;
 })}</>;
}
function Markdown({text,onCite}){
 const blocks=String(text||"").split(/\n{2,}/);
 return <div className="md">{blocks.map((b,i)=>{
  const lines=b.split("\n");
  if(lines.every(l=>/^\s*[-*•]\s+/.test(l)))return <ul key={i}>{lines.map((l,j)=><li key={j}><Inline text={l.replace(/^\s*[-*•]\s+/,"")} onCite={onCite}/></li>)}</ul>;
  if(lines.every(l=>/^\s*\d+[.)]\s+/.test(l)))return <ol key={i}>{lines.map((l,j)=><li key={j}><Inline text={l.replace(/^\s*\d+[.)]\s+/,"")} onCite={onCite}/></li>)}</ol>;
  if(/^#{1,3}\s/.test(lines[0]))return <h4 key={i}><Inline text={lines[0].replace(/^#+\s/,"")}/></h4>;
  return <p key={i}>{lines.map((l,j)=><React.Fragment key={j}>{j>0&&<br/>}<Inline text={l} onCite={onCite}/></React.Fragment>)}</p>;
 })}</div>;
}

/* ------------------------------------------------------------------ status bits */
function StatusBadge({status,small}){
 const s=status||"ERROR";
 return <span className={"badge st-"+s.toLowerCase()+(small?" small":"")}>{s==="PASS"?<CheckCircle2 size={small?11:13}/>:s==="ERROR"?<XCircle size={small?11:13}/>:<AlertTriangle size={small?11:13}/>}{STATUS_TR[s]||s}</span>;
}
function HashRow({label,value}){
 const[c,setC]=useState(false);
 if(!value)return null;
 return <div className="hashrow"><span>{label}</span><code title={value}>{short(value)}</code><button onClick={()=>{navigator.clipboard?.writeText(value);setC(true);setTimeout(()=>setC(false),1200)}} title="Kopyala">{c?<CheckCircle2 size={12}/>:<Copy size={12}/>}</button></div>;
}

/* ------------------------------------------------------------------ sources */
function SourceCards({sources,onFocus}){
 if(!sources?.length)return null;
 return <div className="sourcegrid">{sources.map((s,i)=>{
  const isFile=s.source_type==="attachment";
  const tag=isFile?"DOSYA":s.evidence_status==="DIRECT_EVIDENCE"?"KANIT":s.direct_fetch?"KANIT":"KEŞİF";
  const inner=<><div className="srchead"><span className="srcnum">{i+1}</span><span className={"srctag "+(isFile?"file":s.direct_fetch?"direct":"disc")}>{tag}</span></div><b>{s.title||host(s.url)}</b><small>{isFile?<><FileText size={11}/> {s.snippet?.slice(0,80)||"yüklenen dosya"}</>:<><Globe size={11}/> {s.publisher||host(s.url)}</>}</small></>;
  return isFile?<div className="srccard" key={s.source_id} onClick={()=>onFocus?.(i)}>{inner}</div>:<a className="srccard" key={s.source_id} href={s.url} target="_blank" rel="noreferrer">{inner}</a>;
 })}</div>;
}

/* ------------------------------------------------------------------ evidence panel */
function EvidencePanel({result,durationMs}){
 const[open,setOpen]=useState(false);
 const[tab,setTab]=useState("pipeline");
 const v=result.verification||{},r=result.receipt||{};
 const tools=r.selected_tools||[];
 const failed=v.failed_gates||[];
 const tabs=[["pipeline","Adımlar"],["claims","İddialar ("+(result.claims?.length||0)+")"],["evidence","Kanıt zinciri"],["receipt","Kriptografik makbuz"],["raw","Ham JSON"]];
 return <div className={"evidence"+(open?" open":"")}>
  <button className="evhead" onClick={()=>setOpen(!open)}>
   <ShieldCheck size={15}/><span>Doğrulama ve Kanıt</span>
   <StatusBadge status={result.status} small/>
   {v.model_assurance_status&&<em>güvence: {v.model_assurance_status}</em>}
   {v.v1_disposition&&<em>karar: {v.v1_disposition}</em>}
   {tools.length>0&&<em><Wrench size={10}/> {tools.map(t=>TOOL_TR[t]||t).join(", ")}</em>}
   {durationMs!=null&&<em><Clock size={10}/> {(durationMs/1000).toFixed(1)} sn</em>}
   <ChevronDown size={15} className="chev"/>
  </button>
  {open&&<div className="evbody">
   <div className="evstats">
    <div><b>{result.confidence!=null?Math.round(result.confidence*100)+"%":"—"}</b><span>Güven</span></div>
    <div><b>{result.sources?.length??0}</b><span>Kaynak</span></div>
    <div><b>{v.direct_source_count??0}</b><span>Doğrudan kanıt</span></div>
    <div><b>{v.evidence_gate_pass_rate!=null?Math.round(v.evidence_gate_pass_rate*100)+"%":"—"}</b><span>Kanıt kapısı geçişi</span></div>
    <div><b>{failed.length}</b><span>Başarısız kapı</span></div>
    <div><b>{result.effective_mode||"—"}</b><span>Etkin mod</span></div>
   </div>
   {failed.length>0&&<div className="gatefail"><AlertTriangle size={13}/> Başarısız kapılar: {failed.join(", ")}</div>}
   {result.warnings?.length>0&&<details className="warn"><summary>Uyarılar ({result.warnings.length})</summary><ul>{result.warnings.map((w,i)=><li key={i}><code>{w}</code></li>)}</ul></details>}
   <div className="evtabs">{tabs.map(([k,l])=><button key={k} className={tab===k?"on":""} onClick={()=>setTab(k)}>{l}</button>)}</div>
   {tab==="pipeline"&&<div className="pipeline">{(result.pipeline||[]).map((p,i)=><div className={"pipestep "+p.status.toLowerCase()} key={i}><div className="pipeidx">{i+1}</div><div><b>{STEP_TR[p.step]||p.step}</b><span>{p.detail}</span>{p.endpoint&&<code>{p.endpoint}</code>}</div><StatusBadge status={p.status} small/></div>)}</div>}
   {tab==="claims"&&<div className="claims">{(result.claims||[]).length===0&&<p className="muted">İddia çıkarılmadı.</p>}{(result.claims||[]).map((c,i)=><div className="claim" key={i}><div className="claimtop"><span className={"claimst "+String(c.status||"").toLowerCase()}>{c.status||"—"}</span>{c.nli_label&&<span className="nli">NLI: {c.nli_label}{c.nli_entailment!=null&&` · entailment ${Math.round(c.nli_entailment*100)}%`}</span>}</div><p>{c.claim}</p><small>Destekleyen: {(c.supporting_sources||[]).join(", ")||"—"}{(c.contradicting_sources||[]).length>0&&<> · Çelişen: {c.contradicting_sources.join(", ")}</>}</small></div>)}</div>}
   {tab==="evidence"&&<div className="evchain">{(result.sources||[]).length===0&&<p className="muted">Kaynak yok.</p>}{(result.sources||[]).map((s,i)=><div className="evitem" key={s.source_id}><span className="srcnum">{i+1}</span><div><b>{s.title}</b><small>{s.source_type==="attachment"?"dosya eki":s.url}</small><div className="evmeta"><em>{s.source_type}</em><em>{s.direct_fetch?"doğrudan indirildi":"yalnızca keşif"}</em>{s.retrieved_at&&<em>alındı: {new Date(s.retrieved_at*1000).toLocaleTimeString("tr-TR")}</em>}{s.published_at&&<em>yayın: {s.published_at}</em>}</div>{s.direct_fetch&&s.snippet&&<p>{s.snippet}</p>}</div></div>)}</div>}
   {tab==="receipt"&&<div className="receipt">
    <div className="hashes"><HashRow label="İstek kimliği" value={r.request_id}/><HashRow label="Nonce SHA-256" value={r.nonce_sha256}/><HashRow label="Sürüm SHA" value={r.release_sha}/><HashRow label="Yapılandırma SHA-256" value={r.configuration_sha256}/><HashRow label="Çıktı SHA-256" value={r.output_sha256}/><HashRow label="Kanıt manifesti SHA-256" value={r.evidence_manifest_sha256}/></div>
    <div className="kv"><span>Üretici</span><code>{r.generator||"—"}</code></div>
    <div className="kv"><span>Seçilen araçlar</span><code>{tools.join(", ")||"—"}</code></div>
    {r.attachment_ids?.length>0&&<div className="kv"><span>Ek kimlikleri</span><code>{r.attachment_ids.join(", ")}</code></div>}
    <div className="kv"><span>Yönlendirilen uç noktalar</span><div className="eps">{(r.routed_endpoints||[]).map(e=><code key={e}>{e}</code>)}</div></div>
    {r.engineering&&<details><summary>Mühendislik analizi</summary><pre>{JSON.stringify(r.engineering,null,2)}</pre></details>}
    <p className="boundary">{result.boundary}</p>
   </div>}
   {tab==="raw"&&<div className="raw"><div className="rawbar"><button onClick={()=>downloadJson(`orbythra-denetim-${(r.request_id||"kayit").slice(-12)}.json`,result)}><Download size={13}/> Denetim kaydını indir (JSON)</button><button onClick={()=>navigator.clipboard?.writeText(JSON.stringify(result,null,2))}><Copy size={13}/> Kopyala</button></div><pre>{JSON.stringify(result,null,2)}</pre></div>}
  </div>}
 </div>;
}

/* ------------------------------------------------------------------ messages */
function AssistantMessage({msg,apiKey,workspaceId}){
 const r=msg.result;
 const[focus,setFocus]=useState(null);
 const[exporting,setExporting]=useState(false);
 const[exportError,setExportError]=useState("");
 async function exportExcel(){
  if(!r||exporting)return;setExporting(true);setExportError("");
  try{const{blob,filename}=await downloadFile("/v11/answer/export/xlsx",{apiKey,workspaceId,body:r});const href=URL.createObjectURL(blob);const a=document.createElement("a");a.href=href;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),2000)}
  catch(e){setExportError(friendlyError(e))}finally{setExporting(false)}
 }
 if(msg.error)return <div className="msg assistant"><div className="avatar err"><XCircle size={15}/></div><div className="bubble errbubble"><b>Hata</b><p>{msg.error}</p></div></div>;
 if(!r)return null;
 const label=r.status==="PASS"?"Doğrulanmış cevap":r.status==="REVIEW"?"Cevap gösteriliyor · dış kanıt sınırlı":r.status==="BLOCKED"?"Çıktı engellendi":"Hata";
 return <div className="msg assistant"><div className={"avatar "+r.status.toLowerCase()}><ShieldCheck size={15}/></div><div className="bubble">
  <div className="bubblehead"><StatusBadge status={r.status}/><span className="label">{label}</span>{r.error_code&&<code className="errcode">{r.error_code.replaceAll("_"," ")}</code>}<button className="xlsxbtn" onClick={exportExcel} disabled={exporting} title="Arama sonuçlarını ve claimleri Excel olarak indir">{exporting?<RefreshCw size={13} className="spin"/>:<Download size={13}/>} {exporting?"Hazırlanıyor…":"Excel indir"}</button></div>{exportError&&<div className="exporterr"><AlertTriangle size={12}/> Excel indirilemedi: {exportError}</div>}
  {r.sources?.length>0&&<><div className="sectitle"><BookOpen size={12}/> Kaynaklar</div><SourceCards sources={r.sources} onFocus={setFocus}/></>}
  {r.status==="REVIEW"&&r.answer&&<div className="reviewnote"><AlertTriangle size={12}/> Cevap kullanılabilir; ancak dış kaynak kanıtı doğrulanmış PASS seviyesine ulaşmadı.</div>}{r.answer?<Markdown text={r.answer} onCite={n=>setFocus(n-1)}/>:<p className="muted">{r.status==="BLOCKED"?"Bu sorgu doğrudan kanıt gerektiriyor; gerekli kanıt/güvence kapıları geçilemediği için cevap yayınlanmadı.":"Cevap üretilmedi."}</p>}
  {focus!=null&&r.sources?.[focus]&&<div className="focussrc"><b>[{focus+1}] {r.sources[focus].title}</b><p>{r.sources[focus].direct_fetch&&r.sources[focus].snippet?r.sources[focus].snippet:r.sources[focus].url}</p><button onClick={()=>setFocus(null)}><X size={12}/></button></div>}
  <EvidencePanel result={r} durationMs={msg.durationMs}/>
 </div></div>;
}
function UserMessage({msg}){
 return <div className="msg user"><div className="bubble"><p>{msg.text}</p>{msg.files?.length>0&&<div className="msgfiles">{msg.files.map(f=><span key={f}><FileText size={11}/> {f}</span>)}</div>}<small>{MODES.find(m=>m[0]===msg.mode)?.[1]||msg.mode}</small></div></div>;
}
const THINK_STEPS=["Soru anlaşılıyor","Araçlar seçiliyor","Web'de aranıyor / dosyalar okunuyor","Kaynaklar indiriliyor","Kanıt doğrulanıyor","Çıktı güvencesi uygulanıyor"];
function Thinking(){
 const[i,setI]=useState(0);
 useEffect(()=>{const t=setInterval(()=>setI(x=>Math.min(x+1,THINK_STEPS.length-1)),1400);return()=>clearInterval(t)},[]);
 return <div className="msg assistant"><div className="avatar think"><Sparkles size={15}/></div><div className="bubble thinking"><div className="dots"><span/><span/><span/></div><ul>{THINK_STEPS.map((s,j)=><li key={s} className={j<i?"done":j===i?"now":""}>{j<i?<CheckCircle2 size={12}/>:<span className="ring"/>}{s}</li>)}</ul><small>Gerçek yürütülen adımlar cevapla birlikte "Doğrulama ve Kanıt" panelinde listelenir.</small></div></div>;
}

/* ------------------------------------------------------------------ chat view */
function Chat({chat,updateChat,apiKey,workspaceId,readiness}){
 const[query,setQuery]=useState("");
 const[mode,setMode]=useState("AUTO");
 const[files,setFiles]=useState([]);
 const[busy,setBusy]=useState(false);
 const[uploading,setUploading]=useState(false);
 const[drag,setDrag]=useState(false);
 const[uerr,setUerr]=useState("");
 const fileInput=useRef(null),bottom=useRef(null),ta=useRef(null);
 useEffect(()=>{bottom.current?.scrollIntoView({behavior:"smooth"})},[chat?.messages?.length,busy]);
 useEffect(()=>{if(ta.current){ta.current.style.height="auto";ta.current.style.height=Math.min(ta.current.scrollHeight,220)+"px"}},[query]);

 async function addFiles(list){
  const chosen=Array.from(list||[]);if(!chosen.length)return;
  setUploading(true);setUerr("");
  for(const f of chosen){try{const meta=await upload("/v11/answer/files",{apiKey,workspaceId,file:f});setFiles(p=>[...p.filter(x=>x.attachment_id!==meta.attachment_id),meta])}catch(e){setUerr(f.name+": "+friendlyError(e))}}
  setUploading(false);
 }
 async function removeFile(id){setFiles(p=>p.filter(x=>x.attachment_id!==id));try{await request("/v11/answer/files/"+encodeURIComponent(id),{apiKey,workspaceId,method:"DELETE"})}catch{}}

 async function send(text,forcedMode){
  const q=(text??query).trim();if(!q||busy)return;
  const m=forcedMode||mode;
  const userMsg={id:uid(),role:"user",text:q,mode:m,files:files.map(f=>f.filename),at:Date.now()};
  const title=chat.title||q.slice(0,48);
  updateChat({...chat,title,messages:[...chat.messages,userMsg]});
  setQuery("");setBusy(true);
  const t0=performance.now();
  let asst;
  try{
   const value=await request("/v11/answer",{apiKey,workspaceId,method:"POST",body:{query:q,mode:m,attachment_ids:files.map(f=>f.attachment_id)}});
   asst={id:uid(),role:"assistant",result:value,durationMs:Math.round(performance.now()-t0),at:Date.now()};
  }catch(e){asst={id:uid(),role:"assistant",error:friendlyError(e),durationMs:Math.round(performance.now()-t0),at:Date.now()}}
  updateChat(c=>({...c,title,messages:[...c.messages,asst]}));
  setBusy(false);
 }
 function onKey(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}
 const empty=!chat.messages.length;
 return <div className={"chat"+(drag?" drag":"")} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);addFiles(e.dataTransfer.files)}}>
  <div className="stream">
   {empty&&<div className="welcome">
    <div className="logo-glow"><ShieldCheck size={34}/></div>
    <h1>ORBYTHRA'ya sorun</h1>
    <p>Soru yazın veya dosya ekleyin. Ajan aracını kendisi seçer, web'de arar, kaynakları indirir ve her cevabı kanıt kapılarından geçirir. <b>DOĞRULANDI</b> etiketi yalnızca doğrudan kanıt bağlandığında verilir — demo için asla uydurulmaz.</p>
    {readiness&&<div className="caps">
     <span className={readiness.web_search_configured?"on":""}>{readiness.web_search_configured?<CheckCircle2 size={11}/>:<XCircle size={11}/>} Web araması{readiness.keyless_search_configured&&!readiness.google_search_configured?" (anahtarsız)":""}</span>
     <span className={readiness.file_attachments_supported?"on":""}>{readiness.file_attachments_supported?<CheckCircle2 size={11}/>:<XCircle size={11}/>} Dosya ekleri</span>
     <span className={readiness.llm_provider_configured?"on":""}>{readiness.llm_provider_configured?<CheckCircle2 size={11}/>:<XCircle size={11}/>} LLM sağlayıcı{!readiness.llm_provider_configured&&" (çıkarımsal mod)"}</span>
     <span className={readiness.release_binding_configured?"on":""}>{readiness.release_binding_configured?<CheckCircle2 size={11}/>:<XCircle size={11}/>} Sürüm bağlama</span>
     <span className={readiness.fail_closed_assurance?"on":""}><Lock size={11}/> Kapalı-başarısız güvence</span>
    </div>}
    <div className="examples">{EXAMPLES.map(e=><button key={e.t} onClick={()=>{setMode(e.m);send(e.t,e.m)}}><b>{e.t}<small>{e.d}</small></b><ChevronRight size={14}/></button>)}</div>
   </div>}
   {chat.messages.map(m=>m.role==="user"?<UserMessage key={m.id} msg={m}/>:<AssistantMessage key={m.id} msg={m} apiKey={apiKey} workspaceId={workspaceId}/>)}
   {busy&&<Thinking/>}
   <div ref={bottom}/>
  </div>
  <div className="composer">
   {drag&&<div className="dropzone"><Paperclip size={18}/> Dosyaları buraya bırakın</div>}
   {files.length>0&&<div className="filechips">{files.map(f=><span className="filechip" key={f.attachment_id} title={f.preview}><FileText size={13}/><b>{f.filename}</b><small>{String(f.kind).toUpperCase()} · {(f.text_chars||0).toLocaleString("tr-TR")} karakter</small><button onClick={()=>removeFile(f.attachment_id)} aria-label="Dosyayı kaldır"><X size={12}/></button></span>)}</div>}
   {uerr&&<div className="uerr"><AlertTriangle size={12}/> {uerr}</div>}
   <div className="inputrow">
    <input ref={fileInput} type="file" multiple hidden accept=".txt,.md,.csv,.tsv,.json,.yaml,.yml,.xml,.html,.log,.pdf,.docx,.py,.js,.jsx,.ts,.tsx,.java,.go,.rs,.c,.h,.cpp,.cs,.rb,.php,.sql,.sh" onChange={e=>{addFiles(e.target.files);e.target.value=""}}/>
    <button className="iconbtn" onClick={()=>fileInput.current?.click()} disabled={uploading} title="Dosya ekle (txt, md, csv, pdf, docx, kod)">{uploading?<RefreshCw size={16} className="spin"/>:<Paperclip size={16}/>}</button>
    <textarea ref={ta} rows={1} value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={onKey} placeholder="ORBYTHRA'ya bir soru sorun… (Enter: gönder · Shift+Enter: yeni satır)"/>
    <button className="sendbtn" onClick={()=>send()} disabled={busy||!query.trim()} title="Gönder">{busy?<RefreshCw size={16} className="spin"/>:<Send size={16}/>}</button>
   </div>
   <div className="composerfoot">
    <div className="modes">{MODES.map(([k,l])=><button key={k} className={mode===k?"on":""} onClick={()=>setMode(k)}>{l}</button>)}</div>
    <span className="hint"><Lock size={10}/> Doğrulama kapıları kapalı-başarısız çalışır · çalışma alanı: {workspaceId}</span>
   </div>
  </div>
 </div>;
}

/* ------------------------------------------------------------------ system status */
function Card({icon,title,children,ok}){return <div className={"card"+(ok===true?" ok":ok===false?" bad":"")}><div className="cardhead">{icon}<b>{title}</b>{ok===true&&<CheckCircle2 size={14} className="okic"/>}{ok===false&&<XCircle size={14} className="badic"/>}</div>{children}</div>}
function Row({k,v}){return <div className="row"><span>{k}</span><b>{v===true?"evet":v===false?"hayır":v==null?"—":String(v)}</b></div>}
function SystemStatus({apiKey,workspaceId}){
 const[ready,setReady]=useState(null),[readiness,setReadiness]=useState(null),[schema,setSchema]=useState(null),[err,setErr]=useState(""),[at,setAt]=useState(null);
 async function load(){
  setErr("");
  const[a,b,c]=await Promise.allSettled([request("/ready",{apiKey,workspaceId}),request("/v11/answer/readiness",{apiKey,workspaceId}),openapi()]);
  if(a.status==="fulfilled")setReady(a.value);else setErr(friendlyError(a.reason));
  if(b.status==="fulfilled")setReadiness(b.value);
  if(c.status==="fulfilled")setSchema(c.value);
  setAt(new Date());
 }
 useEffect(()=>{load()},[apiKey,workspaceId]);
 const ops=useMemo(()=>schema?operations(schema):[],[schema]);
 const groups=useMemo(()=>{const g={};for(const o of ops){const m=o.path.match(/^\/(v[\d.]+[a-z]?)/);const k=m?m[1]:"temel";g[k]=(g[k]||0)+1}return Object.entries(g).sort((x,y)=>x[0].localeCompare(y[0],undefined,{numeric:true}))},[ops]);
 const tags=useMemo(()=>[...new Set(ops.flatMap(o=>o.tags))].length,[ops]);
 return <div className="status">
  <div className="pagehead"><div><p className="eyebrow">CANLI SİSTEM KANITI</p><h2>Sistem durumu ve yetenekler</h2><span>Veriler doğrudan <code>/ready</code>, <code>/v11/answer/readiness</code> ve <code>/openapi.json</code> uç noktalarından çekilir.{at&&<> Son yenileme: {at.toLocaleTimeString("tr-TR")}</>}</span></div><button className="ghost" onClick={load}><RefreshCw size={14}/> Yenile</button></div>
  {err&&<div className="uerr"><AlertTriangle size={12}/> {err}</div>}
  <div className="cards">
   <Card icon={<Activity size={15}/>} title="Hazırlık" ok={ready?.ready}><Row k="Ortam" v={ready?.environment}/><Row k="Hazır" v={ready?.ready}/><Row k="Sürüm" v={ready?.release||ready?.release_sha?String(ready.release||ready.release_sha).slice(0,24):readiness?.release}/></Card>
   <Card icon={<Database size={15}/>} title="Veritabanı" ok={ready?.database_ready}><Row k="Hazır" v={ready?.database_ready}/><Row k="Arka uç" v={ready?.database_backend}/></Card>
   <Card icon={<Lock size={15}/>} title="Kriptografi" ok={ready?.crypto_configured}><Row k="Yapılandırıldı" v={ready?.crypto_configured}/><Row k="PQC modu" v={ready?.pqc_mode}/><Row k="PQC arka ucu" v={ready?.pqc_backend_ready}/></Card>
   <Card icon={<KeyRound size={15}/>} title="Kimlik doğrulama" ok={ready?.auth_configured}><Row k="Yapılandırıldı" v={ready?.auth_configured}/><Row k="Çalışma alanı" v={readiness?.workspace_id||workspaceId}/><Row k="Sürüm bağlama" v={readiness?.release_binding_configured}/></Card>
   <Card icon={<Globe size={15}/>} title="Arama sağlayıcısı" ok={readiness?.web_search_configured}><Row k="Web araması" v={readiness?.web_search_configured}/><Row k="Google PSE" v={readiness?.google_search_configured}/><Row k="Anahtarsız (DDG/Bing)" v={readiness?.keyless_search_configured}/><Row k="Kanıt sağlayıcı" v={readiness?.evidence_provider_configured??ready?.providers?.evidence}/></Card>
   <Card icon={<Cpu size={15}/>} title="LLM / Model" ok={readiness?.llm_provider_configured}><Row k="LLM sağlayıcı" v={readiness?.llm_provider_configured??ready?.providers?.llm}/><Row k="Üretici modu" v={readiness?.llm_provider_configured?"model":"çıkarımsal (extractive)"}/><Row k="Yalnızca-AI politikası" v={readiness?.ai_only_unverified_answer_policy}/></Card>
   <Card icon={<ShieldCheck size={15}/>} title="Güvence politikası" ok={readiness?.fail_closed_assurance}><Row k="Kapalı-başarısız" v={readiness?.fail_closed_assurance}/><Row k="Otomatik nonce" v={readiness?.automatic_nonce}/><Row k="Ham nonce açığa çıkar" v={readiness?.raw_nonce_exposed}/><Row k="Dosya ekleri" v={readiness?.file_attachments_supported}/></Card>
   <Card icon={<Layers size={15}/>} title="API yüzeyi" ok={!!schema}><Row k="Toplam uç nokta" v={ops.length||null}/><Row k="Etiket (modül)" v={tags||null}/><Row k="OpenAPI" v={schema?.openapi}/><Row k="Başlık" v={schema?.info?.title}/><Row k="Sürüm" v={schema?.info?.version}/></Card>
  </div>
  {groups.length>0&&<div className="groups"><h3><Code2 size={14}/> Sürüm gruplarına göre uç noktalar</h3><div className="grouplist">{groups.map(([k,n])=><span key={k}><b>{k}</b>{n}</span>)}</div></div>}
  {ready?.capabilities?.length>0&&<div className="groups"><h3><Sparkles size={14}/> Bildirilen yetenekler ({ready.capabilities.length})</h3><div className="caplist">{ready.capabilities.map(c=><span key={c}>{c}</span>)}</div></div>}
  {ready&&<details className="rawdetails"><summary>Ham /ready yanıtı</summary><pre>{JSON.stringify(ready,null,2)}</pre></details>}
 </div>;
}

/* ------------------------------------------------------------------ API explorer (preserved) */
function ApiExplorer({apiKey,workspaceId}){
 const[schema,setSchema]=useState(null),[selected,setSelected]=useState(null),[filter,setFilter]=useState(""),[tag,setTag]=useState("ALL"),[body,setBody]=useState(""),[params,setParams]=useState({}),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[err,setErr]=useState("");
 async function load(){setErr("");try{setSchema(await openapi())}catch(e){setErr(e.message)}}
 useEffect(()=>{load()},[]);
 const ops=useMemo(()=>schema?operations(schema):[],[schema]);
 const tags=useMemo(()=>["ALL",...new Set(ops.flatMap(o=>o.tags))],[ops]);
 const filtered=ops.filter(o=>(tag==="ALL"||o.tags.includes(tag))&&((o.path+" "+o.summary+" "+o.method).toLowerCase().includes(filter.toLowerCase())));
 function choose(o){setSelected(o);setResult(null);setParams(Object.fromEntries((o.parameters||[]).map(p=>[p.name,p.schema?.default??""])));setBody(starterBody(o,schema))}
 function concretePath(){let p=selected.path;for(const x of selected.parameters||[])if(x.in==="path")p=p.replace("{"+x.name+"}",encodeURIComponent(params[x.name]??""));const qs=(selected.parameters||[]).filter(x=>x.in==="query"&&params[x.name]!==""&&params[x.name]!=null).map(x=>encodeURIComponent(x.name)+"="+encodeURIComponent(params[x.name])).join("&");return p+(qs?"?"+qs:"")}
 async function run(){if(!selected)return;if(["DELETE","PUT","PATCH"].includes(selected.method)&&!window.confirm("Sonuç doğuran API işlemini onaylayın: "+selected.method+" "+selected.path))return;setBusy(true);setResult(null);try{let parsed=undefined;if(body.trim())parsed=JSON.parse(body);const value=await request(concretePath(),{apiKey,workspaceId,method:selected.method,body:parsed});setResult({ok:true,value})}catch(e){setResult({ok:false,status:e.status,error:e.data??e.message})}finally{setBusy(false)}}
 return <div className="advancedcard"><div className="advancedhead"><div><p className="eyebrow">GELİŞMİŞ</p><h2>API Konsolu</h2><span>Tam OpenAPI yüzeyi. Normal kullanıcıların bu ekrana ihtiyacı yoktur.</span></div><button className="ghost" onClick={load}><RefreshCw size={14}/> Şemayı yenile</button></div>{err&&<div className="uerr">{err}</div>}
  <div className="tagrow">{tags.map(t=><button key={t} className={tag===t?"tagon":""} onClick={()=>setTag(t)}>{t==="ALL"?"TÜMÜ":t}</button>)}</div>
  <div className="console"><section className="catalog"><div className="search"><Search size={15}/><input placeholder="Yol, yöntem veya işlem ara…" value={filter} onChange={e=>setFilter(e.target.value)}/></div><div className="count">{filtered.length} işlem</div><div className="oplist">{filtered.map(o=><button className={selected===o?"op selected":"op"} key={o.method+o.path} onClick={()=>choose(o)}><span className={methodClass(o.method)}>{o.method}</span><span><b>{o.path}</b><small>{o.summary}</small></span><ChevronRight size={14}/></button>)}</div></section>
   <section className="runner">{!selected?<div className="empty"><Server size={34}/><h2>Bir uç nokta seçin</h2><p>Kayıtlı her rota canlı OpenAPI şemasından üretilir.</p></div>:<><div className="rhead"><span className={methodClass(selected.method)}>{selected.method}</span><div><h2>{selected.path}</h2><p>{selected.summary}</p></div></div>{(selected.parameters||[]).length>0&&<div className="panel"><h3>Parametreler</h3>{selected.parameters.map(p=><label key={p.in+p.name}>{p.name} <em>{p.in}{p.required?" · zorunlu":""}</em><input value={params[p.name]??""} onChange={e=>setParams({...params,[p.name]:e.target.value})}/></label>)}</div>}{selected.requestBody&&<div className="panel"><h3>JSON İstek Gövdesi</h3><textarea value={body} onChange={e=>setBody(e.target.value)} spellCheck="false"/></div>}<div className="execute"><code>{concretePath()}</code><button onClick={run} disabled={busy}><Play size={14}/>{busy?"Çalışıyor…":"Çalıştır"}</button></div>{result&&<div className={result.ok?"response good":"response bad"}><h3>{result.ok?<><CheckCircle2 size={16}/> Yanıt</>:<><XCircle size={16}/> Hata {result.status||""}</>}</h3><pre>{JSON.stringify(result.ok?result.value:result.error,null,2)}</pre></div>}</>}</section>
  </div>
 </div>;
}
function Advanced({apiKey,setApiKey,workspaceId,setWorkspaceId}){
 const[showKey,setShowKey]=useState(false);
 return <div className="advancedpage">
  <details className="settings"><summary><Settings size={14}/> Geliştirici ayarları (isteğe bağlı)</summary>
   <div className="settingsbody"><p>Demo derlemesi yerel anahtarı proxy üzerinden otomatik ekler; bu alanlar yalnızca üretim kimlik bilgileri için gereklidir.</p>
    <label>API Anahtarı<div className="keyfield"><input type={showKey?"text":"password"} value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder="(demo: boş bırakın)"/><button onClick={()=>setShowKey(!showKey)}>{showKey?"Gizle":"Göster"}</button></div></label>
    <label>Çalışma alanı<input value={workspaceId} onChange={e=>setWorkspaceId(e.target.value)} onBlur={()=>sessionStorage.setItem("orbythra-workspace",workspaceId)}/></label>
   </div></details>
  <ApiExplorer apiKey={apiKey} workspaceId={workspaceId}/>
 </div>;
}

/* ------------------------------------------------------------------ app shell */
function App(){
 const[view,setView]=useState("chat");
 const[apiKey,setApiKey]=useState("");
 const[workspaceId,setWorkspaceId]=useState(sessionStorage.getItem("orbythra-workspace")||"default");
 const[chats,setChats]=useState(()=>{const c=loadChats();return c.length?c:[{id:uid(),title:"",messages:[],at:Date.now()}]});
 const[activeId,setActiveId]=useState(()=>chats[0]?.id);
 const[sideOpen,setSideOpen]=useState(false);
 const[readiness,setReadiness]=useState(null);
 useEffect(()=>{saveChats(chats)},[chats]);
 useEffect(()=>{request("/v11/answer/readiness",{apiKey,workspaceId}).then(setReadiness).catch(()=>setReadiness(null))},[apiKey,workspaceId]);
 const active=chats.find(c=>c.id===activeId)||chats[0];
 function updateChat(next){setChats(cs=>cs.map(c=>c.id===active.id?(typeof next==="function"?next(c):next):c))}
 function newChat(){if(active&&!active.messages.length)return;const c={id:uid(),title:"",messages:[],at:Date.now()};setChats(cs=>[c,...cs]);setActiveId(c.id);setView("chat");setSideOpen(false)}
 function delChat(id){setChats(cs=>{const n=cs.filter(c=>c.id!==id);if(!n.length)n.push({id:uid(),title:"",messages:[],at:Date.now()});if(id===activeId)setActiveId(n[0].id);return n})}
 const navs=[["chat","Sohbet",<MessageSquare size={15}/>],["status","Sistem durumu",<Activity size={15}/>],["advanced","Gelişmiş / API Konsolu",<Server size={15}/>]];
 return <div className={"appshell"+(sideOpen?" sideopen":"")}>
  <div className="scrim" onClick={()=>setSideOpen(false)}/>
  <aside className="sidebar">
   <div className="brand"><div className="mark"><ShieldCheck size={18}/></div><div><b>ORBYTHRA</b><small>DOĞRULANABİLİR GENEL AJAN</small></div><button className="closeside" onClick={()=>setSideOpen(false)}><X size={16}/></button></div>
   <button className="newchat" onClick={newChat}><Plus size={15}/> Yeni sohbet</button>
   <nav className="primarynav">{navs.map(([k,l,ic])=><button key={k} className={view===k?"navon":""} onClick={()=>{setView(k);setSideOpen(false)}}>{ic} {l}</button>)}</nav>
   <div className="histhead">Sohbet geçmişi</div>
   <div className="history">{chats.map(c=><div key={c.id} className={"hist"+(c.id===activeId&&view==="chat"?" on":"")}><button className="histbtn" onClick={()=>{setActiveId(c.id);setView("chat");setSideOpen(false)}}><MessageSquare size={13}/><span>{c.title||"Yeni sohbet"}</span></button><button className="histdel" onClick={()=>delChat(c.id)} title="Sil"><Trash2 size={12}/></button></div>)}</div>
   <div className="boundary"><ShieldCheck size={13}/> Normalize → İddia → Kanıt → Güvence</div>
  </aside>
  <main className="content">
   <header className="topbar"><button className="menubtn" onClick={()=>setSideOpen(true)}><Menu size={18}/></button><div><p className="eyebrow">ORBYTHRA</p><b>{view==="chat"?(active?.title||"Doğrulanabilir sohbet asistanı"):view==="status"?"Sistem durumu ve yetenek kanıtı":"Geliştirici kontrol düzlemi"}</b></div><div className="topright">{readiness&&<span className={"pill "+(readiness.web_search_configured?"on":"")}><Globe size={11}/> {readiness.web_search_configured?"Web açık":"Web kapalı"}</span>}{readiness&&<span className={"pill "+(readiness.llm_provider_configured?"on":"warn")}><Cpu size={11}/> {readiness.llm_provider_configured?"LLM bağlı":"LLM yok · çıkarımsal"}</span>}<span className="pill"><Hash size={11}/> {workspaceId}</span></div></header>
   {view==="chat"&&active&&<Chat key={active.id} chat={active} updateChat={updateChat} apiKey={apiKey} workspaceId={workspaceId} readiness={readiness}/>}
   {view==="status"&&<SystemStatus apiKey={apiKey} workspaceId={workspaceId}/>}
   {view==="advanced"&&<Advanced apiKey={apiKey} setApiKey={setApiKey} workspaceId={workspaceId} setWorkspaceId={setWorkspaceId}/>}
  </main>
 </div>;
}
createRoot(document.getElementById("root")).render(<App/>);
