/* 11-govern.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- people / govern ---------- */
const OWN_KEYWORDS={"Customer":["customer"],"Governance":["governance","alert","policy"],"Billing & Rates":["billing","rate","invoice","account number"],"Usage":["usage","consumption"],"Records & Documents":["document","record","file"]};
async function loadPeople(){
  try{ PEOPLE=(await (await fetch('/api/people')).json()).people||[]; }catch(e){ PEOPLE=[]; }
  PEOPLE_LOADED=true; ROSTER_DIRTY=false; updateRosterDirtyUI(); renderRoster(); fillGovSelects(); if(ROWS.length)buildCatTable(); renderStepper();
}
let ROSTER_DIRTY=false;
function markRosterDirty(){ ROSTER_DIRTY=true; updateRosterDirtyUI(); }
function updateRosterDirtyUI(){ const el=$('rosterDirty'); if(el) el.innerHTML=ROSTER_DIRTY?'<span class="dirtydot" title="Unsaved roster changes — click Save roster"></span> <span class="hint" style="color:#C25E00">unsaved</span>':''; }
function renderRoster(){
  const fns=(p,i)=>{
    const f=personFns(p), m=[['businessSteward','Steward'],['owner','Owner'],['custodian','Custodian']];
    return `<div class="rrole">${m.map(([k,l])=>`<button class="fnbtn${f[k]?' on':''}" onclick="toggleFn(${i},'${k}')" title="Toggle the ${l} function for this person — your setting overrides the Keycloak role and persists with Save roster. The Govern pools (defaults prefill, Auto-assign candidates) draw from these.">${l}</button>`).join('')}</div>`;
  };
  const q=(($('rosterFilter')&&$('rosterFilter').value)||'').trim().toLowerCase();
  const match=p=>!q||[p.name,p.display_name,p.email,p.expertise].some(x=>String(x||'').toLowerCase().includes(q));
  const rows=PEOPLE.map((p,i)=>({p,i})).filter(({p})=>match(p));
  $('rosterRows').innerHTML=PEOPLE.length?(rows.length?rows.map(({p,i})=>`<tr><td>${esc(p.name||'')}${fns(p,i)}</td><td>${esc(p.display_name||'')}</td><td>${esc(p.email||'')}</td><td><code>${esc(p.id||'(none)')}</code></td><td><input type="text" class="exp-inp" value="${esc(p.expertise||'')}" placeholder="add expertise…" oninput="setExpertise(${i},this.value)" style="width:100%;min-width:180px;font-size:12px;padding:4px 7px;border:1px solid var(--line);border-radius:6px"/></td><td><button class="danger sm" onclick="rmPerson(${i})">Remove</button></td></tr>`).join(''):`<tr><td colspan="6" class="msg">No matches for &ldquo;${esc(q)}&rdquo;.</td></tr>`):'<tr><td colspan="6" class="msg">No people yet.</td></tr>';
}
function setExpertise(i,v){ if(PEOPLE[i]){ PEOPLE[i].expertise=v; markRosterDirty(); } }
async function suggestExpertise(){
  if(!PEOPLE.length){ $('expMsg').textContent='No people in the roster yet.'; return; }
  const cats=[...new Set(ROWS.map(r=>r.Category).filter(Boolean))];
  const overwrite=$('exp_overwrite')?$('exp_overwrite').checked:false;
  $('expMsg').textContent='Generating expertise from roles, responsibilities'+(cats.length?' and scanned categories':'')+'…';
  try{
    const d=await (await fetch('/api/suggest-expertise',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({people:PEOPLE,categories:cats,overwrite})})).json();
    const by={}; (d.people||[]).forEach(p=>{ if(p.id)by['i:'+p.id]=p; if(p.email)by['e:'+(p.email||'').toLowerCase()]=p; if(p.name)by['n:'+(p.name||'').toLowerCase()]=p; });
    PEOPLE.forEach(p=>{ const m=by['i:'+p.id]||by['e:'+(p.email||'').toLowerCase()]||by['n:'+(p.name||'').toLowerCase()]; if(m&&m.expertise) p.expertise=m.expertise; });
    if(d.updated) markRosterDirty();
    renderRoster(); fillGovSelects();
    const via=d.used_llm?'the LLM':'offline rules ('+( (d.llm&&d.llm.online)?'LLM returned nothing':'Ollama offline')+')';
    $('expMsg').innerHTML='&#9889; Set expertise for <b>'+(d.updated||0)+'</b> people via '+via+'.'
      +(cats.length?'':' <span style="color:#C25E00">Scan a source first for sharper, category-aware keywords.</span>')
      +(d.updated?' Review, then <b>Save roster</b>.':'');
  }catch(e){ $('expMsg').textContent='Suggest failed: '+e; }
}
// validate the add-person row: UUID (if given) must be a UUID; email (if given) valid
function valPerson(){
  const idEl=$('p_id'), emEl=$('p_email');
  const uuidOk=!idEl.value.trim()||/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(idEl.value.trim());
  const emOk=!emEl.value.trim()||/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(emEl.value.trim());
  idEl.closest('.fld').classList.toggle('bad',!uuidOk);
  emEl.closest('.fld').classList.toggle('bad',!emOk);
  const btn=$('addPersonBtn'); if(btn) btn.disabled=!(uuidOk&&emOk);
  return uuidOk&&emOk;
}
// Map a user's Keycloak realm roles to a governance function. PDC's model:
// Business_Steward maintains glossaries; Data_Steward gives governance ownership;
// Data_Storage_Administrator is the technical custodian of the stored data.
function roleFns(roles){
  const R=(roles||[]).map(x=>String(x).toLowerCase());
  const any=(...ks)=>R.some(r=>ks.some(k=>r.includes(k)));
  return {
    businessSteward: any('business_steward','business steward'),
    owner:           any('data_steward','data steward'),
    custodian:       any('data_storage','storage_admin','storage administrator','custodian')
  };
}
// Best roster member for a governance function. Prefer the most specialised
// account (fewest governance functions) so a dedicated Business Steward is chosen
// ahead of an all-roles admin; tie-break by name.
function pickByFn(fn){
  const c=PEOPLE.filter(p=>p.id&&personFns(p)[fn]);
  if(!c.length) return null;
  const gcount=p=>{const f=personFns(p);return (f.businessSteward?1:0)+(f.owner?1:0)+(f.custodian?1:0);};
  return c.slice().sort((a,b)=>gcount(a)-gcount(b)||String(a.display_name||a.name).localeCompare(b.display_name||b.name))[0];
}
function rolesShort(roles){
  const m={businessSteward:'Business Steward',owner:'Owner',custodian:'Custodian'};
  const f=roleFns(roles); return Object.keys(m).filter(k=>f[k]).map(k=>m[k]);
}
// Effective governance functions for a person: the steward's explicit roster
// toggles (p.fns, persisted in people.json) OVERRIDE the Keycloak-derived
// roles — so anyone can be made an Owner/Custodian/Steward without touching
// Keycloak (whose realm roles often mark only the admin account).
function personFns(p){
  const base=roleFns(p&&p.roles), o=(p&&p.fns)||{};
  return {businessSteward:(o.businessSteward!=null?!!o.businessSteward:base.businessSteward),
          owner:(o.owner!=null?!!o.owner:base.owner),
          custodian:(o.custodian!=null?!!o.custodian:base.custodian)};
}
function toggleFn(i,key){
  const p=PEOPLE[i]; if(!p) return;
  p.fns=p.fns||{};
  p.fns[key]=!personFns(p)[key];
  markRosterDirty(); renderRoster(); fillGovSelects();
}
const PDC_DOMAINS=["Human Resources","Marketing","Sales","Finance","Logistics and supply chain Management","Technology","Construction","E-commerce","Engineering","Energy","Utilities","Sustainability","Renewable Energy","Healthcare","LifeSciences","Manufacturing","Semiconductor","Telecommunication","Automotive","Banking","Real estate","Gaming","Cybersecurity","Business","Fitness","Legal","Biology","Services","Transportation","Government sector","Online services"];
function autoDomain(explicit){
  const cats=[...new Set(ROWS.map(r=>(r.Category||'').trim()).filter(Boolean))];
  const terms=ROWS.slice(0,60).map(r=>r.Term).filter(Boolean).slice(0,15);
  return fetch('/api/suggest-domain',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({domains:PDC_DOMAINS,categories:cats,terms:terms,model:currentModel()||null,compute:COMPUTE})})
    .then(r=>r.json()).then(d=>{
      if(d.domain&&$('g_domain')){ $('g_domain').value=d.domain; saveGovDefaults(); }
      if(explicit&&$('govDefMsg')) $('govDefMsg').textContent=d.domain?('\u2713 domain: '+d.domain+' \u2014 '+(d.reason||'')):(d.reason||'no suggestion');
      return !!d.domain;
    }).catch(e=>{ if(explicit&&$('govDefMsg')) $('govDefMsg').textContent='Domain suggestion failed: '+(e.message||e); return false; });
}
function fillGovSelects(){
  const dsel=$('g_domain'); if(dsel && !dsel.options.length){ dsel.innerHTML=PDC_DOMAINS.map(d=>`<option ${d==='Utilities'?'selected':''}>${esc(d)}</option>`).join(''); }
  const b=PEOPLE.filter(p=>p.id);
  const optsFor=slot=>'<option value="">(none)</option>'+b.filter(p=>eligibleFor(p,slot)).map(p=>`<option value="${esc(p.id)}">${esc(p.display_name||p.name)}</option>`).join('');
  $('g_steward').innerHTML=optsFor('businessSteward');
  $('g_owner').innerHTML=optsFor('owner');
  $('g_custodian').innerHTML=optsFor('custodian');
  if(b.length){
    // default each function to a role-matched account, else the first account
    const bs=pickByFn('businessSteward')||b[0], ow=pickByFn('owner')||b[0], cu=pickByFn('custodian')||b[0];
    $('g_steward').value=bs.id; $('g_owner').value=ow.id; $('g_custodian').value=cu.id;
  }
  $('g_stakeholders').innerHTML=b.length?b.map(p=>`<label><input type="checkbox" class="stk" value="${esc(p.id)}" onchange="saveGovDefaults()"> ${esc(p.display_name||p.name)}</label>`).join(''):'<span class="msg">No accounts with a UUID yet.</span>';
  applyGovDefaults();       // saved defaults beat the role-based prefill
  wireGovDefaults();
}

