const $=id=>document.getElementById(id);
const form=$('engineeringForm');
const apiKey=$('apiKey');
apiKey.value=localStorage.getItem('orbythra_api_key')||'';
form.addEventListener('submit',async e=>{
  e.preventDefault();
  const key=apiKey.value.trim();
  if(key)localStorage.setItem('orbythra_api_key',key);
  $('status').textContent='analiz ediliyor';
  $('answer').textContent='ORBYTHRA Engineering Intelligence çalışıyor…';
  $('audit').innerHTML='';
  const list=id=>$(id).value.split(',').map(x=>x.trim()).filter(Boolean);
  const body={problem:$('problem').value,target:$('target').value||null,budget:$('budget').value||null,quantity:$('quantity').value||null,operating_conditions:$('conditions').value||null,lifetime:$('lifetime').value||null,standards:list('standards'),manufacturing_capability:$('manufacturing').value||null,constraints:list('constraints'),language:'tr'};
  try{
    const headers={'Content-Type':'application/json'};
    if(key)headers['X-API-Key']=key;
    const r=await fetch('/engineering/analyze',{method:'POST',headers,body:JSON.stringify(body)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||`HTTP ${r.status}`);
    $('answer').textContent=data.answer;
    for(const [name,ok] of Object.entries(data.audit||{})){
      const badge=document.createElement('span'); badge.textContent=name; badge.className=ok?'ok':'bad'; $('audit').appendChild(badge);
    }
    $('status').textContent=`${data.provider} / ${data.model}`;
  }catch(err){$('answer').textContent=`Hata: ${err.message}`;$('status').textContent='başarısız';}
});
