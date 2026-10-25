'use strict';

// Public player aids. They never roll, spend resources, or advance initiative.
(() => {
  const mounts = new WeakMap();
  const turnMounts = new WeakMap();
  const effectMounts = new WeakMap();
  const samples = [];
  const arr = value => Array.isArray(value) ? value : [];
  const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  function node(tag, cls, value) {
    const n = document.createElement(tag); if (cls) n.className=cls;
    if (value !== undefined) n.textContent=String(value); return n;
  }
  function button(label, action, cls='outline-button') {
    const b=node('button',cls,label); b.type='button'; b.addEventListener('click',action); return b;
  }
  function current(state) { return state.combat?.active ? arr(state.combat.participants)[state.combat.turn_index] || null : null; }
  function actorFor(state,draft,speakerId) {
    const prefix=String(draft || '').match(/^([^:\n]{1,80}):\s*/)?.[1]?.trim();
    if (prefix) return arr(state.party).find(c=>norm(c.name)===norm(prefix)) || null;
    return arr(state.party).find(c=>c.id===speakerId) || null;
  }
  function advice({state,draft='',speakerId}) {
    const issues=[], turn=current(state), actor=actorFor(state,draft,speakerId);
    if (!turn || !actor || !draft.trim()) return issues;
    if (actor.id!==turn.id) issues.push({kind:'turn',text:'Stai scrivendo per '+actor.name+', mentre il turno è di '+turn.name+'. Domande, dialoghi e reazioni restano possibili; un attacco normale attende il proprio turno.'});
    const intent=norm(draft.replace(/^[^:\n]{1,80}:\s*/,''));
    const usage=state.flags?.combat_context?.turn_usage;
    const actionIntent=/^(attacco|colpisco|spingo|afferro|tento di afferrare|provo a liberarmi|tento di liberarmi|schivo|mi disimpegno)\b/.test(intent);
    if (actor.id===turn.id && usage?.actor_id===actor.id && usage.action_used===true && actionIntent)
      issues.push({kind:'action',text:'L’azione di '+actor.name+' risulta già usata. Il DM verifica se una capacità consente ancora questa mossa.'});
    if (actor.hp===0) issues.push({kind:'condition',text:actor.name+' è a 0 PF: le possibilità dipendono da coscienza, stabilità e condizioni.'});
    const names=arr(actor.conditions).map(norm);
    if (names.includes('afferrato') && /^(mi sposto|mi muovo|avanzo|corro|fuggo)/.test(intent)) issues.push({kind:'movement',text:'Afferrato porta la velocità a zero finché la presa continua.'});
    const spellSlot=arr(actor.resources).filter(r=>/^spell_slot_|^pact_slot_/.test(r.id || ''));
    const spellNames=[...arr(actor.spells?.known),...arr(actor.spells?.prepared)].map(norm);
    if (/^(lancio|uso)\b/.test(intent) && spellNames.some(name=>intent.includes(name)) && spellSlot.length && spellSlot.every(r=>r.current===0))
      issues.push({kind:'resource',text:'Gli slot annotati sono esauriti. Il DM verifica eventuali rituali o altre fonti della magia.'});
    const weapon=arr(actor.attacks).find(a=>intent.includes(norm(a.name).split('·')[0].trim()));
    if (weapon && /giavellotto|dardo|freccia|quadrello/.test(norm(weapon.name))) {
      const stem=norm(weapon.name).split('·')[0].trim();
      const inventory=arr(actor.inventory).filter(item=>norm(item.name).includes(stem));
      if (inventory.length && inventory.every(item=>Number(item.qty)<=0)) issues.push({kind:'ammo',text:'Nell’inventario non risultano esemplari disponibili di '+stem+'.'});
    }
    return issues;
  }
  function renderTurn({host,state,following,onFollow}) {
    if (!host) return;
    const turn=current(state); host.hidden=!turn;
    if (!turn) return;
    let record=turnMounts.get(host);
    if(!record){
      const row=node('div','turn-helper-row'),label=node('label','turn-follow');
      const input=document.createElement('input');input.type='checkbox';input.id='follow-current-turn';
      const caption=node('span','turn-follow-caption');
      record={input,caption,onFollow};turnMounts.set(host,record);
      input.addEventListener('change',()=>record.onFollow?.(input.checked));
      label.append(input,node('span','','Segui il personaggio di turno'));row.append(label,caption);host.replaceChildren(row);
    }
    record.onFollow=onFollow;record.input.checked=Boolean(following);
    const isParty=arr(state.party).some(c=>c.id===turn.id);
    record.caption.textContent=following&&isParty?'Scheda e proposte seguono '+turn.name+'.':following?'Turno di '+turn.name+'. Potete consultare le schede del gruppo.':'Puoi consultare qualsiasi scheda. Tocca a '+turn.name+'.';
  }
  function renderAdvice({host,...options}) {
    if (!host) return;
    const issues=advice(options); host.hidden=!issues.length;
    host.replaceChildren(...issues.map(issue=>node('p','turn-advice-line',issue.text)));
  }
  function renderEffects({host,state,onIntent}) {
    if (!host) return;
    const effects=arr(state.flags?.effects).filter(e=>e && e.visible!==false);
    const concentrations=arr(state.party).filter(c=>c.concentration || c.concentrating);
    let record=effectMounts.get(host);
    if(!record){
      const details=node('details','table-effects'),summary=node('summary'),body=node('div','table-effects-body');
      details.open=effects.length>0||concentrations.length>0;details.append(summary,body);host.replaceChildren(details);
      record={details,summary,body};effectMounts.set(host,record);
    }
    const signature=JSON.stringify([effects,concentrations,state.combat?.round,state.combat?.participants?.map(p=>[p.id,p.name])]);
    if(record.signature===signature)return;
    record.signature=signature;
    record.summary.textContent='Effetti e concentrazione · '+effects.length+' effetti annotati';
    const body=record.body;body.replaceChildren();
    if (!effects.length && !concentrations.length) body.append(node('p','muted','Nessun effetto temporaneo annotato. Le durate seguono i turni di gioco, anche mentre la chat è ferma.'));
    for (const effect of effects) {
      const card=node('article','table-effect'); card.append(node('h3','',effect.name || 'Effetto'));
      if (effect.description) card.append(node('p','',effect.description));
      const caster=arr(state.party).find(c=>c.id===(effect.caster_id || effect.actor_id));
      if (caster) card.append(node('small','',caster.name+(effect.concentration?' · concentrazione':'')));
      if (Number.isInteger(effect.expires_round)) {
        const expiresActor=arr(state.combat?.participants).find(p=>p.id===effect.expires_actor_id);
        const phase=effect.expires_phase || (expiresActor?'inizio turno di '+expiresActor.name:'');
        const expiry=Number(state.combat?.round)>effect.expires_round ? 'Scadenza da verificare con il DM' : 'Scadenza: round '+effect.expires_round+(phase?', '+phase:'');
        card.append(node('p','effect-expiry',expiry));
      } else if (effect.duration) card.append(node('p','effect-expiry',effect.duration));
      card.append(button('Chiedi dettagli',()=>onIntent?.('Vorrei chiarire durata e condizioni di «'+(effect.name || 'questo effetto')+'».'))); body.append(card);
    }
    for (const c of concentrations) {
      const value=c.concentration || c.concentrating;
      body.append(node('p','effect-concentration',c.name+' mantiene concentrazione'+(typeof value==='string'?' su '+value:typeof value?.spell==='string'?' su '+value.spell:'')+'.'));
    }
  }
  function reference(item,character,key) {
    const result=window.DndReference?.button({kind:'item',name:item.name,label:item.name,character,context:{item}}) || node('span','',item.name);
    result.id='party-chest-ref-'+key;return result;
  }
  function renderChest(config) {
    const {host,state,onIntent}=config; if (!host) return;
    let record=mounts.get(host);
    if (!record) {
      const section=node('section','party-chest'); const heading=node('div','party-chest-heading');
      heading.append(node('p','overline gold','OGGETTI E BOTTINO'),node('h2','','Le risorse del gruppo'));
      const input=node('input'); input.type='search'; input.id='party-chest-search'; input.placeholder='Cerca un oggetto o il proprietario'; input.setAttribute('aria-label','Cerca negli inventari del gruppo');
      const list=node('div','party-chest-list');list.setAttribute('role','region');list.setAttribute('aria-label','Inventari del gruppo');list.tabIndex=0;
      const count=node('p','party-chest-count');count.setAttribute('role','status');
      section.append(heading,node('p','muted','Gli oggetti conservano il proprio proprietario. Uso, recupero e passaggi si propongono in chat.'),input,count,list);
      host.replaceChildren(section); record={section,input,list,count,config}; mounts.set(host,record);
      input.addEventListener('input',()=>fillChest(record));
    }
    record.config=config; fillChest(record);
  }
  function fillChest(record) {
    const {state,onIntent}=record.config, query=norm(record.input.value);
    const rows=[];
    for (const c of arr(state.party)) for (const item of arr(c.inventory)) if (Number(item.qty)>0)
      rows.push({item,owner:c.name,character:c,location:'Inventario'});
    for (const item of arr(state.flags?.shared_inventory)) if (Number(item.qty)>0) rows.push({item,owner:'Gruppo',character:null,location:'Scorta comune'});
    const scene=state.flags?.table_scene;
    if (!scene?.location_id || scene.location_id===state.location_id) for (const item of arr(scene?.ground_items))
      if (Number(item.qty)>0) rows.push({item,owner:item.owner_name || 'Da recuperare',character:null,location:item.location || 'A terra'});
    const filtered=rows.filter(row=>norm(row.item.name+' '+row.owner+' '+row.location).includes(query));
    const signature=JSON.stringify([filtered,arr(state.party).map(c=>[c.id,c.name])]);
    if(record.signature===signature)return;
    record.signature=signature;
    const focus=record.list.contains(document.activeElement)?{id:document.activeElement.id,value:document.activeElement.value}:null;
    const scrollTop=record.list.scrollTop;
    const keys=new Map();
    const cards=filtered.map(row=>{
      const base=(row.character?.id||row.owner)+'|'+row.location+'|'+row.item.name;
      const occurrence=keys.get(base)||0;keys.set(base,occurrence+1);
      let hash=2166136261;for(const c of base+'|'+occurrence)hash=Math.imul(hash^c.charCodeAt(0),16777619);
      const key=(hash>>>0).toString(36);
      const card=node('article','party-chest-item'); const copy=node('div');
      copy.append(reference(row.item,row.character,key),node('small','',row.owner+' · '+row.location));
      card.append(copy,node('strong','','× '+row.item.qty));
      const tools=node('div','party-chest-actions');
      const use=button(row.location==='Inventario'?'Proponi uso':'Proponi recupero',()=>record.config.onIntent?.(row.location==='Inventario'?'Vorrei usare '+row.item.name+'.':'Vorrei recuperare '+row.item.name+' da '+row.location+'.',row.character?{actorId:row.character.id,actorName:row.character.name}:{}));
      use.id='party-chest-use-'+key;tools.append(use);
      if (row.character) {
        const select=node('select');select.id='party-chest-pass-'+key; select.setAttribute('aria-label','Destinatario di '+row.item.name); select.append(new Option('Passa a…',''));
        arr(state.party).filter(c=>c.id!==row.character.id).forEach(c=>select.append(new Option(c.name,c.id)));
        select.addEventListener('change',()=>{const target=arr(record.config.state.party).find(c=>c.id===select.value);if(target)record.config.onIntent?.('Vorrei passare '+row.item.name+' a '+target.name+'.',{actorId:row.character.id,actorName:row.character.name});select.value='';}); tools.append(select);
      }
      card.append(tools);return card;
    });
    record.list.replaceChildren(...(cards.length?cards:[node('p','muted','Nessun oggetto corrisponde alla ricerca.')]));
    record.count.textContent=cards.length+' '+(cards.length===1?'voce':'voci')+(query?' nella ricerca':' negli inventari');
    if(focus?.id){const target=document.getElementById(focus.id);if(target){if(target.tagName==='SELECT'&&[...target.options].some(option=>option.value===focus.value))target.value=focus.value;target.focus({preventScroll:true});}}
    record.list.scrollTop=scrollTop;
  }
  function recordMetric(name,ms) { if(Number.isFinite(ms)){samples.push({name,ms:Math.round(ms*100)/100,at:new Date().toISOString()});if(samples.length>60)samples.shift();} }
  function renderMetrics({host}) {
    if (!host) return;
    const open=host.querySelector('details')?.open || false, details=node('details','table-metrics'); details.open=open;
    details.append(node('summary','','Prestazioni del tavolo'));
    const body=node('div','table-metrics-body');
    body.append(node('p','muted','Tempi locali misurati nel browser. Le risposte del master includono anche ragionamento e chiamate agli strumenti, esterni a questa misura.'));
    for (const name of ['Lettura del tavolo','Disegno della plancia']) {
      const values=samples.filter(s=>s.name===name).map(s=>s.ms).sort((a,b)=>a-b);
      body.append(node('p','',name+': '+(values.length?values[Math.floor(values.length/2)]+' ms (mediana, '+values.length+' campioni)':'in attesa')));
    }
    body.append(button('Esporta misure',()=>{const blob=new Blob([JSON.stringify({scope:'browser_only',samples},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=node('a');link.href=url;link.download='prestazioni-tavolo.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
    details.append(body);host.replaceChildren(details);
  }
  window.DndTableTools=Object.freeze({current,advice,renderTurn,renderAdvice,renderEffects,renderChest,recordMetric,renderMetrics});
})();
