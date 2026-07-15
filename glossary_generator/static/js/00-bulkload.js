/* 00-bulkload.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
    let BL_CANDS=[], BL_SEL=new Set(), _blRemapT;
    function blImpRemapVal(){ return ($('blImpRemap')?$('blImpRemap').value:'').trim(); }
    async function blImpPreview(preserveSel){
      const csv=(document.getElementById('bl_csv')||{}).value||'', msg=$('blMsg');
      const prev = preserveSel ? new Set(BL_SEL) : null;
      const d=await (await fetch('/api/connections/import-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv,preview:true,remap:blImpRemapVal()})})).json();
      if(d.error){ if(msg) msg.textContent=d.error; return null; }
      BL_CANDS=d.candidates||[];
      BL_SEL = prev || new Set(BL_CANDS.filter(c=>c.ok).map(c=>c.name));
      blImpRender();
      return d;
    }
    async function blImportApp(){
      const csv=(document.getElementById('bl_csv')||{}).value||'', msg=document.getElementById('blMsg');
      if(!csv.trim()){ if(msg) msg.textContent='Paste or choose a CSV first (the same one you bulk-load).'; return; }
      if(msg) msg.textContent='Reading the CSV…';
      try{
        if($('blImpAll'))$('blImpAll').checked=true; if($('blImpSearch'))$('blImpSearch').value='';
        $('blImportPanel').style.display='';
        const d=await blImpPreview(false);
        if(d && msg) msg.textContent=`${d.count} connection(s) — set a reachability remap if the app runs outside Docker, tick which to import.`;
      }catch(e){ if(msg) msg.textContent='Import failed: '+(e.message||e); }
    }
    function blImpApplyRemap(){ clearTimeout(_blRemapT); _blRemapT=setTimeout(()=>blImpPreview(true),250); }
    function blImpRender(){
      const q=($('blImpSearch')?$('blImpSearch').value:'').toLowerCase().trim();
      const list=BL_CANDS.filter(c=>!q||(`${c.name} ${c.type||''} ${c.summary||''}`.toLowerCase().includes(q)));
      const el=$('blImpList'); if(!el) return;
      el.innerHTML=list.map(c=>{ const on=BL_SEL.has(c.name), ek=encodeURIComponent(c.name);
        return `<label style="display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid #eef3f5;font-size:12.5px;${c.ok?'cursor:pointer':'opacity:.6'}">
          <input type="checkbox" ${on?'checked':''} ${c.ok?'':'disabled'} onchange="blImpPick('${ek}',this.checked)"/>
          <span style="flex:1;word-break:break-word"><b>${esc(c.name)}</b>${c.type?` <span style="color:var(--mute);font-size:11px">${esc(c.type)}</span>`:''}</span>
          <span style="color:var(--mute);font-size:11px;word-break:break-all;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(c.summary||c.reason||'')}">${esc(c.ok?(c.summary||''):('skip — '+(c.reason||'')))}</span>
        </label>`; }).join('')||'<p class="msg" style="padding:8px">No matches.</p>';
      blImpSelCount();
    }
    function blImpPick(ek,on){ const n=decodeURIComponent(ek); if(on)BL_SEL.add(n); else BL_SEL.delete(n); blImpSelCount(); }
    function blImpToggleAll(on){ const q=($('blImpSearch')?$('blImpSearch').value:'').toLowerCase().trim();
      BL_CANDS.filter(c=>c.ok&&(!q||(`${c.name} ${c.type||''} ${c.summary||''}`.toLowerCase().includes(q)))).forEach(c=>{ if(on)BL_SEL.add(c.name); else BL_SEL.delete(c.name); });
      blImpRender(); }
    function blImpSelCount(){ if($('blImpSel'))$('blImpSel').textContent=BL_SEL.size?`${BL_SEL.size} selected`:'none selected'; }
    async function blImportSelected(){
      const only=[...BL_SEL], msg=document.getElementById('blMsg');
      if(!only.length){ if(msg) msg.textContent='Tick at least one connection to import.'; return; }
      const csv=(document.getElementById('bl_csv')||{}).value||'';
      try{
        const d=await (await fetch('/api/connections/import-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv,only,remap:blImpRemapVal()})})).json();
        if(d.error){ if(msg) msg.textContent=d.error; return; }
        if(typeof CONNS!=='undefined'){ CONNS=d.connections; if(typeof renderConns==='function') renderConns(); }
        $('blImportPanel').style.display='none';
        if(msg) msg.innerHTML=`Added <b>${d.added}</b>, updated <b>${d.updated}</b> app connection(s). Now on the <a href="#" onclick="showPage('schema');return false">Schema</a> and <a href="#" onclick="showPage('files');return false">Files</a> pages (and live-scan).`;
      }catch(e){ if(msg) msg.textContent='Import failed: '+(e.message||e); }
    }
    function blLoadFile(ev){ const f=ev.target.files&&ev.target.files[0]; if(!f) return;
      const r=new FileReader(); r.onload=()=>{ document.getElementById('bl_csv').value=r.result; }; r.readAsText(f); }
    async function blInspect(){
      const b={ base_url:document.getElementById('bl_base').value.trim(), username:document.getElementById('bl_user').value,
                password:document.getElementById('bl_pass').value, token:document.getElementById('bl_token').value.trim(),
                version:(document.getElementById('bl_ver').value||'v2').trim(), realm:'pdc',
                verify_tls:document.getElementById('bl_verify').checked,
                resource_name:document.getElementById('bl_inspect').value.trim() };
      const out=document.getElementById('blInspectOut'); out.style.display=''; out.textContent='Reading PDC…';
      try{
        const d=await (await fetch('/api/pdc/source-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
        out.textContent = d.error ? d.error : (d.count? JSON.stringify(d.sources,null,2) : 'No matching source — check the name (or leave blank to list all).');
      }catch(e){ out.textContent='Failed: '+(e.message||e); }
    }
    function blCell(v){ const c={OK:'#16a34a',FAIL:'#dc2626',SKIP:'#9ca3af',DRY:'#6366f1',EXISTS:'#1C7293',RECREATED:'#2EC4B6',SENT:'#7a4a00'}[v]||'#6b7280';
      return '<td style="padding:4px 6px;color:'+c+';font-weight:600">'+(v||'')+'</td>'; }
    function blRowHtml(r){ return '<td style="padding:4px 6px;word-break:break-word">'+(r.resourceName||'')+'</td>'+
      blCell(r.create)+blCell(r.ingest)+blCell(r.job)+
      '<td style="padding:4px 6px;color:#6b7280;word-break:break-word;white-space:normal">'+((r.note||r.error)?String(r.note||r.error).replace(/</g,'&lt;'):'')+'</td>'; }
    async function blExport(){
      const msg=document.getElementById('blMsg');
      const btn=document.getElementById('blExportBtn'); btn.disabled=true; msg.textContent='Exporting your saved connections…';
      try{
        const resp=await fetch('/api/connections/export.csv');
        if(!resp.ok){ const e=await resp.json().catch(()=>({})); throw new Error(e.error||('HTTP '+resp.status)); }
        const csv=await resp.text();
        const rows=csv.split(/\r?\n/).filter(l=>l.trim()).length-1;
        document.getElementById('bl_csv').value=csv;
        const blob=new Blob([csv],{type:'text/csv'}); const a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='connections.csv'; document.body.appendChild(a); a.click(); a.remove();
        msg.textContent = rows>0
          ? ('Exported '+rows+' saved connection'+(rows===1?'':'s')+' — CSV filled below and downloaded (includes credentials). Review, then Create & ingest.')
          : 'No saved connections to export yet — build one in the New connection panel first.';
      }catch(e){ msg.textContent='Export failed: '+(e.message||e); }
      finally{ btn.disabled=false; }
    }
    async function blRun(dry){
      const msg=document.getElementById('blMsg'), tbl=document.getElementById('blTable'), tb=document.getElementById('blRows');
      const csv=document.getElementById('bl_csv').value.trim();
      const base=document.getElementById('bl_base').value.trim();
      if(!base){ msg.textContent='PDC base URL is required.'; return; }
      if(!csv){ msg.textContent='Paste or choose a CSV first.'; return; }
      const payload={ base_url:base, version:document.getElementById('bl_ver').value.trim()||'v2',
        verify_tls:document.getElementById('bl_verify').checked,
        username:document.getElementById('bl_user').value, password:document.getElementById('bl_pass').value,
        token:document.getElementById('bl_token').value.trim(), csv:csv, dry_run:!!dry,
        options:{ ingest:document.getElementById('bl_ingest').checked, wait:true, replace_existing:document.getElementById('bl_replace').checked, internal_scan:document.getElementById('bl_internal').checked } };
      tb.innerHTML=''; tbl.style.display='none'; msg.textContent = dry?'Building payloads…':'Loading… creating, testing and ingesting each source.';
      document.getElementById('blRunBtn').disabled=true; document.getElementById('blDryBtn').disabled=true;
      const idx={};
      try{
        const resp=await fetch('/api/pdc/bulk-load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(!resp.ok && !resp.body){ const e=await resp.json().catch(()=>({})); throw new Error(e.error||('HTTP '+resp.status)); }
        const reader=resp.body.getReader(), dec=new TextDecoder(); let buf='';
        while(true){ const {value,done}=await reader.read(); if(done) break; buf+=dec.decode(value,{stream:true});
          let nl; while((nl=buf.indexOf('\n'))>=0){ const line=buf.slice(0,nl).trim(); buf=buf.slice(nl+1); if(!line) continue;
            let ev; try{ ev=JSON.parse(line); }catch(_){ continue; }
            if(ev.event==='start'){ tbl.style.display=''; msg.textContent=(ev.dry_run?'Dry run — ':'')+'Processing '+ev.total+' source(s)…'; }
            else if(ev.event==='row_start'){ const tr=document.createElement('tr'); tr.id='blr'+ev.index; idx[ev.index]=tr;
              tr.innerHTML='<td style="padding:4px 6px;word-break:break-word">'+(ev.resourceName||'')+'</td><td colspan="4" style="padding:4px 6px;color:#6b7280">working…</td>'; tb.appendChild(tr); }
            else if(ev.event==='row'){ let tr=idx[ev.index]; if(!tr){ tr=document.createElement('tr'); tb.appendChild(tr);} tr.innerHTML=blRowHtml(ev.result); }
            else if(ev.event==='error'){ msg.textContent='Error: '+ev.message; }
            else if(ev.event==='done'){ msg.textContent = ev.dry_run? ('Dry run complete — '+ev.total+' payload(s) built, nothing sent.')
              : ('Done — '+(ev.ok||0)+' ok, '+(ev.failed||0)+' failed of '+ev.total+'.'); }
          } }
      }catch(e){ msg.textContent='Error: '+(e.message||e); }
      finally{ document.getElementById('blRunBtn').disabled=false; document.getElementById('blDryBtn').disabled=false; }
    }
