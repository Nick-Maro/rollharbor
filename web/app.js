'use strict';

const $ = selector => document.querySelector(selector);
const NS = 'http://www.w3.org/2000/svg';
let world = null, state = null, selectedLocation = null, zoom = 1, toastTimer;
let selectedView = 'atlante', characterRenderKey = '', importCandidate = null, importRevision = null, polling = false;
let tableStatus = null, worldRenderKey = '', tableStatusKey = '', diceActorName = '', tableConnected = false;
const tableViews = ['atlante','combattimento','scena','personaggio','diario','taccuino','guida'];
let followingTurn=true;
let actionDockVisible=false;
try { followingTurn=localStorage.getItem('dnd-follow-turn')!=='false'; } catch { /* A private browser can keep this preference in memory. */ }
let initialViewPending = !tableViews.includes(location.hash.slice(1));
const abilityNames = {str:'Forza',dex:'Destrezza',con:'Costituzione',int:'Intelligenza',wis:'Saggezza',cha:'Carisma'};
const abilityShort = {str:'FOR',dex:'DES',con:'COS',int:'INT',wis:'SAG',cha:'CAR'};
const skillNames = {acrobatics:'Acrobazia',animal_handling:'Addestrare animali',arcana:'Arcano',athletics:'Atletica',deception:'Inganno',history:'Storia',insight:'Intuizione',intimidation:'Intimidire',investigation:'Indagare',medicine:'Medicina',nature:'Natura',perception:'Percezione',performance:'Intrattenere',persuasion:'Persuasione',religion:'Religione',sleight_of_hand:'Rapidità di mano',stealth:'Furtività',survival:'Sopravvivenza'};
const skillAbilities = {acrobatics:'dex',animal_handling:'wis',arcana:'int',athletics:'str',deception:'cha',history:'int',insight:'wis',intimidation:'cha',investigation:'int',medicine:'wis',nature:'int',perception:'wis',performance:'cha',persuasion:'cha',religion:'int',sleight_of_hand:'dex',stealth:'dex',survival:'wis'};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
function svgEl(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function icon(name) {
  const node = svgEl('svg', {'aria-hidden':'true'});
  node.append(svgEl('use', {href:'#i-' + name}));
  return node;
}
const signed = value => Number(value) >= 0 ? '+' + value : String(value);
const modifier = score => Math.floor((Number(score) - 10) / 2);
const timeText = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('it-IT', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); };
const locationById = id => world?.locations.find(location => location.id === id);
function referenceButton(kind, name, label = name, context = {}, character = state?.character) {
  const button = window.DndReference?.button({kind,name,label,context,character}) || el('span',{},label);
  // A stable ID lets the inspector return keyboard focus after a live redraw.
  let hash = 2166136261;
  for (const letter of String(name)+'|'+(context.referenceGroup || '')) hash = Math.imul(hash ^ letter.charCodeAt(0),16777619);
  button.id = 'reference-'+(character?.id || 'table')+'-'+kind+'-'+(hash >>> 0).toString(36);
  return button;
}
function viewCharacter() {
  const turn=window.DndTableTools?.current(state || {});
  return followingTurn && selectedView==='combattimento' && turn ? state?.party?.find(c=>c.id===turn.id) || state?.character : state?.character;
}
function presentationState() { const c=viewCharacter();return c ? {...state,character:c,active_character_id:c.id} : state; }
function setFollowTurn(value) {
  followingTurn=Boolean(value);
  try { localStorage.setItem('dnd-follow-turn',String(followingTurn)); } catch { /* Session preference still works. */ }
  if(state) render(state,true);
}
window.DndReference?.configure({getCharacter:id=>id ? state?.party?.find(character=>character.id===id) || null : viewCharacter()});
function statRow(label, bonus, context, character, diceLabel = label) {
  return el('div',{class:'reference-stat-row'},
    referenceButton('rule',label,label,{stat:context},character),
    el('button',{class:'skill-button reference-roll-button',title:'Prepara il tiro di '+diceLabel,'aria-label':'Prepara il tiro di '+diceLabel,
      onclick:()=>openDice('1d20'+signed(bonus),diceLabel)},el('strong',{},signed(bonus)),el('span',{'aria-hidden':'true'},' ↗')));
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').className = 'toast show' + (error ? ' error' : '');
  toastTimer = setTimeout(() => { $('#toast').className = 'toast'; }, error ? 7500 : 5200);
}
async function api(path, body) {
  const startedAt=performance.now();
  const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),8000);
  try {
    const options = body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
    const response = await fetch('/api/' + path,{...options,signal:controller.signal});
    let result;
    try { result = await response.json(); } catch { throw new Error('Il server non ha risposto correttamente. Riapri AVVIA.cmd.'); }
    if (!response.ok) { const error = new Error(result.error || 'Operazione non riuscita.'); error.status=response.status; throw error; }
    if(path==='table') window.DndTableTools?.recordMetric('Lettura del tavolo',performance.now()-startedAt);
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Il tavolo non risponde. Riapri AVVIA.cmd: la pagina si ricollegherà.');
    throw error;
  } finally { clearTimeout(timeout); }
}
function setConnected(online) {
  tableConnected = online;
  $('#connection').className = 'connection ' + (online ? 'online' : 'error');
  $('#connection').replaceChildren(el('span'), online ? 'Tavolo connesso' : 'Tavolo scollegato');
}
function showView(view) {
  if (!tableViews.includes(view)) view = 'atlante';
  const previousView=selectedView;
  selectedView = view;
  document.body.dataset.view=view;
  const skip=$('.skip-link'); if(skip)skip.href='#view-'+view;
  for (const section of document.querySelectorAll('.view')) { const active = section.id === 'view-' + view; section.hidden = !active; section.classList.toggle('active', active); }
  for (const button of document.querySelectorAll('[data-view]')) { const active = button.dataset.view === view; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); }
  if (location.hash !== '#' + view) history.replaceState(null,'','#' + view);
  const dock=$('#table-action-dock');
  if (dock) dock.hidden=view==='guida';
  const metrics=$('#performance-panel'); if(metrics)metrics.hidden=view!=='guida';
  const jump=$('#action-jump'); if(jump)jump.hidden=view==='guida' || actionDockVisible;
  if(previousView!==view) window.scrollTo({top:0,behavior:'auto'});
  if(state && previousView!==view) queueMicrotask(()=>render(state,true));
}
function preserveFocus() {
  const active = document.activeElement;
  const id = active?.id;
  const locationId = active?.getAttribute('data-location-id');
  const selection = typeof active?.selectionStart === 'number' ? [active.selectionStart,active.selectionEnd,active.selectionDirection] : null;
  return () => {
    const replacement = id ? document.getElementById(id) : locationId ? [...document.querySelectorAll('[data-location-id]')].find(node=>node.getAttribute('data-location-id')===locationId) : null;
    if (replacement && replacement !== active) {
      replacement.focus({preventScroll:true});
      if (selection && replacement.setSelectionRange) replacement.setSelectionRange(...selection);
    }
  };
}
function renderTableStatus() {
  const count=(state.party || []).length, size=state.party_size || 4;
  const started=tableStatus?.started ?? Boolean(state.flags?.started || state.flags?.adventure_started || state.flags?.character_creation_locked || state.combat.active || state.journal.some(entry=>entry.kind==='master'));
  const current=state.combat.active ? state.combat.participants[state.combat.turn_index] : null;
  const key=JSON.stringify([count,size,started,state.phase,state.combat.active,state.combat.round,current?.id,current?.name]);
  if (key===tableStatusKey) return;
  tableStatusKey=key;
  const host=$('#table-status');
  if (state.phase==='ended') {
    host.replaceChildren(el('div',{},el('h2',{},'Un capitolo si è concluso.'),el('p',{},'Personaggi e conseguenze restano salvati. Parliamone in chat per scegliere come proseguire.')));
  } else if (count<size) {
    host.replaceChildren(el('div',{},el('h2',{},'Il vostro gruppo · '+count+' / '+size),el('p',{},'Scegliete i vostri personaggi in Il gruppo, oppure raccontatemi in chat chi volete interpretare.')),el('button',{type:'button',class:'outline-button',onclick:()=>showView('personaggio')},'Completa il gruppo'));
  } else if (!started) {
    host.replaceChildren(el('div',{},el('h2',{},'Siete pronti. La parola passa a voi.'),el('p',{},'Scrivetemi «Avvia la partita» nella chat. Potete ancora modificare i personaggi.')),el('button',{type:'button',id:'copy-start',class:'primary-button',onclick:async()=>{const copied=await copyText('Avvia la partita');toast(copied?'Copiato. Incollate «Avvia la partita» nella chat con il master.':'Scrivete «Avvia la partita» nella chat con il master.');}},'Copia il messaggio di avvio'));
  } else if (current) {
    host.replaceChildren(el('div',{},el('p',{class:'overline gold'},'ROUND '+state.combat.round),el('h2',{},'Tocca a '+current.name),el('p',{},'Scegliete liberamente in chat. La scheda selezionata non cambia il turno.')),
      el('div',{class:'table-status-actions'},el('button',{type:'button',class:'outline-button',onclick:()=>showView('combattimento')},'Apri battaglia'),el('button',{type:'button',class:'quiet-button',onclick:()=>focusAction()},'Scrivi un’azione ↓')));
  } else {
    host.replaceChildren(el('div',{},el('h2',{},'Si gioca nella chat.'),el('p',{},'Ditemi che cosa fate: aggiorno scena, luoghi e schede mentre giochiamo. Le idee della plancia sono solo suggerimenti.')),
      el('button',{type:'button',class:'outline-button',onclick:()=>showView('scena')},'Apri la scena'));
  }
}
function render(next, force = false) {
  if (state && next.campaign_id===state.campaign_id && next.revision<state.revision) return;
  if (!force && state && next.revision === state.revision && next.campaign_id === state.campaign_id) return;
  const renderStarted=performance.now();
  const restoreFocus=preserveFocus();
  const pendingOpen=$('#pending-details')?.open;
  state = next;
  document.body.dataset.combatActive=String(Boolean(state.combat?.active));
  if (initialViewPending) {
    initialViewPending=false;
    if (state.combat.active) showView('combattimento');
    else if (state.flags?.started || state.phase==='playing') showView('scena');
  }
  if (tableStatus && tableStatus.revision!==state.revision) tableStatus=null;
  $('#action-actor-label').textContent = 'Parlate liberamente in chat: intenzioni, domande, dialoghi o idee vostre. Qui potete preparare un messaggio da copiare.';
  const viewed=viewCharacter();
  $('#action-speaker option[value="active"]').textContent=viewed ? viewed.name+(followingTurn && selectedView==='combattimento' && state.combat.active?' · segui turno':' · scheda selezionata') : 'Nessun personaggio selezionato';
  renderTableStatus();
  $('#campaign-title').textContent = world.title;
  $('#campaign-subtitle').textContent = world.subtitle || 'Ogni scelta lascia una traccia.';
  $('#session-label').textContent = 'SESSIONE ' + String(state.session).padStart(2,'0');
  $('#current-location').textContent = locationById(state.location_id)?.name || state.location_id;
  $('#world-day').textContent = 'Giorno ' + state.clock.day;
  $('#world-time').textContent = state.clock.time;
  const weather=String(state.clock.weather || '');
  const weatherKnown=weather && !/da stabilire|non descritto|da definire/i.test(weather);
  $('#world-weather').textContent = weatherKnown ? weather : 'Meteo non descritto';
  $('#world-weather').closest('.weather').hidden=!weatherKnown;
  $('#save-state').textContent = 'Salvato · rev. ' + state.revision;
  $('#revision-label').textContent = 'SESSIONE ' + String(state.session).padStart(2,'0') + ' · REVISIONE ' + state.revision;
  document.title = world.title + ' · Tavolo d’avventura';
  if (!selectedLocation || !state.discovered.includes(selectedLocation)) selectedLocation = state.location_id;
  const activeQuest = state.quests.find(quest => quest.status === 'active');
  $('#sidebar-quest-title').textContent = activeQuest?.title || 'Una nuova strada';
  $('#sidebar-quest-text').textContent = activeQuest?.description || 'L’avventura continua. Decidi tu dove andare.';
  $('#scene-title').textContent = state.scene.title;
  $('#scene-text').replaceChildren(...state.scene.text.split(/\n\s*\n/).filter(Boolean).map(p => el('p',{},p)));
  $('#scene-choices').replaceChildren(...state.scene.choices.map(choice => el('button',{class:'choice-button',onclick:()=>prepareAction(choice)},el('span',{class:'choice-mark'},'›'),el('span',{},choice))));
  renderMap(); renderLocation(); renderMiniCharacter(); renderCharacter(); renderJournal(); renderRolls(); renderPending(); renderCombat();
  renderTableViews();
  renderActionAdvice();
  if (pendingOpen && $('#pending-details')) $('#pending-details').open=true;
  restoreFocus();
  window.DndReference?.refresh();
  window.DndTableTools?.recordMetric('Disegno della plancia',performance.now()-renderStarted);
  window.DndTableTools?.renderMetrics({host:$('#performance-panel')});
}
function renderMap() {
  $('#fog-holes').replaceChildren(...state.discovered.map(id => locationById(id)).filter(Boolean).map(loc => svgEl('circle',{cx:loc.x,cy:loc.y,r:165,fill:'black'})));
  $('#map-paths').replaceChildren(...world.paths.filter(([a,b]) => state.discovered.includes(a) && state.discovered.includes(b)).map(([a,b]) => {
    const start = locationById(a), end = locationById(b);
    return svgEl('path',{d:`M${start.x} ${start.y} Q${(start.x+end.x)/2} ${(start.y+end.y)/2+18} ${end.x} ${end.y}`});
  }));
  $('#map-pins').replaceChildren(...state.discovered.map(id => locationById(id)).filter(Boolean).map(loc => {
    const current = loc.id === state.location_id;
    const group = svgEl('g',{class:'map-pin' + (loc.id === selectedLocation ? ' selected' : ''),'data-location-id':loc.id,transform:`translate(${loc.x} ${loc.y})`,role:'button',tabindex:0,'aria-label':loc.name + (current ? ', la vostra posizione' : ''),'aria-pressed':String(loc.id === selectedLocation)});
    if (current) group.append(svgEl('circle',{r:23,class:'player-ring'}));
    group.append(svgEl('circle',{r:current ? 15 : 11,fill:current?'#2e5238':'#e6ddbd',stroke:'#3f583c','stroke-width':2}));
    if (current) group.append(svgEl('path',{d:'M0 -6 5 5 0 2 -5 5Z',fill:'#e2c57d'}));
    else group.append(svgEl('path',{d:'M0 -5 5 0 0 5 -5 0Z',fill:'#486044'}));
    group.append(svgEl('text',{y:current ? 43 : 35,'text-anchor':'middle'},loc.name));
    const select = () => { const restoreFocus=preserveFocus(); selectedLocation = loc.id; renderMap(); renderLocation(); restoreFocus(); };
    group.addEventListener('click',select);
    group.addEventListener('keydown',event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
    return group;
  }));
  $('#discovery-count').textContent = state.discovered.length + (state.discovered.length === 1 ? ' luogo scoperto' : ' luoghi scoperti');
}
function renderLocation() {
  const loc = locationById(selectedLocation);
  if (!loc) return;
  $('#location-detail').replaceChildren(el('span',{class:'location-icon'},icon('pin')),el('div',{class:'location-copy'},el('h3',{},loc.name),el('p',{},loc.description)),el('button',{onclick:()=>prepareAction((loc.actions || [])[0] || 'Vorrei esplorare ' + loc.name + '.')},loc.id === state.location_id ? 'Esplora il luogo ↗' : 'Proponi il viaggio ↗'));
}
function focusAction() {
  $('#action-input').focus({preventScroll:true});
  $('#action-form').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
}
function prepareAction(text, actor = {}) {
  if (actor.actorName || actor.actorId) {
    const name=actor.actorName || state.party.find(member=>member.id===actor.actorId)?.name;
    if (name && !/^[^:\n]{1,80}\s*:\s*/.test(text)) text=name+': '+text;
    $('#action-speaker').value='none';
  }
  $('#action-input').value = text;
  renderActionAdvice();
  focusAction();
  toast('Puoi modificare l’azione, poi prepararla per la chat.');
}
function renderTableViews() {
  const shown=presentationState();
  const options={state:shown,world,status:tableStatus,onIntent:prepareAction,onSelectCharacter:selectCharacter};
  window.DndEncounter?.render({...options,host:$('#encounter-content')});
  const battleLayout=$('#encounter-content .encounter-layout');
  const battleMain=$('#encounter-content .encounter-main');
  const tacticalRegion=$('#tactical-region');
  if(battleLayout && battleMain && tacticalRegion && tacticalRegion.parentElement!==battleLayout) battleLayout.insertBefore(tacticalRegion,battleMain);
  window.DndAdventure?.render({...options,mode:'scena',host:$('#scene-view-content')});
  window.DndAdventure?.render({...options,mode:'diario',host:$('#adventure-journal')});
  window.DndTactical?.render({...options,host:$('#tactical-board')});
  window.DndTactical?.render({...options,host:$('#scene-interactions')});
  window.DndImmersion?.render({...options,host:$('#knowledge-content')});
  window.DndImmersion?.mountAtmosphere({...options,host:$('#atmosphere-controls')});
  window.DndImmersion?.mountArtwork({...options,host:$('#scene-artwork')});
  window.DndTableTools?.renderTurn({host:$('#turn-assist'),state:shown,following:followingTurn,onFollow:setFollowTurn});
  window.DndTableTools?.renderEffects({...options,host:$('#table-effects')});
  window.DndTableTools?.renderChest({...options,host:$('#party-chest')});
}
function renderActionAdvice() {
  if(!state)return;
  const speaker=$('#action-speaker').value;
  window.DndTableTools?.renderAdvice({host:$('#action-advice'),state,draft:$('#action-input').value,speakerId:speaker==='active'?viewCharacter()?.id:null});
}
function renderMiniCharacter() {
  const character = viewCharacter();
  if (!character) {
    $('#mini-character').replaceChildren(el('p',{class:'overline gold'},'IL VOSTRO GRUPPO'),el('h3',{},'Chi varcherà la soglia?'),el('p',{},'Create '+(state.party_size || 1)+' avventurieri. Ognuno avrà la propria scheda.'),el('button',{class:'primary-button',onclick:()=>showView('personaggio')},'Crea il gruppo',icon('arrow')));
    return;
  }
  const percent = character.max_hp > 0 ? Math.max(0, Math.min(100, 100 * character.hp / character.max_hp)) : 0;
  const hpFill = el('div'); hpFill.style.width = percent + '%';
  $('#mini-character').replaceChildren(el('div',{class:'mini-char-head'},el('span',{class:'char-emblem'},character.name.slice(0,1)),el('div',{},el('h3',{},character.name),el('p',{},character.class + ' · Livello ' + character.level)),el('button',{'aria-label':'Apri scheda personaggio',onclick:()=>showView('personaggio')},'↗')),el('div',{class:'hp-line'},el('span',{},'PUNTI FERITA'),el('strong',{},character.hp + ' / ' + character.max_hp)),el('div',{class:'hp-track',role:'meter','aria-label':'Punti ferita','aria-valuemin':0,'aria-valuemax':character.max_hp,'aria-valuenow':character.hp},hpFill),el('div',{class:'mini-stats'},el('span',{},'CA ',el('strong',{},character.ac)),el('span',{},'VELOCITÀ ',el('strong',{},character.speed + ' m')),el('span',{},'ORO ',el('strong',{},character.gold))));
  if ((state.party || []).length < (state.party_size || 1)) $('#mini-character').append(el('button',{class:'primary-button',onclick:()=>showView('personaggio')},'Completa il gruppo · '+state.party.length+'/'+state.party_size));
  else if ((state.party || []).length > 1) $('#mini-character').append(partyRoster(true));
}
async function selectCharacter(id) {
  followingTurn=false;
  try { localStorage.setItem('dnd-follow-turn','false'); } catch { /* Preference remains local. */ }
  if (id === state.active_character_id) {render(state,true);return;}
  try { const result = await api('active-character',{character_id:id}); render(result.state); }
  catch(error) { toast(error.message,true); }
}
function partyRoster(compact = false) {
  const party = state.party || (state.character ? [state.character] : []);
  return el('div',{class:compact ? 'party-roster compact' : 'party-roster','aria-label':'Seleziona il personaggio attivo'},...party.map(character=>el('button',{class:'party-member'+(character.id===viewCharacter()?.id?' active':''),'aria-pressed':String(character.id===viewCharacter()?.id),onclick:()=>selectCharacter(character.id)},el('span',{class:'party-initial'},character.name.slice(0,1)),el('span',{},el('strong',{},character.name),el('small',{},character.class+' · '+character.hp+'/'+character.max_hp+' PF')))));
}
function renderCharacter() {
  const party = state.party || (state.character ? [state.character] : []);
  const targetSize = state.party_size || 1;
  const key = JSON.stringify({party,active:viewCharacter()?.id,character:viewCharacter(),world:world.id,targetSize,editing:editingCharacterId,canEdit:characterOptions?.can_edit_characters});
  if (key === characterRenderKey) return;
  characterRenderKey = key;
  const host = $('#character-content');
  if (party.length < targetSize || editingCharacterId) {
    renderCharacterSetup(host,party,targetSize);
    return;
  }
  const c = viewCharacter();
  const abilities = Object.entries(abilityNames).map(([key,name]) => el('div',{class:'ability-box reference-ability-box'},
    referenceButton('rule',name,abilityShort[key],{stat:{type:'ability',key,name,score:c.abilities[key],bonus:modifier(c.abilities[key])}},c),
    el('button',{type:'button',class:'reference-ability-roll',title:'Prepara un tiro di '+name,'aria-label':'Prepara un tiro di '+name,
      onclick:()=>openDice('1d20'+signed(modifier(c.abilities[key])),name)},el('strong',{},signed(modifier(c.abilities[key]))),el('small',{},c.abilities[key]))));
  const skills = Object.entries(skillNames).map(([key,label]) => {
    const bonus=c.skills[key] ?? modifier(c.abilities[skillAbilities[key]]);
    return statRow(label,bonus,{type:'skill',key,name:label,bonus,ability:abilityNames[skillAbilities[key]]},c);
  });
  const spellNames=[...(c.spells?.cantrips || []),...(c.spells?.known || []),...(c.spells?.prepared || [])].map(name=>name.split('·')[0].trim().toLocaleLowerCase('it'));
  const attacks = c.attacks.map(attack => {
    const kind=spellNames.includes(attack.name.split('·')[0].trim().toLocaleLowerCase('it')) ? 'spell' : 'weapon';
    return el('div',{class:'reference-attack-row'},
      el('div',{class:'reference-attack-details'},referenceButton(kind,attack.name,attack.name,{attack,referenceGroup:'attacks'},c),el('small',{},'Danni '+attack.damage)),
      el('button',{type:'button',class:'attack-button reference-roll-button',title:'Prepara il tiro per colpire con '+attack.name,
        'aria-label':'Prepara il tiro per colpire con '+attack.name,onclick:()=>openDice('1d20'+signed(attack.bonus),'Attacco · '+attack.name)},el('strong',{},signed(attack.bonus)+' ↗')));
  });
  const description = el('p',{class:'char-description'},c.description);
  const speciesInfo=characterOptions?.species?.find(species=>species.id===c.species_id || species.name===c.species);
  const classInfo=characterOptions?.classes?.find(entry=>entry.id===c.class_id || entry.name===c.class);
  const paper=el('section',{class:'paper-panel'},
    el('div',{class:'sheet-heading'},el('div',{},el('p',{class:'overline gold'},'LA TUA SCHEDA'),el('h2',{},c.name),
      el('p',{},referenceButton('feature',c.species,c.species,{description:speciesInfo?.description || ''},c),' · ',
        referenceButton('feature',c.class,c.class,{description:classInfo?.description || ''},c))),
      el('div',{class:'sheet-level'},'LIVELLO',el('strong',{},c.level))),description,
    el('p',{class:'reference-sheet-hint'},'Tocca un nome per leggere le regole. Usa il bonus ↗ per preparare un tiro.'),
    el('div',{class:'ability-grid'},...abilities),
    el('div',{class:'sheet-metrics'},
      el('div',{},el('strong',{},c.hp+' / '+c.max_hp),referenceButton('rule','Punti ferita','PUNTI FERITA',{stat:{type:'metric',key:'hp',name:'Punti ferita',value:c.hp+' / '+c.max_hp}},c)),
      el('div',{},el('strong',{},c.ac),referenceButton('rule','Classe armatura','CLASSE ARMATURA',{stat:{type:'metric',key:'ac',name:'Classe armatura',value:c.ac}},c)),
      el('div',{},el('strong',{},c.speed+' m'),referenceButton('rule','Velocità','VELOCITÀ BASE',{stat:{type:'metric',key:'speed',name:'Velocità base',value:c.speed+' m'}},c))),
    el('h3',{class:'sheet-section-title'},'Abilità'),el('div',{class:'skill-grid'},...skills),
    el('h3',{class:'sheet-section-title'},'Attacchi'),...attacks);
  const resources=el('section',{class:'dark-panel'},el('p',{class:'overline gold'},'LE TUE RISORSE'),el('h2',{},'Talenti e riserve'),
    ...c.resources.map(resource=>el('div',{class:'resource'},el('span',{},referenceButton('feature',resource.id,resource.name,{resource},c)),el('strong',{},resource.current+' / '+resource.max))),
    el('p',{class:'muted'},'Il master aggiorna le risorse in base alle tue azioni e ai riposi.'));
  const equipment=el('section',{class:'dark-panel'},el('p',{class:'overline gold'},'NELLO ZAINO'),el('h2',{},'Equipaggiamento'),
    ...c.inventory.map(item=>el('div',{class:'inventory-item'},el('span',{},referenceButton('item',item.name,item.name,{item},c)),el('span',{},'× '+item.qty))),
    el('div',{class:'inventory-item'},el('span',{},referenceButton('rule','Monete d’oro','Monete d’oro',{stat:{type:'metric',key:'gold',name:'Monete d’oro',value:c.gold}},c)),el('span',{},c.gold)));
  host.replaceChildren(el('div',{class:'character-sheet'},paper,el('aside',{},resources,equipment)));
  if (party.length > 1) host.prepend(partyRoster());
  extendCharacterSheet(host,c);
}
function renderJournal() {
  $('#journal-entries').replaceChildren(...state.journal.slice().reverse().map(entry=>el('article',{class:'journal-entry'},el('small',{},timeText(entry.at) + (entry.kind === 'note' ? ' · APPUNTO' : '')),el('h3',{},entry.title),el('p',{},entry.text))));
  $('#quest-list').replaceChildren(...state.quests.map(quest=>el('article',{class:'quest-item'},el('span',{class:'quest-status'},({active:'IN CORSO',completed:'COMPLETATO',failed:'CONCLUSO',paused:'IN SOSPESO'})[quest.status] || quest.status),el('h3',{},quest.title),el('p',{},quest.description))));
}
function renderPending() {
  const actions = state.pending_actions;
  $('#pending-label').textContent = actions.length ? actions.length + (actions.length === 1 ? ' azione in attesa del master.' : ' azioni in attesa del master.') : 'Potete sempre scegliere una strada diversa.';
  $('#pending-actions').replaceChildren(...(actions.length ? [el('details',{id:'pending-details'},el('summary',{},'Azioni preparate · inviale nella chat'),el('ol',{},...actions.map(action=>el('li',{},action.text))))] : []));
}
function renderCombat() {
  const combat = state.combat;
  $('#combat-panel').hidden = !combat.active;
  if (!combat.active) return;
  $('#combat-panel').replaceChildren(el('p',{class:'overline gold'},'INIZIATIVA'),el('h3',{},'Combattimento · round ' + combat.round),...combat.participants.flatMap((participant,index)=>participant.hidden ? [] : [
    el('div',{class:'combatant'+(index===combat.turn_index?' current':'')},
      el('span',{},(index===combat.turn_index?'▸ ':'')+participant.name,
        ...(participant.conditions?.length ? [el('span',{class:'reference-combat-conditions'},...participant.conditions.map(condition=>referenceButton('condition',condition,condition,{referenceGroup:participant.id},null)))] : [])),
      el('span',{},participant.hp === undefined ? '' : participant.hp+' PF'))]));
}
function renderRolls() {
  $('#recent-rolls').replaceChildren(...(state.rolls.length ? state.rolls.slice(-6).reverse().map(roll=>el('div',{class:'roll-entry'},el('span',{},roll.label || 'Tiro libero',el('small',{},roll.expression+' · '+timeText(roll.at))),el('strong',{},roll.total))) : [el('p',{class:'empty-message'},'Nessun tiro, per ora.')]));
}
function openDice(expression, label) {
  diceActorName=viewCharacter()?.name || '';
  $('#dice-actor').textContent=diceActorName ? 'Tiro di '+diceActorName : 'Tiro libero';
  if (expression) $('#dice-expression').value = expression;
  if (label !== undefined) $('#dice-label').value = label;
  $('#dice-mode').value = 'normal';
  highlightDie();
  if (!$('#dice-dialog').open) $('#dice-dialog').showModal();
}
function highlightDie() { document.querySelectorAll('#dice-presets button').forEach(button=>button.classList.toggle('selected',button.dataset.expression===$('#dice-expression').value)); }
function setZoom(value) { zoom = Math.min(2, Math.max(1,value)); $('#map-transform').setAttribute('transform',`translate(500 340) scale(${zoom}) translate(-500 -340)`); $('#zoom-out').disabled = zoom === 1; $('#zoom-in').disabled = zoom === 2; }
async function copyText(text) {
  $('#copy-fallback')?.remove();
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const active=document.activeElement, input=el('textarea',{class:'clipboard-helper','aria-label':'Testo da copiare'},text);
    document.body.append(input); input.select();
    let copied=false;
    try { copied=document.execCommand('copy'); } catch { /* Manual copy remains available. */ }
    input.remove(); active?.focus({preventScroll:true});
    if (!copied) { $('#copy-fallback')?.remove(); const field=el('textarea',{id:'copy-fallback',readonly:true,rows:3,'aria-label':'Messaggio da copiare manualmente'},text); $('#action-form').append(field); field.focus(); field.select(); }
    return copied;
  }
}
async function exportSave() {
  try {
    const response = await fetch('/api/export',{cache:'no-store'});
    if (!response.ok) throw new Error('Esportazione non riuscita.');
    const url = URL.createObjectURL(await response.blob());
    const link = el('a',{href:url,download:state.campaign_id+'-sessione-'+state.session+'-rev-'+state.revision+'.json'});
    document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Copia del salvataggio esportata.');
  } catch(error) { toast(error.message,true); }
}
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    const table = await api('table'), next=table.state;
    if (state && next.campaign_id===state.campaign_id && next.revision<state.revision) return;
    const campaignChanged=Boolean(state && next.campaign_id!==state.campaign_id);
    if (!characterOptions || !tableConnected || campaignChanged) await loadCharacterOptions();
    const metadataKey=JSON.stringify(table.world), worldChanged=metadataKey!==worldRenderKey;
    tableStatus=table.status;
    const editChanged=characterOptions.can_edit_characters!==table.status.can_edit_characters;
    characterOptions.can_edit_characters=table.status.can_edit_characters;
    if (campaignChanged) { characterRenderKey=''; selectedLocation=null; editingCharacterId=null; builderDraft=null; }
    if (worldChanged) { world=table.world; worldRenderKey=metadataKey; applyWorldMetadata(); }
    render(next,worldChanged || editChanged); renderTableStatus(); setConnected(true); $('#load-error').hidden = true;
    if(selectedView==='guida' && !$('#performance-panel').contains(document.activeElement)) window.DndTableTools?.renderMetrics({host:$('#performance-panel')});
  } catch(error) {
    setConnected(false); $('#load-error').hidden=false;
    $('#load-error').textContent=(state ? 'La partita è al sicuro. ' : '')+error.message+' Riaprite AVVIA.cmd: questa pagina si ricollega automaticamente.';
  }
  finally { polling = false; }
}
function applyWorldMetadata() {
  const brand = world.brand || 'IL TAVOLO';
  $('.brand>span').firstChild.textContent = brand;
  $('.brand').setAttribute('aria-label',brand + ', torna all’atlante');
  $('#map-heading').textContent = world.region || 'Mappa della campagna';
  const topDiamond = $('.topbar-diamond');
  if (topDiamond) topDiamond.nextSibling.textContent = ' CRONACHE DI ' + brand + ' ';
  $('.page-footer>span:first-child').replaceChildren(brand+' ',el('span',{},'✧'),' LA TUA STORIA COMINCIA QUI');
  if (world.map_asset && /^\/assets\/[a-z0-9-]+\.svg$/.test(world.map_asset)) $('#map-transform image').setAttribute('href',world.map_asset);
  const source=world.source || {}, overview=world.overview || {};
  const sourceLink=$('#campaign-source-link');
  sourceLink.textContent=source.title || world.title;
  if (typeof source.url==='string' && /^https?:\/\//i.test(source.url)) sourceLink.setAttribute('href',source.url);
  else sourceLink.removeAttribute('href');
  const guide=source.guide || [overview.format,overview.levels ? 'Livelli '+overview.levels+'.' : '',overview.sessions_estimate,overview.status].filter(Boolean).join(' ');
  $('#campaign-source-description').textContent=guide ? ' · '+guide : '';
  $('#campaign-rules-description').textContent=overview.rules || 'Usiamo le regole del SRD 5.1 (D&D 5e 2014), con le integrazioni dichiarate in REGOLE.md. Il PDF originale della campagna rimane riservato al master per evitare anticipazioni.';
  $('#campaign-map-description').textContent=overview.map_note || 'La carta della plancia è uno schema originale con distanze indicative. I luoghi si svelano durante il viaggio; le posizioni sono riferimenti, non limiti alle vostre azioni.';
}

document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
$('.brand').addEventListener('click',()=>showView('atlante'));
window.addEventListener('hashchange',()=>showView(location.hash.slice(1)));
$('#dice-open').addEventListener('click',()=>openDice());
$('.close-dialog').addEventListener('click',()=>$('#dice-dialog').close());
$('#dice-dialog').addEventListener('click',event=>{ if (event.target === $('#dice-dialog')) { const bounds=event.target.getBoundingClientRect(); if (event.clientX<bounds.left || event.clientX>bounds.right || event.clientY<bounds.top || event.clientY>bounds.bottom) event.target.close(); } });
$('#dice-presets').replaceChildren(...[4,6,8,10,12,20,100].map(sides=>el('button',{type:'button','data-expression':'1d'+sides,onclick:()=>{$('#dice-expression').value='1d'+sides; highlightDie();}},'d'+sides)));
$('#dice-expression').addEventListener('input',highlightDie);
$('#zoom-in').addEventListener('click',()=>setZoom(zoom+.25));
$('#zoom-out').addEventListener('click',()=>setZoom(zoom-.25));
$('#zoom-reset').addEventListener('click',()=>setZoom(1));
$('#grid-toggle').addEventListener('click',()=>{ const show = $('#grid-layer').hasAttribute('hidden'); $('#grid-layer').toggleAttribute('hidden',!show); $('#grid-toggle').setAttribute('aria-pressed',String(show)); });
$('#action-form').addEventListener('submit',async event=>{
  event.preventDefault(); const rawText = $('#action-input').value.trim();
  if (!state) { toast('Attendete il collegamento al tavolo oppure scrivetemi direttamente in chat.',true); return; }
  if (!rawText) { $('#action-input').focus(); toast('Descrivi che cosa vuoi fare.',true); return; }
  const hasSpeaker = /^[^:\n]{1,80}\s*:\s*/.test(rawText);
  const speaker=$('#action-speaker').value;
  const prefix=speaker==='party' ? 'Tutti' : speaker==='active' ? viewCharacter()?.name : '';
  const text = prefix && !hasSpeaker ? prefix+': '+rawText : rawText;
  const button = $('#action-submit'); button.disabled = true;
  try {
    if (!state.pending_actions.some(action=>action.text===text)) { const result = await api('action',{text}); render(result.state); }
    const copied = await copyText(text);
    toast(copied ? 'Azione salvata e copiata. Incollala nella chat con il master.' : 'Azione salvata. Copia il testo selezionato e invialo nella chat.');
  } catch(error) { toast(error.message,true); } finally { button.disabled = false; }
});
$('#dice-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('#roll-button').disabled = true;
  try {
    const label = (diceActorName ? diceActorName+' · ' : '') + ($('#dice-label').value.trim() || 'Tiro libero');
    const result = await api('roll',{expression:$('#dice-expression').value.trim(),label:label.slice(0,120),mode:$('#dice-mode').value});
    render(result.state); const roll = result.roll;
    const modeText = {normal:'',advantage:' · vantaggio',disadvantage:' · svantaggio'}[roll.mode];
    $('#dice-result').replaceChildren(el('span',{},roll.total),el('p',{},roll.expression+modeText),el('p',{},'Dadi: '+roll.dice.join(', ')+' · tenuti: '+roll.kept.join(', ')+' · modificatore '+signed(roll.modifier)));
  } catch(error) { toast(error.message,true); } finally { $('#roll-button').disabled = false; }
});
$('#note-form').addEventListener('submit',async event=>{
  event.preventDefault(); const input=$('#note-input'), text=input.value.trim(); if (!text) return;
  const button = event.submitter || $('#note-form button'); button.disabled=true;
  try { const result=await api('note',{text}); render(result.state); if(input.value.trim()===text) input.value=''; toast('Appunto aggiunto al diario.'); } catch(error) { toast(error.message,true); } finally { button.disabled=false; }
});
$('#export-button').addEventListener('click',exportSave); $('#export-button-2').addEventListener('click',exportSave);
$('#import-open').addEventListener('click',()=>$('#import-file').click());
$('#import-file').addEventListener('change',async()=>{
  const file=$('#import-file').files[0]; $('#import-file').value=''; if (!file) return;
  try { if (file.size>524288) throw new Error('Il salvataggio supera la dimensione consentita (512 KB).'); importCandidate=JSON.parse(await file.text()); if (importCandidate?.state) importCandidate=importCandidate.state; if (!importCandidate || typeof importCandidate!=='object' || importCandidate.campaign_id!==state.campaign_id) throw new Error('Questa copia appartiene a un’altra campagna o non è un salvataggio valido.'); importRevision=state.revision; $('#confirm-dialog').showModal(); }
  catch(error) { importCandidate=null; toast(error instanceof SyntaxError ? 'Il file non contiene un salvataggio JSON valido.' : error.message,true); }
});
$('#import-cancel').addEventListener('click',()=>{importCandidate=null;$('#confirm-dialog').close();});
$('#confirm-dialog').addEventListener('cancel',()=>{importCandidate=null;});
$('#import-confirm').addEventListener('click',async()=>{
  if (!importCandidate) return; const button=$('#import-confirm'); button.disabled=true;
  try { const result=await api('import',{state:importCandidate,expected_revision:importRevision}); render(result.state); importCandidate=null; $('#confirm-dialog').close(); toast('Salvataggio ripristinato. La copia precedente è in saves/.'); }
  catch(error) { if(error.status===409) {importCandidate=null;$('#confirm-dialog').close();await refresh();toast('Il tavolo è cambiato mentre confermavate. Riaprite la copia per scegliere se ripristinarla sullo stato aggiornato.',true);} else toast(error.message,true); } finally { button.disabled=false; }
});

