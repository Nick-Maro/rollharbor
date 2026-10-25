'use strict';

// Player-facing knowledge and atmosphere. This module never fetches private data,
// rolls dice, mutates campaign state or turns a player's theory into a fact.
(() => {
  const sessions = new WeakMap();
  const artworkSessions = new WeakMap();
  const notebookHosts = new WeakSet();
  const audioHosts = new Map();
  const memory = new Map();
  let nextId = 0;
  const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const list = value => Array.isArray(value) ? value : [];
  const strings = value => (Array.isArray(value) ? value : value ? [value] : []).map(item => typeof item === 'object' ? text(item.text || item.description || item.title) : text(item)).filter(Boolean);
  const normalize = value => text(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const records = value => Array.isArray(value) ? value : value && typeof value === 'object' ? Object.values(value) : [];
  const portraits = {
    gundren: '/assets/immersion/gundren.webp',
    sildar: '/assets/immersion/sildar.webp'
  };
  const artwork = {
    neverwinter: {asset:'/assets/immersion/neverwinter.webp', title:'Le strade di Neverwinter', caption:'Illustrazione d’atmosfera originale: i dettagli della scena sono quelli raccontati dal master.'}
  };

  function node(tag, className, content, attrs = {}) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (content !== undefined && content !== null) result.textContent = text(content);
    Object.entries(attrs).forEach(([name,value]) => result.setAttribute(name, String(value)));
    return result;
  }
  function append(parent, ...children) { children.flat(Infinity).filter(Boolean).forEach(child => parent.append(child)); return parent; }
  function button(label, callback, className = '') {
    const result = node('button', 'im-button ' + className, label, {type:'button'});
    result.addEventListener('click', callback);
    return result;
  }
  function keyFor(state, world) {
    return 'dnd-knowledge-v1:' + text(state.campaign_id || world.id || 'table') + ':' + text(state.flags?.run_id || state.created_at || 'current');
  }
  function readLocal(key) {
    try {
      const raw = localStorage.getItem(key);
      if (raw) return validateNotebook(JSON.parse(raw));
    } catch (_) { /* Browser storage can be disabled. Keep this session usable. */ }
    return memory.get(key) || {notes:[],links:[]};
  }
  function saveLocal(session) {
    memory.set(session.key, session.local);
    try { localStorage.setItem(session.key, JSON.stringify(session.local)); return true; }
    catch (_) { return false; }
  }
  function validateNotebook(value) {
    if (!value || typeof value !== 'object' || !Array.isArray(value.notes) || !Array.isArray(value.links)) throw new Error('Formato del taccuino non valido.');
    if (value.notes.length > 200 || value.links.length > 400) throw new Error('Il taccuino supera 200 appunti o 400 collegamenti.');
    const notes = value.notes.map((item,index) => ({id:text(item?.id).slice(0,120) || 'import-'+index,
      title:text(item?.title).slice(0,140), text:text(item?.text).slice(0,4000),
      kind:item?.kind === 'contact' ? 'contact' : 'clue', contact_id:text(item?.contact_id).slice(0,120)}));
    if (new Set(notes.map(item => item.id)).size !== notes.length) throw new Error('Gli appunti importati hanno identificatori duplicati.');
    const links = value.links.map((item,index) => ({id:text(item?.id).slice(0,120) || 'link-'+index,
      from:text(item?.from).slice(0,150),to:text(item?.to).slice(0,150),label:text(item?.label).slice(0,180)}));
    if (links.some(item => !item.from || !item.to || item.from === item.to)) throw new Error('Un collegamento non è valido.');
    return {notes,links};
  }

  function collectKnowledge(state = {}) {
    const flags = state.flags || {};
    const knowledge = flags.knowledge;
    const contacts = new Map();
    function addContact(value, origin) {
      if (typeof value === 'string') value = {name:value};
      if (!value || typeof value !== 'object' || !text(value.name)) return;
      const id = text(value.id) || normalize(value.name).replace(/\s+/g,'_');
      const previous = contacts.get(id) || [...contacts.values()].find(item => normalize(item.name) === normalize(value.name));
      const contact = {id:previous?.id || id,name:previous?.name || text(value.name),
        description:text(value.description || previous?.description), relationship:text(value.relationship || previous?.relationship),
        status:text(value.status || previous?.status), promises:strings(value.promises || previous?.promises),
        facts:strings(value.knowledge || value.facts || previous?.facts), origin:previous?.origin || origin};
      contacts.set(contact.id, contact);
    }
    records(flags.known_contacts).forEach(item => addContact(item,'Registrato dal master'));
    records(knowledge?.contacts).forEach(item => addContact(item,'Registrato dal master'));
    const party = new Set(list(state.party).map(item => item.id));
    list(state.combat?.participants).filter(item => !party.has(item.id)).forEach(item => addContact(item,'Incontrato nella scena'));
    // Only already published names are carried forward after an initiative closes.
    const publicText = [state.scene?.text,...list(state.journal).map(item => item.text)].map(text).join('\n');
    for (const name of ['Gundren','Sildar']) {
      if (new RegExp('\\b'+name+'\\b','i').test(publicText) && ![...contacts.values()].some(item => normalize(item.name).includes(normalize(name)))) addContact({id:'npc_'+name.toLowerCase(),name},'Nome presente nel diario pubblico');
    }
    const facts = [];
    const entries = Array.isArray(knowledge) ? knowledge : [...records(knowledge?.facts),...records(knowledge?.clues)];
    entries.forEach((entry,index) => {
      if (typeof entry === 'string') entry = {text:entry};
      if (!entry || typeof entry !== 'object') return;
      const value = text(entry.text || entry.description);
      if (!value && !text(entry.title)) return;
      facts.push({id:'known:'+text(entry.id || index),title:text(entry.title) || value.slice(0,90),text:value,source:text(entry.source || entry.obtained_from)});
    });
    return {contacts:[...contacts.values()],facts};
  }

  function portraitFor(contact) {
    const id = normalize(contact.id + ' ' + contact.name);
    return id.includes('gundren') ? portraits.gundren : id.includes('sildar') ? portraits.sildar : null;
  }
  function image(asset, alt, className = '') {
    return node('img',className,undefined,{src:asset,alt,loading:'lazy',decoding:'async'});
  }
  function mountArtwork({host,state = {},world = {}} = {}) {
    if (!host) return;
    const custom = state.flags?.scene_artwork;
    const safeCustom = custom && custom.location_id === state.location_id && /^\/assets\/immersion\/[a-z0-9_/-]+\.(webp|png|jpe?g)$/i.test(text(custom.asset));
    const scene = safeCustom ? custom : artwork[state.location_id];
    const known = new Set(list(state.discovered));
    const contacts = collectKnowledge(state).contacts;
    const signature = JSON.stringify([known.has(state.location_id) ? scene : null,contacts.map(item => [item.id,item.name])]);
    if (artworkSessions.get(host) === signature) return;
    artworkSessions.set(host,signature);
    host.replaceChildren();
    host.classList.add('im-artwork');
    if (scene && known.has(state.location_id)) {
      const figure = node('figure','im-scene-art');
      const frame = node('div','im-art-frame');
      const placeholder = append(node('div','im-art-placeholder',undefined,{'aria-hidden':'true'}),
        node('span','im-art-emblem','✦'),node('span','im-art-loading','L’illustrazione prende forma…'));
      const sceneImage=image(scene.asset,text(scene.title) || 'Atmosfera della scena');
      sceneImage.loading='eager';
      sceneImage.fetchPriority='high';
      sceneImage.addEventListener('load',()=>frame.classList.add('is-loaded'),{once:true});
      sceneImage.addEventListener('error',()=>{frame.classList.add('is-unavailable');placeholder.querySelector('.im-art-loading').textContent='Illustrazione non disponibile. La scena continua nel racconto.';},{once:true});
      append(frame,placeholder,sceneImage);
      if(sceneImage.complete&&sceneImage.naturalWidth>0)frame.classList.add('is-loaded');
      append(figure,frame,
        append(node('figcaption'),node('strong','',scene.title || 'La scena'),node('span','',scene.caption || 'Interpretazione visiva; la descrizione del master definisce i dettagli.')));
      host.append(figure);
    }
    const knownPortraits = contacts.filter(item => portraitFor(item));
    if (knownPortraits.length) {
      const row = node('div','im-portrait-row',undefined,{'aria-label':'Volti conosciuti'});
      knownPortraits.forEach(contact => {
        const figure = node('figure','im-portrait');
        append(figure,image(portraitFor(contact),'Interpretazione visiva di '+contact.name),
          append(node('figcaption'),node('strong','',contact.name),node('small','','Interpretazione visiva')));
        row.append(figure);
      });
      host.append(row);
    }
    if(host.childElementCount){
      host.append(node('a','im-art-library','Sfoglia illustrazioni d’atmosfera ↗',{href:'/artworks.html',target:'_blank',rel:'noopener'}));
    }
    host.hidden = !host.childElementCount;
  }

  function field(session, label, name, {textarea = false,maxLength = 4000,required = false} = {}) {
    const id = 'immersion-'+session.uid+'-'+name;
    const input = node(textarea?'textarea':'input','',undefined,{id,name,maxlength:maxLength});
    if (textarea) input.rows = 3;
    if (required) input.required = true;
    return {input,element:append(node('div','im-field'),node('label','',label,{for:id}),input)};
  }
  function status(session,value) { session.status.textContent = value; }
  function persist(session,message) {
    const durable = saveLocal(session);
    drawNotebook(session,true);
    status(session,durable ? message : message+' Il browser non consente il salvataggio: esportate il taccuino prima di chiudere.');
  }
  function headings(kicker,title) { return append(node('header','im-heading'),node('p','im-kicker',kicker),node('h3','',title)); }
  function intent(session,label,message) {
    const result = button(label,()=>session.args.onIntent?.(message));
    result.disabled = typeof session.args.onIntent !== 'function';
    return result;
  }
  function contactCard(session,contact) {
    const card = node('article','im-contact');
    const top = node('div','im-contact-top');
    const portrait = portraitFor(contact);
    if (portrait) top.append(image(portrait,'Interpretazione di '+contact.name));
    append(top,append(node('div'),node('h4','',contact.name),node('p','im-subtle',contact.origin)));
    card.append(top);
    for (const [label,value] of [['Descrizione',contact.description],['Rapporto',contact.relationship],['Situazione',contact.status]]) {
      if (value) card.append(append(node('p'),node('strong','',label+': '),node('span','',value)));
    }
    for (const [title,values] of [['Promesse e accordi',contact.promises],['Ciò che sappiamo',contact.facts]]) {
      if (!values.length) continue;
      const ul = node('ul');
      values.forEach(value=>ul.append(node('li','',value)));
      append(card,node('h5','',title),ul);
    }
    if (!contact.description && !contact.relationship && !contact.promises.length && !contact.facts.length) card.append(node('p','im-subtle','Nessun altro dettaglio registrato.'));
    const notes = session.local.notes.filter(item => item.kind === 'contact' && item.contact_id === contact.id);
    if (notes.length) {
      card.append(node('h5','','I vostri appunti'));
      notes.forEach(note=>card.append(noteCard(session,note)));
    }
    card.append(intent(session,'Chiedi al master','Vorrei sapere che cosa ricordo di '+contact.name+'.'));
    const details = node('details','im-note-details',undefined,{'data-notebook-key':'contact-'+contact.id});
    details.append(node('summary','','Annota un rapporto o una promessa'));
    const form = node('form','im-form');
    const note = field(session,'Appunto personale su '+contact.name,'contact-'+contact.id,{textarea:true,required:true});
    append(form,note.element,node('button','im-button','Conserva appunto',{type:'submit'}));
    form.addEventListener('submit',event=>{
      event.preventDefault();
      if (!note.input.value.trim()) return;
      if (session.local.notes.length >= 200) { status(session,'Limite di 200 appunti raggiunto: esportate o eliminate un appunto.'); return; }
      session.local.notes.push({id:'note-'+Date.now()+'-'+(++nextId),title:contact.name,text:note.input.value.trim(),kind:'contact',contact_id:contact.id});
      note.input.value='';
      persist(session,'Appunto conservato nel taccuino di questo browser.');
    });
    details.append(form); card.append(details);
    return card;
  }
  function noteCard(session,note) {
    const card = node('article','im-note');
    append(card,node('strong','',note.title),node('p','',note.text),node('small','im-hypothesis','Appunto dei giocatori'));
    card.append(button('Elimina appunto',()=>{
      session.local.notes = session.local.notes.filter(item=>item.id !== note.id);
      session.local.links = session.local.links.filter(item=>item.from !== note.id && item.to !== note.id);
      persist(session,'Appunto eliminato.');
    },'im-delete'));
    return card;
  }
  function contactPanel(session) {
    const section = node('section','im-section');
    append(section,headings('LE PERSONE DELLA STORIA','Volti, rapporti e promesse'),
      node('p','im-subtle','Il master registra ciò che avete scoperto. Potete aggiungere le vostre impressioni senza trasformarle in fatti.'));
    const grid = node('div','im-contact-grid');
    session.knowledge.contacts.forEach(contact=>grid.append(contactCard(session,contact)));
    if (!grid.childElementCount) grid.append(node('p','im-empty','I contatti compariranno quando li conoscerete durante l’avventura.'));
    section.append(grid);
    return section;
  }
  function cluePanel(session) {
    const section = node('section','im-section');
    append(section,headings('LA VOSTRA INDAGINE','Indizi e collegamenti'),node('p','im-subtle','Collegate persone e indizi per costruire le vostre ipotesi. I fili sono appunti personali, non conferme del master.'));
    const grid = node('div','im-clue-grid');
    session.knowledge.facts.forEach(fact=>{
      const card = node('article','im-clue im-known-clue');
      append(card,node('small','im-fact-label','Conoscenza registrata'),node('h4','',fact.title),node('p','',fact.text));
      if (fact.source) card.append(node('small','im-subtle','Fonte conosciuta: '+fact.source));
      grid.append(card);
    });
    session.local.notes.filter(item=>item.kind==='clue').forEach(note=>grid.append(noteCard(session,note)));
    if (!grid.childElementCount) grid.append(node('p','im-empty','Nessun indizio annotato. Aggiungete una scoperta o una domanda da ricordare.'));
    section.append(grid);
    const form = node('form','im-form im-clue-form');
    const title = field(session,'Titolo dell’indizio o della domanda','clue-title',{maxLength:140,required:true});
    const body = field(session,'Il vostro appunto','clue-text',{textarea:true,required:true});
    append(form,title.element,body.element,node('button','im-button','Aggiungi al taccuino',{type:'submit'}));
    form.addEventListener('submit',event=>{
      event.preventDefault();
      if (!title.input.value.trim() || !body.input.value.trim()) return;
      if (session.local.notes.length >= 200) { status(session,'Limite di 200 appunti raggiunto.'); return; }
      session.local.notes.push({id:'note-'+Date.now()+'-'+(++nextId),title:title.input.value.trim(),text:body.input.value.trim(),kind:'clue',contact_id:''});
      title.input.value='';body.input.value='';
      persist(session,'Indizio annotato in questo browser.');
    });
    section.append(form);
    const choices = [...session.knowledge.contacts.map(item=>({id:'contact:'+item.id,title:item.name})),...session.knowledge.facts,...session.local.notes];
    if (choices.length >= 2) {
      const formLink = node('form','im-form im-link-form');
      formLink.append(node('h4','','Collega due elementi'));
      const selects = ['from','to'].map((name,index)=>{
        const id = 'immersion-'+session.uid+'-link-'+name;
        const select = node('select','',undefined,{id,name});
        choices.forEach(choice=>select.append(node('option','',choice.title,{value:choice.id})));
        select.selectedIndex=index;
        formLink.append(append(node('div','im-field'),node('label','',index?'Secondo elemento':'Primo elemento',{for:id}),select));
        return select;
      });
      const label = field(session,'Perché pensate siano collegati?','link-label',{maxLength:180,required:true});
      append(formLink,label.element,node('button','im-button','Aggiungi collegamento',{type:'submit'}));
      formLink.addEventListener('submit',event=>{
        event.preventDefault();
        if (selects[0].value===selects[1].value) { status(session,'Scegliete due elementi diversi.'); return; }
        if (!label.input.value.trim()) return;
        if (session.local.links.length >= 400) { status(session,'Limite di 400 collegamenti raggiunto.'); return; }
        session.local.links.push({id:'link-'+Date.now()+'-'+(++nextId),from:selects[0].value,to:selects[1].value,label:label.input.value.trim()});
        label.input.value='';
        persist(session,'Collegamento aggiunto come vostra ipotesi.');
      });
      section.append(formLink);
    }
    if (session.local.links.length) {
      const links = node('ul','im-links',undefined,{'aria-label':'Collegamenti ipotizzati dai giocatori'});
      const byId = new Map(choices.map(item=>[item.id,item.title]));
      session.local.links.forEach(link=>{
        const item = node('li');
        append(item,node('div','im-link-names',(byId.get(link.from)||'Elemento non più presente')+' ↔ '+(byId.get(link.to)||'Elemento non più presente')),
          node('p','',link.label),node('small','im-hypothesis','Vostra ipotesi'),
          button('Rimuovi collegamento',()=>{session.local.links=session.local.links.filter(item=>item.id!==link.id);persist(session,'Collegamento rimosso.');},'im-delete'));
        links.append(item);
      });
      section.append(links);
    }
    return section;
  }
  function transferPanel(session) {
    const row=node('div','im-transfer');
    const exportButton=button('Esporta taccuino',()=>{
      const data=JSON.stringify({version:1,...session.local},null,2);
      const url=URL.createObjectURL(new Blob([data],{type:'application/json'}));
      const anchor=node('a','',undefined,{href:url,download:'taccuino-'+text(session.args.state.campaign_id||'dnd')+'.json'});
      anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    const file=node('input','',undefined,{type:'file',accept:'.json,application/json',hidden:''});
    file.addEventListener('change',async()=>{
      const selected=file.files?.[0];
      if(!selected)return;
      try{
        if(selected.size>2000000)throw new Error('Scegliete un taccuino JSON inferiore a 2 MB.');
        const imported=validateNotebook(JSON.parse(await selected.text()));
        const notesById=new Map(session.local.notes.map(item=>[item.id,item]));
        imported.notes.forEach(item=>{if(!notesById.has(item.id))notesById.set(item.id,item);});
        const linksById=new Map(session.local.links.map(item=>[item.id,item]));
        imported.links.forEach(item=>{if(!linksById.has(item.id))linksById.set(item.id,item);});
        session.local=validateNotebook({notes:[...notesById.values()],links:[...linksById.values()]});
        persist(session,'Taccuino importato: gli appunti esistenti sono conservati.');
      }catch(error){status(session,'Importazione non riuscita: '+error.message);}
      file.value='';
    });
    append(row,exportButton,button('Importa taccuino',()=>file.click()),file,node('small','im-subtle','Appunti salvati in questo browser. Esportateli per portarli su un altro dispositivo.'));
    return row;
  }
  function drawNotebook(session, preserveDraft = false) {
    const active=document.activeElement;
    const wasInside=session.args.host.contains(active);
    const focusId=wasInside?active.id:null;
    const drafts=preserveDraft?[...session.args.host.querySelectorAll('input[id]:not([type=file]),textarea[id],select[id]')].map(item=>({id:item.id,value:item.value})):[];
    const disclosures=preserveDraft?[...session.args.host.querySelectorAll('details[data-notebook-key]')].map(item=>({key:item.dataset.notebookKey,open:item.open})):[];
    const selection=wasInside&&typeof active.selectionStart==='number'?{start:active.selectionStart,end:active.selectionEnd}:null;
    session.args.host.replaceChildren();
    session.args.host.classList.add('im-notebook');
    append(session.args.host,contactPanel(session),cluePanel(session),transferPanel(session),session.status);
    drafts.forEach(draft=>{const target=document.getElementById(draft.id);if(target)target.value=draft.value;});
    disclosures.forEach(saved=>{const target=[...session.args.host.querySelectorAll('details[data-notebook-key]')].find(item=>item.dataset.notebookKey===saved.key);if(target)target.open=saved.open;});
    if(focusId){const target=document.getElementById(focusId);target?.focus({preventScroll:true});if(target&&selection)target.setSelectionRange?.(selection.start,selection.end);}
  }
  function render(args={}) {
    if(!args.host)return;
    if(!notebookHosts.has(args.host)){
      notebookHosts.add(args.host);
      args.host.addEventListener('focusout',()=>setTimeout(()=>{
        const pending=sessions.get(args.host);
        if(pending?.deferred&&!args.host.contains(document.activeElement)){
          pending.deferred=false;render(pending.args);
        }
      },0));
    }
    const state=args.state||{},world=args.world||{};
    const key=keyFor(state,world);
    let session=sessions.get(args.host);
    if(!session||session.key!==key){session={uid:++nextId,key,local:readLocal(key),status:node('p','im-status','',{role:'status','aria-live':'polite'})};sessions.set(args.host,session);}
    session.args={...args,state,world};
    session.knowledge=collectKnowledge(state);
    const signature=JSON.stringify(session.knowledge);
    if(session.signature===signature)return;
    // A polling update must not erase a partly written note. Delay visual changes
    // until focus leaves the notebook; state/knowledge references are current.
    if(args.host.contains(document.activeElement)){
      session.deferred=true;
      return;
    }
    session.signature=signature;
    drawNotebook(session,true);
  }

  const sound={context:null,master:null,nodes:[],timer:null,enabled:false,volume:0.18,scene:'wind',paused:false,error:''};
  const soundNames={wind:'Vento',rain:'Pioggia',tavern:'Taverna',battle:'Battaglia'};
  function updateAudio(){
    for(const[host,controls]of audioHosts){
      if(!host.isConnected){audioHosts.delete(host);continue;}
      controls.toggle.textContent=sound.enabled?'Spegni atmosfera':'Attiva atmosfera';
      controls.toggle.setAttribute('aria-pressed',String(sound.enabled));
      controls.scene.value=sound.scene;controls.volume.value=String(Math.round(sound.volume*100));
      controls.value.textContent=Math.round(sound.volume*100)+'%';
      controls.status.textContent=sound.error||(sound.enabled?(sound.paused?'In pausa mentre la scheda è nascosta.':sound.volume===0?'Atmosfera silenziata.':'Atmosfera attiva · '+soundNames[sound.scene]):'Spenta. Si attiva soltanto quando lo scegliete.');
    }
  }
  function stopNodes(){
    if(sound.timer){clearInterval(sound.timer);sound.timer=null;}
    sound.nodes.forEach(item=>{try{item.stop?.();item.disconnect?.();}catch(_){}});sound.nodes=[];
  }
  function noise(context){
    const buffer=context.createBuffer(1,context.sampleRate*3,context.sampleRate),data=buffer.getChannelData(0);
    for(let i=0;i<data.length;i++)data[i]=Math.random()*2-1;
    const source=context.createBufferSource();source.buffer=buffer;source.loop=true;return source;
  }
  function buildSound(){
    stopNodes();
    const context=sound.context;if(!context||!sound.enabled||document.hidden)return;
    const source=noise(context),filter=context.createBiquadFilter(),gain=context.createGain();
    filter.type=sound.scene==='rain'?'highpass':'lowpass';
    filter.frequency.value={wind:600,rain:1300,tavern:380,battle:500}[sound.scene];
    gain.gain.value={wind:0.13,rain:0.075,tavern:0.16,battle:0.08}[sound.scene];
    source.connect(filter);filter.connect(gain);gain.connect(sound.master);source.start();
    sound.nodes.push(source,filter,gain);
    if(sound.scene==='wind'){
      const lfo=context.createOscillator(),depth=context.createGain();lfo.frequency.value=0.13;depth.gain.value=240;
      lfo.connect(depth);depth.connect(filter.frequency);lfo.start();sound.nodes.push(lfo,depth);
    }
    if(sound.scene==='tavern'||sound.scene==='battle'){
      const scene=sound.scene;
      sound.timer=setInterval(()=>{
        if(!sound.enabled||document.hidden||context.state!=='running')return;
        const oscillator=context.createOscillator(),envelope=context.createGain(),time=context.currentTime;
        oscillator.type=scene==='battle'?'sine':'triangle';
        oscillator.frequency.setValueAtTime(scene==='battle'?90:120+Math.random()*90,time);
        oscillator.frequency.exponentialRampToValueAtTime(scene==='battle'?42:100,time+0.24);
        envelope.gain.setValueAtTime(0.0001,time);envelope.gain.exponentialRampToValueAtTime(scene==='battle'?0.21:0.025,time+0.012);
        envelope.gain.exponentialRampToValueAtTime(0.0001,time+0.3);
        oscillator.connect(envelope);envelope.connect(sound.master);oscillator.start(time);oscillator.stop(time+0.35);
        sound.nodes.push(oscillator,envelope);
        oscillator.onended=()=>{oscillator.disconnect();envelope.disconnect();sound.nodes=sound.nodes.filter(item=>item!==oscillator&&item!==envelope);};
      },scene==='battle'?850:700);
    }
  }
  async function startAudio(){
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio){sound.error='Questo browser non supporta l’atmosfera audio.';updateAudio();return;}
    try{
      if(!sound.context){sound.context=new Audio();sound.master=sound.context.createGain();sound.master.gain.value=sound.volume;sound.master.connect(sound.context.destination);}
      sound.enabled=true;sound.error='';sound.paused=document.hidden;
      if(!document.hidden){await sound.context.resume();buildSound();}
    }catch(_){sound.enabled=false;sound.error='Audio non disponibile. Potete riprovare con Attiva atmosfera.';}
    updateAudio();
  }
  function stopAudio(){sound.enabled=false;sound.paused=false;stopNodes();sound.context?.suspend().catch(()=>{});updateAudio();}
  function mountAtmosphere({host}={}){
    if(!host||audioHosts.has(host))return;
    host.classList.add('im-atmosphere');
    const controls={toggle:button('Attiva atmosfera',()=>sound.enabled?stopAudio():startAudio()),
      scene:node('select','',undefined,{'aria-label':'Ambiente sonoro'}),
      volume:node('input','',undefined,{type:'range',min:0,max:100,step:1,'aria-label':'Volume atmosfera'}),
      value:node('output','im-volume-value'),status:node('p','im-audio-status','',{role:'status'})};
    Object.entries(soundNames).forEach(([value,label])=>controls.scene.append(node('option','',label,{value})));
    controls.scene.addEventListener('change',()=>{sound.scene=controls.scene.value;if(sound.enabled)buildSound();updateAudio();});
    controls.volume.addEventListener('input',()=>{sound.volume=Number(controls.volume.value)/100;if(sound.master)sound.master.gain.setTargetAtTime(sound.volume,sound.context.currentTime,0.03);updateAudio();});
    append(host,node('span','im-kicker','ATMOSFERA'),controls.toggle,controls.scene,
      append(node('label','im-volume'),node('span','','Volume'),controls.volume,controls.value),controls.status);
    audioHosts.set(host,controls);updateAudio();
  }
  document.addEventListener('visibilitychange',()=>{
    if(!sound.enabled)return;
    sound.paused=document.hidden;
    if(document.hidden){stopNodes();sound.context?.suspend().catch(()=>{});updateAudio();}
    else{sound.context?.resume().then(()=>{if(sound.enabled&&!document.hidden)buildSound();updateAudio();}).catch(()=>{sound.error='Premete Spegni e Attiva atmosfera per riprendere l’audio.';updateAudio();});}
  });
  window.addEventListener('pagehide',stopAudio);
  window.DndImmersion={render,mountArtwork,mountAtmosphere,collectKnowledge,
    configure:()=>{},stopAudio,getAudioState:()=>({enabled:sound.enabled,volume:sound.volume,scene:sound.scene,paused:sound.paused})};
})();