/* ---- stewardship defaults persist to settings.json and restore on start ---- */
let GOV_WIRED=false;
function wireGovDefaults(){
  if(GOV_WIRED) return; GOV_WIRED=true;
  ['g_steward','g_owner','g_custodian','g_status','g_domain','g_rating','g_reviewed','g_applycats'].forEach(id=>{
    const el=$(id); if(el) el.addEventListener('change',()=>saveGovDefaults());
  });
}
function saveGovDefaults(explicit){
  const gd={steward:$('g_steward')?$('g_steward').value:'',owner:$('g_owner')?$('g_owner').value:'',
            custodian:$('g_custodian')?$('g_custodian').value:'',status:$('g_status')?$('g_status').value:'',
            domain:$('g_domain')?$('g_domain').value:'',rating:$('g_rating')?$('g_rating').value:'',
            reviewed:$('g_reviewed')?$('g_reviewed').value:'',applycats:$('g_applycats')?$('g_applycats').checked:true,
            stakeholders:[...document.querySelectorAll('#g_stakeholders .stk:checked')].map(c=>c.value)};
  SETTINGS.gov_defaults=gd;
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gov_defaults:gd})}).catch(()=>{});
  const m=$('govDefMsg'); if(m){ m.textContent=explicit?'\u2713 defaults saved \u2014 they restore on restart and Auto-assign respects them':'\u2713 saved'; if(!explicit) setTimeout(()=>{ if(m.textContent==='\u2713 saved') m.textContent=''; },2500); }
}
function applyGovDefaults(){
  const gd=(typeof SETTINGS!=='undefined'&&SETTINGS.gov_defaults)||null; if(!gd) return;
  const setSel=(id,v)=>{ const el=$(id); if(el&&v!=null&&v!==''&&[...el.options].some(o=>o.value===v)) el.value=v; };
  setSel('g_steward',gd.steward); setSel('g_owner',gd.owner); setSel('g_custodian',gd.custodian);
  setSel('g_status',gd.status); setSel('g_domain',gd.domain); setSel('g_rating',gd.rating);
  if(gd.reviewed&&$('g_reviewed')) $('g_reviewed').value=gd.reviewed;
  if(gd.applycats!=null&&$('g_applycats')) $('g_applycats').checked=!!gd.applycats;
  (gd.stakeholders||[]).forEach(id=>{ const c=document.querySelector('#g_stakeholders .stk[value="'+CSS.escape(id)+'"]'); if(c) c.checked=true; });
  if(gd.rating&&typeof onGlobalRatingChange==='function') onGlobalRatingChange();
  GOV_DEFAULTS_DONE=true;   // saved defaults replace the one-time date/rating seeding
}
function addPerson(){
  if(!valPerson()) return;
  const id=$('p_id').value.trim();
  PEOPLE.push({name:$('p_name').value.trim()||($('p_email').value.split('@')[0]),display_name:$('p_display').value.trim(),email:$('p_email').value.trim(),id,roles:[],stakeholder_role:'Steward',community:'',owns:'',expertise:($('p_expertise')?$('p_expertise').value.trim():'')});
  ['p_name','p_display','p_email','p_id','p_expertise'].forEach(x=>{if($(x))$(x).value='';}); valPerson(); markRosterDirty(); renderRoster(); fillGovSelects();
}
function rmPerson(i){ PEOPLE.splice(i,1); markRosterDirty(); renderRoster(); fillGovSelects(); }
async function saveRoster(){
  const d=await (await fetch('/api/people',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({people:PEOPLE})})).json();
  ROSTER_DIRTY=false; updateRosterDirtyUI();
  $('rosterMsg').innerHTML='Saved <b>'+(d.people||[]).length+'</b> people \u2713';
}
async function fetchKeycloak(){
  $('kMsg').textContent='Fetching from Keycloak…';
  const body={base_url:$('k_base').value,realm:$('k_realm').value,
    auth_realm:($('k_authrealm')&&$('k_authrealm').value.trim())||'master',
    username:$('k_user').value,password:$('k_pass').value,token:$('k_token').value,
    verify_tls:$('k_verify')?$('k_verify').checked:false,save:$('k_save').checked};
  try{ const d=await (await fetch('/api/keycloak-users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(!d.ok){ $('kMsg').textContent='✗ '+d.message; return; }
    // carry over any expertise the user typed in this session but hasn't saved yet
    const prevBy={}; PEOPLE.forEach(p=>{ if(p.expertise){ if(p.id)prevBy['i:'+p.id]=p.expertise; if(p.email)prevBy['e:'+p.email.toLowerCase()]=p.expertise; if(p.name)prevBy['n:'+p.name.toLowerCase()]=p.expertise; } });
    (d.people||[]).forEach(p=>{ if(!p.expertise){ const e=prevBy['i:'+p.id]||prevBy['e:'+(p.email||'').toLowerCase()]||prevBy['n:'+(p.name||'').toLowerCase()]; if(e)p.expertise=e; } });
    PEOPLE=d.people; ROSTER_DIRTY=!d.saved; updateRosterDirtyUI(); renderRoster(); fillGovSelects(); if(ROWS.length)buildCatTable();
    const kept=(d.expertise_preserved||0);
    const blanks=PEOPLE.filter(p=>p.id&&!(p.expertise||'').trim()).length;
    $('kMsg').innerHTML=`✓ Fetched ${d.count} users${d.saved?' (saved to roster)':' — review and Save roster'}${kept?` · kept expertise for ${kept}`:''}.`;
    // optionally have the LLM fill expertise for the freshly-fetched (blank) people
    if(blanks && $('k_genexp') && $('k_genexp').checked){
      $('kMsg').innerHTML+=` Generating expertise for ${blanks}…`;
      await suggestExpertise();   // fills blanks only, then marks the roster unsaved
      $('kMsg').innerHTML=`✓ Fetched ${d.count} users · expertise generated — review and <b>Save roster</b>.`;
    } else if(blanks){
      $('kMsg').innerHTML+=` <b>${blanks}</b> have no expertise yet — tick <b>&#9889; generate expertise (LLM)</b> or run it above so auto-assign can match on more than role.`;
    }
  }catch(e){ $('kMsg').textContent='✗ '+e; }
}
function personById(id){ return PEOPLE.find(p=>p.id===id); }
function personByEmail(em){ em=(em||'').toLowerCase(); return PEOPLE.find(p=>(p.email||'').toLowerCase()===em); }
function prefillFor(cat){
  const hints=ROWS.filter(r=>r.Category===cat&&r.Owner_Hint).map(r=>r.Owner_Hint);
  if(hints.length){ const top=hints.sort((a,b)=>hints.filter(x=>x===b).length-hints.filter(x=>x===a).length)[0]; const p=personByEmail(top)||personById(top); if(p&&p.id)return{id:p.id,src:'minio'}; }
  const kws=OWN_KEYWORDS[cat]||[cat.toLowerCase()];
  for(const p of PEOPLE){ if(!p.id)continue; if(kws.some(k=>(p.owns||'').toLowerCase().includes(k)))return{id:p.id,src:'owns'}; }
  // role-based: a category's terms are maintained by a Business Steward
  const bs=pickByFn('businessSteward'); if(bs)return{id:bs.id,src:'role'};
  return {id:'',src:'def'};
}
var SAVED_CAT_OV={};
// Options for a per-category people <select>: "(use default)" plus every account.
function ccPeopleOpts(b,selId){
  return '<option value="">(use default)</option>'+b.map(p=>`<option value="${esc(p.id)}" ${p.id===selId?'selected':''}>${esc(p.display_name||p.name)}</option>`).join('');
}
function ccName(id){ const p=personById(id); return p?(p.display_name||p.name):''; }
// Build one collapsible card per category. Steward is pre-filled (MinIO tag /
// owns-map / role); every other field starts on "(use default)" and inherits.
function buildCatTable(){
  const cats=[...new Set(ROWS.map(r=>r.Category))], b=PEOPLE.filter(p=>p.id);
  if(!cats.length||!b.length){ $('g_cattbl_wrap').style.display='none'; return; }
  const statusOpts='<option value="">(use default)</option><option>Draft</option><option>Review</option><option>Accepted</option><option>Deprecated</option>';
  const ratingOpts='<option value="">(use default)</option><option value="0">None</option><option value="auto">Auto (DQ)</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option>';
  const shOpts=b.map(p=>`<label><input type="checkbox" class="cc-sh" value="${esc(p.id)}" onchange="ccUpdate(this)"> ${esc(p.display_name||p.name)}</label>`).join('');
  $('g_catcards').innerHTML=cats.map(c=>{
    const pf=prefillFor(c);              // suggested steward for this category
    // each slot's dropdown offers only roster-eligible people (function match,
    // or unscoped) — the same dynamic rule the auto-assign pools follow
    const stewOpts=ccPeopleOpts(b.filter(p=>eligibleFor(p,'businessSteward')),pf.id);
    const ownOpts=ccPeopleOpts(b.filter(p=>eligibleFor(p,'owner')),'');
    const cusOpts=ccPeopleOpts(b.filter(p=>eligibleFor(p,'custodian')),'');
    return `<div class="catcard" data-cat="${esc(c)}">
      <button type="button" class="catcard-h" onclick="toggleCatCard(this)">
        <span class="cc-name">${esc(c)}</span><span class="cc-sum"></span><span class="cc-car">&#9656;</span>
      </button>
      <div class="catcard-b" style="display:none">
        <div class="grid">
          <div class="fld"><label>Business steward</label><select class="cc-field" data-f="businessSteward" onchange="ccUpdate(this)">${stewOpts}</select></div>
          <div class="fld"><label>Owner</label><select class="cc-field" data-f="owner" onchange="ccUpdate(this)">${ownOpts}</select></div>
          <div class="fld"><label>Custodian</label><select class="cc-field" data-f="custodian" onchange="ccUpdate(this)">${cusOpts}</select></div>
          <div class="fld" style="flex:0 0 150px"><label>Status</label><select class="cc-field" data-f="status" onchange="ccUpdate(this)">${statusOpts}</select></div>
          <div class="fld" style="flex:0 0 120px"><label>Rating</label><select class="cc-field" data-f="rating" onchange="ccUpdate(this)">${ratingOpts}</select></div>
          <div class="fld" style="flex:0 0 185px"><label>Reviewed date</label><input class="cc-field" data-f="reviewedAt" type="date" onchange="ccUpdate(this)"/></div>
        </div>
        <div class="fld" style="margin-top:12px">
          <label class="cc-shhead"><input type="checkbox" class="cc-shtoggle" onchange="ccToggleSh(this)"> Override stakeholders for this category</label>
          <div class="stakelist cc-shlist" style="display:none">${shOpts||'<span class="msg">No accounts with a UUID yet.</span>'}</div>
        </div>
      </div></div>`;
  }).join('');
  // re-apply any saved per-category overrides, then paint every summary line
  document.querySelectorAll('#g_catcards .catcard').forEach(card=>{ ccApply(card,SAVED_CAT_OV[card.dataset.cat]); ccUpdate(card); });
  $('g_cattbl_wrap').style.display='';
}
function toggleCatCard(btn){ const card=btn.closest('.catcard'); const open=card.classList.toggle('open'); card.querySelector('.catcard-b').style.display=open?'':'none'; }
function ccToggleSh(cb){ const card=cb.closest('.catcard'); card.querySelector('.cc-shlist').style.display=cb.checked?'':'none'; ccUpdate(cb); }
// Restore a saved override object onto a card's controls.
function ccApply(card,ov){
  if(!ov) return;
  card.querySelectorAll('.cc-field').forEach(f=>{ const k=f.dataset.f;
    if(k==='reviewedAt'){ if(ov.reviewedAt) f.value=ov.reviewedAt; }
    else if(ov[k]!=null&&ov[k]!=='') f.value=(k==='rating'?String(ov[k]):ov[k]); });
  if(ov.stakeholders&&ov.stakeholders.length){ const tog=card.querySelector('.cc-shtoggle'); if(tog){ tog.checked=true; card.querySelector('.cc-shlist').style.display=''; }
    ov.stakeholders.forEach(s=>{ const id=s.id||s; const cb=card.querySelector('.cc-sh[value="'+id+'"]'); if(cb)cb.checked=true; }); }
}
// Recompute the collapsed summary: only fields that differ from the global
// defaults count as overrides, so a category matching the defaults reads clean.
// A user-driven change locks that field so Auto-assign won't overwrite it.
function ccUpdate(el){
  const card=el.closest('.catcard'); if(!card) return;
  if(!AUTO_ASSIGNING && el.classList && (el.classList.contains('cc-field')||el.classList.contains('cc-sh')||el.classList.contains('cc-shtoggle'))){
    el.dataset.src='user'; el.classList.remove('is-auto'); if(el.classList.contains('cc-field')) el.classList.add('is-locked');
  }
  const v=f=>{ const n=card.querySelector('.cc-field[data-f="'+f+'"]'); return n?n.value:''; };
  const bits=[];
  const st=v('businessSteward'); if(st&&st!==($('g_steward').value||'')) bits.push('Steward: '+esc(ccName(st)));
  const ow=v('owner');           if(ow&&ow!==($('g_owner').value||''))   bits.push('Owner: '+esc(ccName(ow)));
  const cu=v('custodian');       if(cu&&cu!==($('g_custodian').value||''))bits.push('Custodian: '+esc(ccName(cu)));
  const sta=v('status');         if(sta&&sta!==($('g_status').value||'')) bits.push(esc(sta));
  const ra=v('rating');
  if(ra==='auto'){ const d=dqForCategory(card.dataset.cat); bits.push(d.n?('\u2605 '+d.stars+' (auto '+d.mean+'%)'):'auto (no DQ)'); }
  else if(ra!==''&&ra!==($('g_rating').value||'')) bits.push(ra==='0'?'No rating':'\u2605 '+ra);
  const rv=v('reviewedAt');      if(rv&&rv!==($('g_reviewed').value||''))  bits.push('Reviewed '+esc(rv));
  const tog=card.querySelector('.cc-shtoggle');
  if(tog&&tog.checked){ const n=card.querySelectorAll('.cc-sh:checked').length; bits.push(n+' stakeholder'+(n===1?'':'s')); }
  const autoTag=card.querySelector('.cc-auto')?'<span class="autosum">&#9889; auto</span>':'';
  card.querySelector('.cc-sum').innerHTML=(bits.length?'<span class="ov">Overrides:</span> '+bits.join(' &middot; '):'Using defaults')+autoTag;
}
/* ---------- auto-assign (keyword) + auto-rating (scan DQ) ---------- */
let AUTO_ASSIGNING=false;
// tokenizer: lower-case, split on separators, drop short/stop words
const STOP=new Set(['the','and','of','for','a','an','to','in','on','with','by','is','are','term','terms','data','id','code','number','name','date','type','value','flag','status','tbl','col']);
function tok(s){ return String(s||'').toLowerCase().replace(/[_./\-]+/g,' ').replace(/[^a-z0-9 ]+/g,' ').split(/\s+/).filter(w=>w&&w.length>2&&!STOP.has(w)); }
// small domain synonym map: bridges a person's words to a category's words even
// when they don't share an exact token (synonyms / related terms)
const DOMAIN_SYNONYMS={
  'billing':['billing','bill','rate','rates','invoice','invoicing','charge','charges','tariff','payment','finance','financial','revenue','balance','dollar','cost','amount'],
  'customer':['customer','account','consumer','client','household','subscriber','contact','address','resident'],
  'usage':['usage','consumption','meter','metering','volume','gallons','demand','flow'],
  'governance':['governance','policy','compliance','alert','audit','steward','regulatory','standard','rule','approval','review','escalation'],
  'records':['document','record','file','report','archive','attachment','scan','pdf']
};
function bucketsOf(tokenSet){ const b=new Set(); for(const [name,words] of Object.entries(DOMAIN_SYNONYMS)){ if(words.some(w=>tokenSet.has(w))) b.add(name); } return b; }
// the vocabulary a category represents, split into:
//   core = the category label + its curated owns-keywords (the canonical domain)
//   ext  = incidental tokens from term names and physical column leaves
// core counts for more so a domain label outweighs a column-name collision
// (e.g. a Billing owner whose notes mention "Customer Account Number").
function catVocab(cat){
  const rows=ROWS.filter(r=>r.Category===cat);
  const core=new Set([...tok(cat), ...(OWN_KEYWORDS[cat]||[]).flatMap(tok)]);
  const ext=new Set();
  rows.forEach(r=>{ tok(r.Term).forEach(t=>ext.add(t));
    String(r.Source_Column||'').split(';').forEach(sc=>{ tok(sc.trim().split('.').pop()).forEach(t=>ext.add(t)); }); });
  core.forEach(t=>ext.delete(t));
  return {core, ext, buckets:bucketsOf(new Set([...core,...ext]))};
}
function personVocab(p){ const exp=new Set(tok(p.expertise)); const own=new Set(tok(p.owns)); return {exp, own, buckets:bucketsOf(new Set([...exp,...own]))}; }
function gcountP(p){ const f=roleFns(p.roles); return (f.businessSteward?1:0)+(f.owner?1:0)+(f.custodian?1:0); }
// keyword score: expertise dominates owns, and the category label (core) dominates
// incidental term/column tokens (ext); a shared domain bucket bridges synonyms.
function scorePC(pv,cv){
  const hits=(a,b)=>{ const h=[]; a.forEach(t=>{ if(b.has(t)) h.push(t); }); return h; };
  const ec=hits(pv.exp,cv.core), ee=hits(pv.exp,cv.ext), oc=hits(pv.own,cv.core), oe=hits(pv.own,cv.ext);
  const bHits=[...pv.buckets].filter(b=>cv.buckets.has(b));
  const score=3*ec.length + 1*ee.length + 2*oc.length + 0.5*oe.length + 3*bHits.length;
  const matched=[...new Set([...ec,...bHits,...ee,...oc,...oe])].slice(0,6);
  return {score, matched, bHits:bHits.length};
}
function confOf(s){ return s>=6?'high':s>=3?'med':s>0?'low':'none'; }
function candidatesFor(slot){ return PEOPLE.filter(p=>p.id&&personFns(p)[slot]); }
// choose the best person for one slot in one category
// Dynamic roster rule: a person's functions are EXCLUSIVE capabilities when
// present — someone marked (or role-derived) only as Custodian must never be
// swept into Steward/Owner slots, even by the expertise-only fallback. People
// with NO functions at all remain fair game for any slot in fallback mode.
function eligibleFor(p,slot){
  const f=personFns(p);
  const scoped=f.businessSteward||f.owner||f.custodian;
  return !scoped || f[slot];
}
function pickSlot(cat,cv,slot,fallbackOn){
  let pool=candidatesFor(slot), fallback=false;
  if(!pool.length&&fallbackOn){ pool=PEOPLE.filter(p=>p.id&&eligibleFor(p,slot)); fallback=true; }
  if(!pool.length) return {id:'',name:'',conf:'none',reason:'no '+slot+' candidate in roster',fallback:false};
  const scored=pool.map(p=>({p,...scorePC(personVocab(p),cv)}));
  scored.sort((a,b)=> b.score-a.score
     || ((b.p.expertise?1:0)-(a.p.expertise?1:0))
     || (gcountP(a.p)-gcountP(b.p))
     || String(a.p.display_name||a.p.name).localeCompare(b.p.display_name||b.p.name));
  const top=scored[0];
  if(top.score===0){
    const def=pickByFn(slot);
    if(def) return {id:def.id,name:def.display_name||def.name,conf:'low',score:0,reason:fallback?'no role/expertise match — role default':'role default (no expertise match)',fallback};
    return {id:'',name:'',conf:'none',score:0,reason:'no match',fallback};
  }
  return {id:top.p.id,name:top.p.display_name||top.p.name,conf:confOf(top.score),score:top.score,reason:(fallback?'expertise-only: ':'')+'matched '+top.matched.join(', '),fallback};
}

// One slot's decision when the steward set a DEFAULT: expertise routing still
// runs, but a candidate must STRICTLY BEAT the default person's own expertise
// score for this category to override — otherwise the default holds. Pure
// (no DOM) so it is unit-testable.
function slotDecision(cat,cv,slot,fb,defId){
  const pk=pickSlot(cat,cv,slot,fb);
  if(!defId) return {mode:'assign',pk};
  const defP=personById(defId);
  const defScore=defP?scorePC(personVocab(defP),cv).score:0;
  if(pk.id && pk.id!==defId && (pk.score||0)>0 && (pk.score||0)>defScore){
    return {mode:'override',pk:Object.assign({},pk,{reason:pk.reason+' — beats your default '+ccName(defId)+' ('+(pk.score||0).toFixed(1)+' vs '+defScore.toFixed(1)+')'}),defScore};
  }
  const why = (pk.id===defId && (pk.score||0)>0) ? ('your default is also the best expertise match — '+(pk.reason||''))
            : (pk.id && (pk.score||0)>0) ? ('default holds — '+pk.name+' matched but not better ('+(pk.score||0).toFixed(1)+' vs '+defScore.toFixed(1)+')')
            : ('left on your default — '+ccName(defId));
  return {mode:'default',pk:{id:'',name:'',conf:'default',reason:why},defScore};
}
function renderAutoCard(card,picks){
  const body=card.querySelector('.catcard-b'); if(!body) return;
  let box=card.querySelector('.cc-auto'); if(!box){ box=document.createElement('div'); box.className='cc-auto'; body.appendChild(box); }
  const lbl={businessSteward:'Business steward',owner:'Owner',custodian:'Custodian'};
  box.innerHTML='<div style="font-weight:600;margin-bottom:5px">&#9889; Auto-assign rationale</div>'+
    ['businessSteward','owner','custodian'].map(s=>{ const pk=picks[s]||{}; const conf=pk.conf||'none';
      const who=pk.id?esc(pk.name):'<i>&mdash; left on default</i>';
      const lock=pk.locked?' <span class="conf low">your pick</span>':'';
      return '<div class="row"><span class="slot">'+lbl[s]+'</span><span>'+who+lock+' <span class="conf '+conf+'">'+conf+'</span></span> <span class="why">'+esc(pk.reason||'')+'</span></div>';
    }).join('');
}
// One-click macro: fill any missing expertise (LLM/offline), then auto-assign all
// slots. Rating (Auto DQ) and reviewed date are already defaulted. Manual picks kept.
async function setupStewardship(){
  if(!ROWS.length){ $('autoMsg').textContent='Scan a source first — stewardship reads each category\u2019s columns.'; return; }
  if(!PEOPLE.filter(p=>p.id).length){ $('autoMsg').textContent='Add at least one account with a UUID first.'; return; }
  const blanks=PEOPLE.filter(p=>p.id&&!(p.expertise||'').trim()).length;
  if(blanks){ $('autoMsg').textContent='Generating expertise for '+blanks+' people…'; await suggestExpertise(); }
  // classify the DOMAIN from the company's own data unless the steward saved one
  if(!(SETTINGS.gov_defaults&&SETTINGS.gov_defaults.domain)) await autoDomain(false);
  autoAssign();
}
function autoAssign(){
  if(!ROWS.length){ $('autoMsg').textContent='Scan a source first — auto-assign reads each category\u2019s columns.'; return; }
  if(!PEOPLE.filter(p=>p.id).length){ $('autoMsg').textContent='Add at least one account with a UUID first.'; return; }
  const fb=$('auto_fallback')?$('auto_fallback').checked:true;
  const respect=$('auto_respect')?$('auto_respect').checked:true;
  // explicit defaults are the steward's word — with "respect defaults" on, a slot
  // that has one stays on (use default) everywhere instead of being overridden
  const defs={businessSteward:$('g_steward').value||'',owner:$('g_owner').value||'',custodian:$('g_custodian').value||''};
  AUTO_ASSIGNING=true; let filled=0, cards=0, locked=0, defaulted=0;
  document.querySelectorAll('#g_catcards .catcard').forEach(card=>{
    cards++; const cat=card.dataset.cat, cv=catVocab(cat), picks={};
    ['businessSteward','owner','custodian'].forEach(slot=>{
      const field=card.querySelector('.cc-field[data-f="'+slot+'"]');
      if(field&&field.dataset.src==='user'){ picks[slot]={conf:'low',reason:'kept your manual pick',locked:true,id:field.value,name:ccName(field.value)}; locked++; return; }
      const dec=slotDecision(cat,cv,slot,fb,respect?defs[slot]:'');
      picks[slot]=dec.pk;
      if(dec.mode==='default'){
        if(field){ if(field.tagName==='SELECT') field.value=''; field.dataset.src=''; field.classList.remove('is-auto'); }
        defaulted++; return;
      }
      if(field&&dec.pk.id){ field.value=dec.pk.id; field.dataset.src='auto'; field.classList.add('is-auto'); field.classList.remove('is-locked'); filled++; }
    });
    renderAutoCard(card,picks);
  });
  AUTO_ASSIGNING=false;
  document.querySelectorAll('#g_catcards .catcard').forEach(c=>ccUpdate(c));
  $('autoMsg').innerHTML='&#9889; Filled <b>'+filled+'</b> slot(s) across <b>'+cards+'</b> categories'+(defaulted?(', left <b>'+defaulted+'</b> on your defaults'):'')+(locked?(', kept <b>'+locked+'</b> manual pick(s)'):'')+'. Expand a category to see why each person was chosen.';
}
function clearAuto(){
  AUTO_ASSIGNING=true;
  document.querySelectorAll('#g_catcards .catcard').forEach(card=>{
    card.querySelectorAll('.cc-field').forEach(f=>{ if(f.dataset.src==='auto'){ if(f.tagName==='SELECT') f.value=''; f.dataset.src=''; f.classList.remove('is-auto'); } });
    const box=card.querySelector('.cc-auto'); if(box) box.remove();
  });
  AUTO_ASSIGNING=false;
  document.querySelectorAll('#g_catcards .catcard').forEach(c=>ccUpdate(c));
  $('autoMsg').textContent='Cleared auto-filled picks. Manual edits and locks were kept.';
}
// --- auto-rating from scan Data Quality ---
function _dqScoreOfDims(d){ // mirror server quality_score_column (default weights)
  const W={c:0.4,u:0.3,v:0.3}, dims=[];
  let comp=(d.c==null&&d.nn)?1.0:d.c;
  if(comp!=null) dims.push([W.c,Math.max(0,Math.min(1,comp))]);
  if(d.eu&&d.u!=null) dims.push([W.u,Math.max(0,Math.min(1,d.u))]);
  if(d.v!=null) dims.push([W.v,Math.max(0,Math.min(1,d.v))]);
  const ws=dims.reduce((s,x)=>s+x[0],0); if(ws<=0) return null;
  return Math.round(100*dims.reduce((s,x)=>s+x[0]*x[1],0)/ws);
}
function _rowDQ(r){
  if(typeof r.Suggested_Quality==='number') return r.Suggested_Quality;
  const dims=r.Source_Quality_Dims||{}, vals=Object.values(dims).map(_dqScoreOfDims).filter(x=>x!=null);
  return vals.length?Math.round(vals.reduce((a,b)=>a+b,0)/vals.length):null;
}
function starsFromDQ(p){ return p>=97?5:p>=90?4:p>=80?3:p>=70?2:1; }
function _meanStars(vals){ const v=vals.filter(x=>x!=null); if(!v.length) return {mean:0,n:0,stars:0}; const m=Math.round(v.reduce((a,b)=>a+b,0)/v.length); return {mean:m,n:v.length,stars:starsFromDQ(m)}; }
function dqForCategory(cat){ return _meanStars(ROWS.filter(r=>r.Category===cat).map(_rowDQ)); }
function dqForAll(){ return _meanStars(ROWS.map(_rowDQ)); }
function globalRatingInt(){ const v=$('g_rating')?$('g_rating').value:'0'; return v==='auto'?0:(parseInt(v||'0',10)||0); }
// default reviewed date = today + N months, as yyyy-mm-dd for <input type=date>
function plusMonthsISO(n){ const d=new Date(); d.setMonth(d.getMonth()+n);
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
let GOV_DEFAULTS_DONE=false;
// One-time sensible defaults for the stewardship block: rating on Auto (DQ) and a
// reviewed date 3 months out. Skipped once the user (or a loaded glossary) has set them.
function initGovDefaults(){
  if(GOV_DEFAULTS_DONE) return; GOV_DEFAULTS_DONE=true;
  const rv=$('g_reviewed'); if(rv && !rv.value) rv.value=plusMonthsISO(3);
  const rt=$('g_rating'); if(rt && !rt.value) rt.value='auto';
  onGlobalRatingChange();
}
function onGlobalRatingChange(){
  const hint=$('g_rating_hint'), v=$('g_rating').value;
  if(v==='auto'){ const d=dqForAll(); hint.innerHTML=d.n?('&#8776; '+d.stars+'&#9733; from '+d.mean+'% mean DQ &middot; each category rated on its own DQ'):'scan a source to compute DQ'; }
  else hint.textContent='';
  document.querySelectorAll('#g_catcards .catcard').forEach(c=>ccUpdate(c));
}
function buildGovernance(){
  if(!PEOPLE_LOADED) return null;
  const sel=id=>$(id).value||''; const mk=id=>{const p=personById(id);return p?{id:p.id,name:p.name,email:p.email,roles:['Steward']}:null;};
  const stakeholders=[...document.querySelectorAll('#g_stakeholders .stk:checked')].map(c=>mk(c.value)).filter(Boolean);
  const def={owner:sel('g_owner'),custodian:sel('g_custodian'),businessSteward:sel('g_steward'),stakeholders};
  const gRatingRaw=$('g_rating').value, gAuto=gRatingRaw==='auto';
  const gRating=gAuto?dqForAll().stars:(parseInt(gRatingRaw||'0',10)||0);
  // each category contributes only the fields the user actually set; "Auto" ratings
  // (per-category, or inherited when the global rating is Auto) resolve to a
  // concrete 1-5 here from that category's mean scan DQ, so the server keeps
  // receiving plain integers and the Trust-Score rollup is unchanged.
  const categories={};
  document.querySelectorAll('#g_catcards .catcard').forEach(card=>{
    const cat=card.dataset.cat, ov={};
    card.querySelectorAll('.cc-field').forEach(f=>{ const k=f.dataset.f, val=f.value;
      if(k==='reviewedAt'){ if(val) ov.reviewedAt=val; }
      else if(k==='rating'){
        if(val==='auto'){ const d=dqForCategory(cat); if(d.n) ov.rating=String(d.stars); }
        else if(val!=='') ov.rating=val;
        else if(gAuto){ const d=dqForCategory(cat); if(d.n) ov.rating=String(d.stars); }
      }
      else if(val!=='') ov[k]=val; });
    const tog=card.querySelector('.cc-shtoggle');
    if(tog&&tog.checked){ const sh=[...card.querySelectorAll('.cc-sh:checked')].map(c=>mk(c.value)).filter(Boolean); if(sh.length) ov.stakeholders=sh; }
    if(Object.keys(ov).length) categories[cat]=ov;
  });
  return {status:$('g_status').value,domain:($('g_domain')?$('g_domain').value:'')||'',rating:gRating,ratingMode:gAuto?'auto':'fixed',reviewedAt:$('g_reviewed').value||'',applyToCategories:$('g_applycats').checked,createdBy:sel('g_steward')||sel('g_owner')||'',default:def,categories};
}