// One composer for every play view: navigating never discards its draft.
$('#table-action-dock').append($('.action-panel'));
const tableContext=el('div',{class:'table-context-bar'},$('.world-bar'),$('#atmosphere-options'));
$('#table-status').after(tableContext);
document.addEventListener('click',event=>{const options=$('#atmosphere-options');if(options.open && !options.contains(event.target))options.open=false;});
document.addEventListener('keydown',event=>{const options=$('#atmosphere-options');if(event.key==='Escape' && options.open){options.open=false;options.querySelector('summary').focus({preventScroll:true});}});
$('#action-jump').addEventListener('click',focusAction);
$('.skip-link').addEventListener('click',event=>{event.preventDefault();const view=$('#view-'+selectedView);view.setAttribute('tabindex','-1');view.focus({preventScroll:true});view.scrollIntoView({block:'start',behavior:'auto'});});
if('IntersectionObserver' in window)new IntersectionObserver(entries=>{actionDockVisible=entries[0].isIntersecting;$('#action-jump').hidden=selectedView==='guida' || actionDockVisible;},{threshold:.2}).observe($('#table-action-dock'));
// The battlefield gets its own column; it is never squeezed inside the actions.
const tacticalRegion=el('details',{id:'tactical-region',class:'tactical-region'},
  el('summary',{},'Campo di battaglia'),$('#tactical-board'),$('#table-effects'));
