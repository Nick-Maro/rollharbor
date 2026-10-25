'use strict';

let characterOptions = null;
let editingCharacterId = null;
let builderDraft = null;
let editingCharacterBaseline = null;
const templateNames = new Map();

async function loadCharacterOptions() {
  try { characterOptions = await api('character-options'); }
  catch (error) { throw new Error('Il server deve essere aggiornato per la scelta delle classi. Chiudi con ARRESTA.cmd, riapri AVVIA.cmd e ricarica la pagina. ' + error.message); }
}

function classById(id) { return characterOptions?.classes.find(item => item.id === id); }
function speciesById(id) { return characterOptions?.species.find(item => item.id === id); }

function beginCharacterEdit(id) {
  const character = state.party.find(member => member.id === id);
  if (!character || !characterOptions?.can_edit_characters) return;
  editingCharacterId = id;
  editingCharacterBaseline = JSON.stringify(character);
  const creation = character.creation;
  const inferredClass = character.class_id || ({guerriero:'fighter',ladra:'rogue',maga:'wizard',chierico:'cleric'})[character.template_id] || 'fighter';
  const selectedClass = classById(creation?.class_id || inferredClass);
  builderDraft = {
    class_id:selectedClass?.id || '', species_id:creation?.species_id || character.species_id || 'human',
    name:character.name, abilities:{...(creation?.base_abilities || selectedClass?.recommended_abilities)},
    skills:[...(creation?.skills || selectedClass?.recommended_skills || [])],
    background_id:creation?.background_id || 'studente', description:creation?.description || '',
    expected_revision:state.revision
  };
  characterRenderKey = '';
  showView('personaggio');
  renderCharacter();
  $('#builder-name')?.focus({preventScroll:true});
}

function cancelCharacterEdit() {
  editingCharacterId = null; editingCharacterBaseline=null; builderDraft = null; characterRenderKey = ''; renderCharacter();
}

function characterSlots() {
  const members = state.party || [];
  return el('div',{class:'party-slots','aria-label':'I posti del vostro gruppo'},...Array.from({length:state.party_size},(_,index)=>{
    const member = members[index];
    const card = el('article',{class:'party-slot'+(member?' filled':' empty')},el('p',{class:'overline'},'GIOCATORE '+(index+1)),el('h3',{},member?.name || 'Un posto per la tua storia'),el('p',{},member ? member.class+' · '+member.species : 'Nome e classe li scegli tu.'));
    if (member) {
      card.append(el('span',{class:'slot-level'},'Livello '+member.level));
      if (characterOptions?.can_edit_characters) card.append(el('button',{type:'button',class:'quiet-button edit-character-button','data-character-id':member.id,onclick:()=>beginCharacterEdit(member.id)},'Modifica nome e classe ↗'));
    } else card.append(el('button',{type:'button',class:'quiet-button',onclick:()=>{ $('#builder-name')?.focus(); $('#builder-form')?.scrollIntoView({behavior:'smooth',block:'start'}); }},'Crea personaggio ↓'));
    return card;
  }));
}

function readyCharacterTemplates() {
  const details = el('details',{id:'ready-templates',class:'ready-templates'},el('summary',{},'Preferite partire subito? Apri i modelli pronti (facoltativi)'),el('p',{class:'builder-hint'},'Queste sono scorciatoie. Potete scegliere tutte le classi nel creatore e modificare le schede prima dell’inizio della storia.'));
  const templates = world.character_templates.map(template=>{
    const inputId = 'name-'+template.id;
    const input = el('input',{id:inputId,value:templateNames.get(template.id) ?? template.name,maxlength:80,'aria-label':'Nome del modello '+template.class,oninput:event=>templateNames.set(template.id,event.target.value)});
    const button = el('button',{class:'outline-button',type:'button',onclick:async()=>{
      if (!input.value.trim()) { input.focus(); return; }
      button.disabled=true;
      try {
        const result=await api('character',{template_id:template.id,name:input.value.trim(),expected_revision:state.revision});
        builderDraft=null;
        render(result.state);
        showView('personaggio');
        toast('Modello aggiunto. Puoi modificarne nome e classe prima di iniziare.');
      } catch(error) { toast(error.message,true); button.disabled=false; }
    }},'Usa questo modello');
    return el('article',{class:'template-card'},el('p',{class:'overline'},'MODELLO PRONTO · '+template.class.toUpperCase()),el('h3',{},template.name),el('p',{class:'template-description'},template.description),el('label',{for:inputId},'Nome del personaggio'),input,button);
  });
  details.append(el('div',{class:'character-templates'},...templates));
  return details;
}

