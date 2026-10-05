const BASE=(import.meta.env.VITE_API_BASE_URL||"").replace(/\/$/,"");
export async function request(path,{apiKey,workspaceId,method="GET",body}={}){
 const headers={Accept:"application/json"};if(body!==undefined)headers["Content-Type"]="application/json";
 const effectiveApiKey=(apiKey||"").trim();
 const effectiveWorkspace=(workspaceId||"default").trim()||"default";
 if(effectiveApiKey)headers["X-API-Key"]=effectiveApiKey;
 headers["X-Workspace-ID"]=effectiveWorkspace;
 const r=await fetch(BASE+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
 const raw=await r.text();let data;try{data=raw?JSON.parse(raw):null}catch{data=raw}
 if(!r.ok){const e=new Error(typeof data==="object"?JSON.stringify(data):String(data));e.status=r.status;e.data=data;throw e}return data;
}
export async function upload(path,{apiKey,workspaceId,file}={}){
 const headers={Accept:"application/json"};
 const effectiveApiKey=(apiKey||"").trim();
 if(effectiveApiKey)headers["X-API-Key"]=effectiveApiKey;
 headers["X-Workspace-ID"]=(workspaceId||"default").trim()||"default";
 const form=new FormData();form.append("file",file,file.name);
 const r=await fetch(BASE+path,{method:"POST",headers,body:form});
 const raw=await r.text();let data;try{data=raw?JSON.parse(raw):null}catch{data=raw}
 if(!r.ok){const e=new Error(typeof data==="object"?JSON.stringify(data):String(data));e.status=r.status;e.data=data;throw e}return data;
}
export async function downloadFile(path,{apiKey,workspaceId,method="POST",body}={}){
 const headers={Accept:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"};
 const effectiveApiKey=(apiKey||"").trim();
 if(body!==undefined)headers["Content-Type"]="application/json";
 if(effectiveApiKey)headers["X-API-Key"]=effectiveApiKey;
 headers["X-Workspace-ID"]=(workspaceId||"default").trim()||"default";
 const r=await fetch(BASE+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
 if(!r.ok){const raw=await r.text();let data;try{data=raw?JSON.parse(raw):null}catch{data=raw}const e=new Error(typeof data==="object"?JSON.stringify(data):String(data));e.status=r.status;e.data=data;throw e}
 const cd=r.headers.get("content-disposition")||"";const match=cd.match(/filename="?([^";]+)"?/i);
 return{blob:await r.blob(),filename:match?.[1]||"orbythra-arama-claim.xlsx"};
}
export async function openapi(){const r=await fetch(BASE+"/openapi.json");if(!r.ok)throw new Error("OpenAPI unavailable: "+r.status);return r.json()}
export function operations(schema){
 const out=[];for(const[path,item]of Object.entries(schema.paths||{}))for(const method of ["get","post","put","patch","delete"])if(item[method]){
  const op=item[method];out.push({path,method:method.toUpperCase(),summary:op.summary||op.operationId||path,tags:op.tags||["other"],operationId:op.operationId||"",parameters:[...(item.parameters||[]),...(op.parameters||[])],requestBody:op.requestBody,responses:op.responses||{}});
 }return out.sort((a,b)=>a.path.localeCompare(b.path)||a.method.localeCompare(b.method));
}
export function starterBody(op,schema){const ref=op.requestBody?.content?.["application/json"]?.schema;return ref?JSON.stringify(exampleFor(ref,schema),null,2):""}
function resolve(s,root){if(s?.$ref){const p=s.$ref.replace(/^#\//,"").split("/");return p.reduce((v,k)=>v?.[k],root)||s}return s||{}}
function exampleFor(input,root,depth=0){if(depth>5)return null;const s=resolve(input,root);if(s.example!==undefined)return s.example;if(s.default!==undefined)return s.default;if(s.enum?.length)return s.enum[0];if(s.type==="array")return [exampleFor(s.items||{},root,depth+1)];if(s.type==="object"||s.properties){const o={};for(const[k,v]of Object.entries(s.properties||{})){if((s.required||[]).includes(k)||v.default!==undefined)o[k]=exampleFor(v,root,depth+1)}return o}if(s.type==="boolean")return false;if(s.type==="integer"||s.type==="number")return s.minimum??0;return "";}