tacticalRegion.open=true;
$('#view-combattimento').append(tacticalRegion);
const actionAdvice=el('div',{id:'action-advice',class:'turn-advice',role:'status',hidden:true});
$('#action-input').after(actionAdvice);
$('#action-input').addEventListener('input',renderActionAdvice);
$('#action-speaker').addEventListener('change',renderActionAdvice);
const diary=$('#view-diario'), journalTools=diary.querySelector('.journal-layout');
diary.prepend(el('div',{id:'adventure-journal'}));
journalTools.classList.add('journal-tools');
journalTools.querySelector('.paper-panel').hidden=true;
$('#quest-list').closest('section').hidden=true;
const cartographyGuide=el('section',{class:'reference-guide'},el('h3',{},'Le carte del tavolo'),
  el('p',{},'Apri le mappe condivise e i dungeon dimostrativi, ingrandiscili e scaricali. Le bozze sono separate dalla partita; i luoghi ancora sconosciuti restano al master.'),
  el('a',{href:'/maps.html',target:'_blank',rel:'noopener',class:'outline-button'},'Apri la cartoteca ↗'));
$('#view-guida .guide').insertBefore(cartographyGuide,$('#view-guida .attribution'));
const artworkGuide=el('section',{class:'reference-guide'},el('h3',{},'Illustrazioni d’atmosfera'),
  el('p',{},'Accampamenti, strade e luoghi da immaginare: sfoglia le illustrazioni originali del tavolo, guardale da vicino e scaricale. Il racconto del master definisce la scena giocata.'),
  el('a',{href:'/artworks.html',target:'_blank',rel:'noopener',class:'outline-button'},'Galleria delle illustrazioni ↗'));
$('#view-guida .guide').insertBefore(artworkGuide,$('#view-guida .attribution'));
(async()=>{
  showView(location.hash.slice(1)); setZoom(1);
  if (!['http:','https:'].includes(location.protocol)) { setConnected(false); $('#load-error').hidden=false; $('#load-error').textContent='Apri AVVIA.cmd nella cartella dnd: la plancia ha bisogno del suo server locale.'; return; }
  setInterval(refresh,2000);
  window.addEventListener('online',refresh);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden) refresh();});
  await refresh();
})();