function renderCharacterSetup(host, party, targetSize) {
  if (!characterOptions) {
    host.replaceChildren(el('div',{class:'error-panel'},'Caricamento delle classi in corso. Se non termina, riavvia AVVIA.cmd e ricarica la pagina.'));
    return;
  }
  const editing = party.find(member=>member.id===editingCharacterId);
  if (editingCharacterId && !editing) { editingCharacterId=null; editingCharacterBaseline=null; builderDraft=null; }
  if (!builderDraft) builderDraft={name:'',class_id:'',species_id:'human',background_id:'studente',abilities:{str:15,dex:14,con:13,int:12,wis:10,cha:8},skills:[],description:''};
  const draft = builderDraft;
  const nameInput = el('input',{id:'builder-name',name:'name',value:draft.name,placeholder:'Il nome che scegli tu',maxlength:80,required:true,autocomplete:'off',oninput:event=>{draft.name=event.target.value;}});
  const classSelect = el('select',{id:'builder-class',name:'class_id',required:true},el('option',{value:''},'Scegli una classe…'),...characterOptions.classes.map(item=>el('option',{value:item.id},item.name)));
  classSelect.value=draft.class_id;
  const speciesSelect=el('select',{id:'builder-species',name:'species_id'},...characterOptions.species.map(item=>el('option',{value:item.id},item.name)));
  speciesSelect.value=draft.species_id;
  const backgroundSelect=el('select',{id:'builder-background',name:'background_id'},...characterOptions.backgrounds.map(item=>el('option',{value:item.id},item.name)));
  backgroundSelect.value=draft.background_id;
  if (!backgroundSelect.value) { backgroundSelect.selectedIndex=0; draft.background_id=backgroundSelect.value; }
  const concept=el('textarea',{id:'builder-description',name:'description',rows:3,maxlength:2000,placeholder:'Che tipo di persona è? Che cosa cerca in questa avventura?',oninput:event=>{draft.description=event.target.value;}},draft.description);
  const classInfo=el('section',{class:'builder-class-info','aria-live':'polite'});
  const speciesInfo=el('p',{class:'builder-hint'});
  const backgroundInfo=el('p',{class:'builder-hint'});
  const abilities=el('div',{class:'builder-abilities'});
  const skillCount=el('p',{id:'builder-skill-count',class:'builder-hint'});
  const skillGrid=el('div',{id:'builder-skill-grid',class:'builder-skills'});
  const preview=el('div',{class:'builder-preview','aria-live':'polite'});
  const errorBox=el('p',{id:'builder-error',class:'builder-error',role:'alert',hidden:true});
  const submit=el('button',{id:'builder-submit',type:'submit',class:'primary-button'},editing?'Salva le modifiche':'Aggiungi al gruppo',icon('arrow'));

  function updateSpecies() {
    const species=speciesById(draft.species_id);
    speciesInfo.textContent=species ? species.description+' · '+Object.entries(species.bonuses).map(([key,bonus])=>abilityShort[key]+' '+signed(bonus)).join(', ')+' · Velocità '+species.speed+' m' : '';
    updatePreview();
  }
  function updateBackground() {
    const background=characterOptions.backgrounds.find(item=>item.id===draft.background_id);
    backgroundInfo.textContent=background ? background.description+' · '+background.skills.map(key=>skillNames[key] || key).join(', ') : '';
  }
  function updatePreview() {
    const species=speciesById(draft.species_id);
    preview.replaceChildren(el('p',{class:'overline'},'CARATTERISTICHE FINALI · BONUS DELLA SPECIE INCLUSI'),el('div',{class:'builder-final-scores'},...Object.keys(abilityNames).map(key=>{
      const finalScore=Number(draft.abilities[key])+(species?.bonuses[key] || 0);
      return el('div',{},el('span',{},abilityShort[key]),el('strong',{},finalScore),el('small',{},signed(modifier(finalScore))));
    })),el('p',{class:'builder-hint'},'Punti ferita, armatura, attacchi e risorse saranno calcolati per la tua classe quando salvi.'));
  }
  function updateAbilityFields() {
    abilities.replaceChildren(...Object.entries(abilityNames).map(([key,label])=>{
      const select=el('select',{id:'builder-ability-'+key,'aria-label':'Punteggio base di '+label},...characterOptions.standard_array.map(score=>el('option',{value:score},score)));
      select.value=String(draft.abilities[key]);
      select.addEventListener('change',()=>{
        const previous=draft.abilities[key], next=Number(select.value);
        const other=Object.keys(draft.abilities).find(ability=>ability!==key && draft.abilities[ability]===next);
        if (other) draft.abilities[other]=previous;
        draft.abilities[key]=next;
        updateAbilityFields(); updatePreview();
        $('#builder-ability-'+key)?.focus({preventScroll:true});
      });
      return el('div',{},el('label',{for:select.id},label),select);
    }));
  }
  function updateSkills() {
    const selectedClass=classById(draft.class_id);
    const choices=selectedClass?.skill_choices || [];
    draft.skills=draft.skills.filter(key=>choices.includes(key));
    const count=selectedClass?.skill_count || 0;
    function updateCount() {
      skillCount.textContent=selectedClass ? 'Scegli '+count+' competenze di classe · '+draft.skills.length+'/'+count+' selezionate. Le competenze del passato si aggiungono automaticamente.' : 'Scegli prima una classe per vedere le competenze disponibili.';
      skillGrid.querySelectorAll('input').forEach(input=>{ input.disabled=!input.checked && draft.skills.length>=count; });
    }
    skillGrid.replaceChildren(...choices.map(key=>{
      const input=el('input',{type:'checkbox',value:key,name:'skills','aria-label':skillNames[key] || key});
      input.checked=draft.skills.includes(key);
      input.addEventListener('change',()=>{ draft.skills=input.checked?[...draft.skills,key]:draft.skills.filter(value=>value!==key); updateCount(); });
      return el('label',{class:'builder-skill'},input,el('span',{},skillNames[key] || key));
    }));
    updateCount();
  }
  function updateClass(recommend = false) {
    const selectedClass=classById(draft.class_id);
    if (selectedClass && recommend) {
      draft.abilities={...selectedClass.recommended_abilities};
      draft.skills=[...selectedClass.recommended_skills];
    }
    classInfo.replaceChildren(...(selectedClass ? [el('div',{class:'class-summary-title'},el('h3',{},selectedClass.name),el('span',{},'Dado vita d'+String(selectedClass.hit_die).replace(/^d/,''))),el('p',{},selectedClass.description),el('p',{class:'builder-hint'},'Caratteristiche principali: '+selectedClass.primary_abilities.map(key=>abilityNames[key]).join(', ')+'. Tiri salvezza: '+selectedClass.saving_throws.map(key=>abilityNames[key]).join(', ')+'.'),el('ul',{},...selectedClass.features.map(feature=>el('li',{},feature)))] : [el('h3',{},'Il personaggio nasce dalla tua scelta.'),el('p',{},'Scegli fra le dodici classi base. Non serve un gruppo con una classe per tipo: potete anche ripeterle.')]));
    updateAbilityFields(); updateSkills(); updatePreview();
  }
  classSelect.addEventListener('change',()=>{ draft.class_id=classSelect.value; updateClass(true); });
  speciesSelect.addEventListener('change',()=>{draft.species_id=speciesSelect.value;updateSpecies();});
  backgroundSelect.addEventListener('change',()=>{draft.background_id=backgroundSelect.value;updateBackground();});
  const resetScores=el('button',{class:'quiet-button',type:'button',onclick:()=>updateClass(true)},'Usa la distribuzione consigliata per questa classe ↺');
  const form=el('form',{id:'builder-form',class:'character-builder'},el('div',{class:'builder-title'},el('p',{class:'overline gold'},editing?'MODIFICA PRIMA DELL’AVVENTURA':'GIOCATORE '+(party.length+1)+' · CREA IL TUO PERSONAGGIO'),el('h2',{},editing?'La scelta è ancora tua.':'Chi vuoi interpretare?'),el('p',{class:'muted'},editing?'Le modifiche riguardano questa scheda. Gli altri personaggi e la scena restano conservati.':'Scegli nome, classe e specie. I valori consigliati ti aiutano a partire; puoi ridistribuirli.')),
    el('div',{class:'builder-top-fields'},el('div',{},el('label',{for:nameInput.id},'Nome del personaggio'),nameInput),el('div',{},el('label',{for:classSelect.id},'Classe'),classSelect),el('div',{},el('label',{for:speciesSelect.id},'Specie'),speciesSelect)),
    classInfo,speciesInfo,el('div',{class:'builder-section'},el('h3',{},'Caratteristiche'),el('p',{class:'builder-hint'},'Distribuisci 15, 14, 13, 12, 10 e 8. Cambiando un valore lo scambi con quello che lo occupava: ogni punteggio si usa una volta.'),abilities,resetScores,preview),
    el('div',{class:'builder-section'},el('h3',{},'Competenze'),skillCount,skillGrid),
    el('div',{class:'builder-section'},el('label',{for:backgroundSelect.id},'Passato del personaggio'),backgroundSelect,backgroundInfo,el('label',{for:concept.id},'Un’idea del personaggio · facoltativo'),concept),
    el('p',{class:'builder-hint'},'Partiamo al livello 1 con equipaggiamento e capacità iniziali SRD 5.1. Le scelte successive di magie, sottoclassi e crescita si concordano con il master. Per altre specie puoi chiedermelo in chat.'),errorBox,el('div',{class:'builder-actions'},editing?el('button',{id:'builder-cancel',type:'button',class:'outline-button',onclick:cancelCharacterEdit},'Annulla'):null,submit));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const selectedClass=classById(draft.class_id);
    errorBox.hidden=true;
    if (!selectedClass || draft.skills.length!==selectedClass.skill_count) {
      errorBox.hidden=false; errorBox.textContent='Scegli una classe e il numero indicato di competenze.'; return;
    }
    submit.disabled=true;
    const payload={class_id:draft.class_id,species_id:draft.species_id,name:draft.name.trim(),abilities:{...draft.abilities},skills:[...draft.skills],background_id:draft.background_id,description:draft.description.trim(),expected_revision:state.revision};
    try {
      if (editing) {
        const current=await api('table');
        if (!current.status.can_edit_characters) throw new Error('La partita è iniziata. La bozza resta qui: concordiamo le modifiche in chat.');
        const latest=current.state.party.find(member=>member.id===editing.id);
        if (JSON.stringify(latest)!==editingCharacterBaseline) throw new Error('Questa scheda è stata aggiornata mentre la modificavi. La tua bozza resta qui: annulla per leggere gli aggiornamenti e poi riapri la modifica.');
        Object.assign(payload,{character_id:editing.id,expected_revision:current.state.revision});
      }
      const result=await api(editing?'character-rebuild':'character',payload);
      editingCharacterId=null; editingCharacterBaseline=null; builderDraft=null;
      characterRenderKey=''; render(result.state,true); showView('personaggio');
      toast(editing?'Personaggio aggiornato.':'Personaggio creato. '+(result.state.party.length===targetSize?'Il gruppo è pronto!':'Ora tocca al prossimo giocatore.'));
    } catch(error) { const message=error.status===409 ? 'Il tavolo si è aggiornato. La bozza è conservata: riprova a salvare.' : error.message; errorBox.hidden=false; errorBox.textContent=message; toast(message,true); submit.disabled=false; }
  });
  host.replaceChildren(el('div',{class:'character-intro'},el('p',{class:'overline gold'},'IL VOSTRO GRUPPO · '+party.length+' / '+targetSize),el('h2',{},'Quattro giocatori, personaggi scelti da voi.'),el('p',{},'I quattro posti sono per i giocatori. Nomi, classi e personalità non sono già decisi.')),characterSlots(),form,...(!editing && party.length<targetSize ? [readyCharacterTemplates()] : []));
  updateClass(); updateSpecies(); updateBackground();
}

function extendCharacterSheet(host, character) {
  if (characterOptions?.can_edit_characters) host.prepend(el('div',{class:'sheet-edit-bar'},el('p',{},'Prima di iniziare potete ancora cambiare nome, classe e specie.'),el('button',{type:'button',class:'outline-button edit-character-button','data-character-id':character.id,onclick:()=>beginCharacterEdit(character.id)},'Modifica personaggio')));
  const paper=host.querySelector('.paper-panel');
  const sidebar=host.querySelector('.character-sheet>aside');
  if (Number.isInteger(character.xp)) {
    const thresholds=[0,0,300,900,2700,6500,14000,23000,34000,48000,64000,85000,100000,120000,140000,165000,195000,225000,265000,305000,355000];
    const next=thresholds[character.level+1];
    const panel=el('section',{class:'sheet-xp-panel','aria-label':'Esperienza del personaggio'},el('strong',{},character.xp.toLocaleString('it-IT')+' PE'),el('span',{},next ? 'Livello '+(character.level+1)+' a '+next.toLocaleString('it-IT')+' PE' : 'Livello massimo'));
    if (next && character.xp>=next) panel.append(el('p',{},'Soglia raggiunta: scegliamo insieme in chat come cresce il personaggio.'));
    paper.querySelector('.sheet-metrics').after(panel);
  }
  if (character.conditions?.length || character.temporary_hp || character.hp===0) {
    const conditionNames={blinded:'Accecato',charmed:'Affascinato',deafened:'Assordato',frightened:'Spaventato',grappled:'Afferrato',incapacitated:'Incapacitato',invisible:'Invisibile',paralyzed:'Paralizzato',petrified:'Pietrificato',poisoned:'Avvelenato',prone:'Prono',restrained:'Trattenuto',stunned:'Stordito',unconscious:'Privo di sensi',exhaustion:'Indebolimento'};
    const conditionPanel=el('section',{class:'sheet-condition-panel','aria-label':'Condizioni del personaggio'},el('h3',{},'Stato attuale'));
    if (character.conditions?.length) conditionPanel.append(el('div',{class:'reference-condition-list'},...character.conditions.map(condition=>referenceButton('condition',condition,conditionNames[condition] || condition,{},character))));
    if (character.temporary_hp) conditionPanel.append(el('p',{},referenceButton('rule','Punti ferita temporanei',character.temporary_hp+' punti ferita temporanei',{stat:{type:'metric',key:'temporary_hp',name:'Punti ferita temporanei',value:character.temporary_hp}},character)));
    if (character.hp===0 && character.death_saves) conditionPanel.append(el('p',{},referenceButton('rule','Tiri salvezza contro morte','Tiri contro morte · '+character.death_saves.successes+' successi · '+character.death_saves.failures+' fallimenti',{stat:{type:'metric',key:'death_saves',name:'Tiri salvezza contro morte',value:character.death_saves.successes+' successi, '+character.death_saves.failures+' fallimenti'}},character)));
    paper.querySelector('.char-description').after(conditionPanel);
  }
  host.querySelectorAll('.resource').forEach((node,index)=>{
    const reset=({short:'Riposo breve o lungo',long:'Riposo lungo',dawn:'All’alba'})[character.resources[index].reset];
    if (reset) { node.title='Recupero: '+reset; node.querySelector('span').append(el('small',{class:'resource-reset'},reset)); }
  });
  if (character.saving_throws) paper.append(el('h3',{class:'sheet-section-title'},'Tiri salvezza'),el('div',{class:'skill-grid'},...Object.entries(abilityNames).map(([key,label])=>statRow('TS '+label,character.saving_throws[key],{type:'save',key,name:label,bonus:character.saving_throws[key],ability:label},character,'TS '+label))));
  const chosenTemplate=world?.character_templates?.find(template=>template.id===character.template_id && template.class===character.class && template.level===character.level);
  const features=character.features?.length ? character.features : chosenTemplate?.features || [];
  if (features.length) paper.append(el('h3',{class:'sheet-section-title'},'Capacità e tratti'),el('ul',{class:'sheet-features'},...features.map(feature=>el('li',{},referenceButton('feature',feature,feature,{description:feature},character)))));
  const spells=character.spells;
  if (spells && (spells.cantrips.length || spells.known.length || spells.prepared.length)) {
    const spellPanel=el('section',{class:'dark-panel spell-panel'},el('p',{class:'overline gold'},'LA TUA MAGIA'),el('h2',{},'Incantesimi'),el('p',{},'CD '+spells.dc+' · Attacco '+signed(spells.attack_bonus)));
    for (const [key,title] of [['cantrips','Trucchetti'],['known','Conosciuti / nel libro'],['prepared','Preparati']]) {
      if (spells[key].length) spellPanel.append(el('h3',{},title),el('div',{class:'reference-spell-list'},...spells[key].map(name=>referenceButton('spell',name,name,{referenceGroup:key},character))));
    }
    spellPanel.append(el('p',{class:'muted'},spells.notes || 'Il master verifica componenti, bersagli e risorse.'));
    sidebar.append(spellPanel);
  }
  const training=character.proficiencies;
  if (training) sidebar.append(el('section',{class:'dark-panel training-panel'},el('p',{class:'overline gold'},'LA TUA FORMAZIONE'),el('h2',{},'Competenze e lingue'),...Object.entries({armor:'Armature',weapons:'Armi',tools:'Strumenti',languages:'Lingue'}).flatMap(([key,label])=>Array.isArray(training[key]) && training[key].length ? [el('h3',{},label),el('div',{class:'reference-training-list'},...training[key].map(name=>referenceButton(key==='armor'?'armor':key==='weapons'?'weapon':'rule',name,name,{referenceGroup:'training-'+key,description:'Competenza conosciuta da '+character.name+': '+name},character)))] : [])));
}
