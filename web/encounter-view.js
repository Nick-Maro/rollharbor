'use strict';

// This view reads the public table snapshot. Its buttons prepare intentions only.
(() => {
  const mounted = new WeakMap();
  const array = value => Array.isArray(value) ? value : [];
  const number = value => typeof value === 'number' && Number.isFinite(value);
  const signed = value => Number(value) >= 0 ? '+' + value : String(value);
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();

  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined && text !== null) result.textContent = String(text);
    return result;
  }
  function button(label, handler, className = 'encounter-button') {
    const result = node('button',className,label);
    result.type = 'button';
    result.addEventListener('click',handler);
    return result;
  }
  function reference(kind, name, character = null, context = {}) {
    return window.DndReference?.button({kind,name,label:name,character,context}) || node('span','',name);
  }
  function idFor(prefix, value) {
    let hash = 2166136261;
    for (const letter of String(value)) hash = Math.imul(hash ^ letter.charCodeAt(0),16777619);
    return 'encounter-' + prefix + '-' + (hash >>> 0).toString(36);
  }
  function conditions(values, character, owner) {
    const list = node('div','encounter-conditions');
    for (const condition of array(values)) {
      const item = reference('condition',condition,character,{referenceGroup:owner});
      item.id = idFor('condition',owner + '|' + condition);
      list.append(item);
    }
    return list;
  }
  function health(participant) {
    if (!number(participant.hp) || !number(participant.max_hp) || participant.max_hp <= 0) return null;
    const result = node('div','encounter-health');
    const label = node('span','encounter-health-label',participant.hp + ' / ' + participant.max_hp + ' PF');
    const meter = node('div','encounter-health-track');
    meter.setAttribute('role','meter');
    meter.setAttribute('aria-label','Punti ferita di ' + participant.name);
    meter.setAttribute('aria-valuemin','0');
    meter.setAttribute('aria-valuemax',String(participant.max_hp));
    meter.setAttribute('aria-valuenow',String(participant.hp));
    const fill = node('span',participant.hp <= participant.max_hp / 2 ? 'wounded' : '');
    fill.style.width = Math.max(0,Math.min(100,100 * participant.hp / participant.max_hp)) + '%';
    meter.append(fill);
    result.append(label,meter);
    return result;
  }
  function heading(kicker, title) {
    const result = node('header','encounter-section-heading');
    result.append(node('p','overline gold',kicker),node('h3','',title));
    return result;
  }
  function mount(host) {
    const frame = node('div','encounter-view');
    const hero = node('section','encounter-hero');
    const layout = node('div','encounter-layout');
    const initiative = node('section','encounter-panel encounter-initiative');
    const main = node('div','encounter-main');
    const actor = node('section','encounter-panel encounter-character');
    const scene = node('details','encounter-panel encounter-scene');
    const composer = node('section','encounter-panel encounter-composer');
    const recent = node('details','encounter-panel encounter-recent');
    scene.id='battle-scene-details';
    recent.id='battle-rolls-details';
    composer.append(heading('LA VOSTRA INTENZIONE','Ogni idea può diventare una mossa'));
    const label = node('label','encounter-field-label','Descrivi cosa vuoi tentare');
    label.htmlFor = 'encounter-intent';
    const input = node('textarea');
    input.id = 'encounter-intent';
    input.rows = 3;
    input.maxLength = 1900;
    input.placeholder = 'Attacchi, parli, ti sposti, usi il carro come copertura…';
    const tools = node('div','encounter-composer-actions');
    const notice = node('p','encounter-notice');
    notice.setAttribute('role','status');
    notice.setAttribute('aria-live','polite');
    const record = {frame,hero,initiative,actor,scene,composer,recent,input,notice,config:null,targetId:'',actorId:'',signatures:{}};
    const copy = button('Copia per la chat',async () => {
      const text = input.value.trim();
      if (!text) { input.focus(); notice.textContent = 'Descrivi prima la tua intenzione.'; return; }
      const c = currentCharacter(record.config.state);
      const message = (c?.name ? c.name + ': ' : '') + text;
      let copied = false;
      try { await navigator.clipboard.writeText(message); copied = true; } catch { /* Use the local fallback below. */ }
      if (!copied) {
        const helper = node('textarea','encounter-copy-helper',message);
        document.body.append(helper);
        helper.select();
        try { copied = document.execCommand('copy'); } catch { /* A visible field is the final fallback. */ }
        helper.remove();
      }
      if (copied) notice.textContent = 'Copiato. Incolla il messaggio nella chat con il master.';
      else {
        let fallback = composer.querySelector('.encounter-copy-fallback');
        if (!fallback) {
          fallback = node('textarea','encounter-copy-fallback');
          fallback.readOnly = true;
          fallback.rows = 3;
          fallback.setAttribute('aria-label','Messaggio completo da copiare manualmente');
          composer.append(fallback);
        }
        fallback.value = message;
        fallback.focus(); fallback.select();
        notice.textContent = 'Seleziona e copia il messaggio qui sotto, poi incollalo nella chat.';
      }
    },'primary-button');
    copy.id = 'encounter-copy';
    const prepare = button('Apri nel messaggio del tavolo',() => {
      const text = input.value.trim();
      if (!text) { input.focus(); return; }
      const c = currentCharacter(record.config.state);
      record.config.onIntent?.(text,{actorId:c?.id || null,actorName:c?.name || ''});
    },'outline-button');
    prepare.id = 'encounter-prepare';
    record.prepare = prepare;
    tools.append(copy,prepare);
    composer.append(label,input,tools,notice,node('p','encounter-fineprint','I pulsanti preparano una proposta. Il master risolve dadi, portata, risorse e conseguenze nella chat.'));
    main.append(actor,composer,scene,recent);
    layout.append(initiative,main);
    frame.append(hero,layout);
    host.replaceChildren(frame);
    if('ResizeObserver' in window) {
      record.resizeObserver=new ResizeObserver(()=>{
        const strip=initiative.querySelector('.encounter-initiative-list');
        const current=strip?.querySelector('.is-current');
        if(!strip || !current || !strip.clientWidth)return;
        const bounds=strip.getBoundingClientRect(),card=current.getBoundingClientRect();
        if(card.left<bounds.left || card.right>bounds.right) strip.scrollLeft+=card.left-bounds.left-5;
      });
      record.resizeObserver.observe(initiative);
    }
    mounted.set(host,record);
    return record;
  }
  function currentCharacter(state) {
    return array(state.party).find(c => c.id === state.active_character_id) || state.character || null;
  }
  function selectedTarget(record) {
    return array(record.config.state.combat?.participants).find(p => p.id === record.targetId);
  }
  function suggest(record, text) {
    if (typeof record.config.onIntent === 'function') {
      const c = currentCharacter(record.config.state);
      record.config.onIntent(text,{actorId:c?.id || null,actorName:c?.name || ''});
      return;
    }
    record.input.value = text;
    record.notice.textContent = 'Puoi cambiare il testo liberamente, poi copiarlo nella chat.';
    record.input.focus({preventScroll:true});
    record.composer.scrollIntoView({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',block:'nearest'});
  }
  function targetText(record, prefix = ' contro ') {
    const target = selectedTarget(record);
    return target ? prefix + target.name : '';
  }
  function renderHero(record) {
    const {state,world} = record.config;
    const combat = state.combat || {};
    const current = array(combat.participants)[combat.turn_index];
    const location = array(world?.locations).find(item => item.id === state.location_id);
    const copy = node('div','encounter-hero-copy');
    copy.append(node('p','overline gold',combat.active ? 'ROUND ' + combat.round + ' · COMBATTIMENTO' : 'PRONTI PER LA PROSSIMA SCENA'));
    copy.append(node('h2','',combat.active && current ? 'Tocca a ' + current.name : 'Il tavolo di combattimento'));
    copy.append(node('p','encounter-hero-subtitle',combat.active ? 'Scegli che cosa tentare. Puoi anche trattare, ritirarti o inventare un piano.' : 'Quando inizia uno scontro, qui trovi iniziativa, condizioni e le mosse dei tuoi personaggi.'));
    const meta = node('div','encounter-hero-meta');
    if (location) meta.append(node('span','encounter-location',location.name));
    meta.append(node('span','encounter-sync','Salvato · rev. ' + state.revision));
    const budget = node('div','encounter-turn-budget');
    const context = state.flags?.combat_context;
    const usage = context?.turn_usage;
    const reliable = combat.active && current && context?.awaiting_actor_id === current.id && usage?.actor_id === current.id;
    for (const [field,label] of [['action_used','Azione'],['bonus_action_used','Azione bonus']]) {
      const item = node('span','encounter-budget-item');
      item.append(reference('rule',label));
      if (reliable && typeof usage[field] === 'boolean') {
        item.classList.add(usage[field] ? 'spent' : 'unused');
        item.append(node('strong','',usage[field] ? 'Usata' : 'Non usata'));
      } else item.append(node('small','','Regole del turno'));
      budget.append(item);
    }
    const reaction = node('span','encounter-budget-item');
    reaction.append(reference('rule','Reazione'),node('small','','Se il suo innesco si verifica'));
    budget.append(reaction);
    record.hero.replaceChildren(copy,meta,budget,node('p','encounter-budget-note','Un’azione bonus richiede una capacità che la conceda. Il movimento dipende da terreno, condizioni e quanto già percorso.'));
  }
  function renderInitiative(record) {
    const {state,onSelectCharacter} = record.config;
    const combat = state.combat || {};
    const party = array(state.party);
    const participants = combat.active ? array(combat.participants) : party;
    const list = node('ol','encounter-initiative-list');
    list.setAttribute('aria-label',combat.active ? 'Ordine di iniziativa' : 'Personaggi del gruppo');
    participants.forEach((participant,index) => {
      const character = party.find(c => c.id === participant.id) || null;
      const current = Boolean(combat.active && index === combat.turn_index);
      const item = node('li','encounter-combatant' + (current ? ' is-current' : '') + (participant.id === state.active_character_id ? ' is-selected' : ''));
      if (current) item.setAttribute('aria-current','step');
      const score = node('span','encounter-initiative-score',combat.active ? participant.initiative : '—');
      score.setAttribute('aria-label',combat.active ? 'Iniziativa ' + participant.initiative : 'Fuori combattimento');
      const body = node('div','encounter-combatant-body');
      const name = node('strong','encounter-combatant-name',participant.name);
      name.title=participant.name;
      body.append(name,node('small','encounter-combatant-type',(current ? 'DI TURNO · ' : '') + (character ? character.class || 'PERSONAGGIO' : 'PNG')));
      const hp = health(participant);
      if (hp) body.append(hp);
      body.append(conditions(participant.conditions,character,participant.id));
      if (character && onSelectCharacter) {
        const select = button(participant.id === state.active_character_id ? 'Scheda selezionata' : 'Usa questa scheda',() => onSelectCharacter(participant.id),'encounter-select-character');
        select.id = idFor('select',participant.id);
        select.setAttribute('aria-pressed',String(participant.id === state.active_character_id));
        body.append(select);
      }
      item.append(score,body);
      list.append(item);
    });
    const previousScroll=record.initiative.querySelector('.encounter-initiative-list')?.scrollLeft || 0;
    record.initiative.replaceChildren(heading(combat.active ? 'ORDINE DI INIZIATIVA' : 'IL GRUPPO',combat.active ? 'A chi tocca' : 'Le vostre schede'),list);
    const currentId=participants[combat.turn_index]?.id;
    if(record.initiativeTurnId!==currentId) {
      const currentCard=list.querySelector('.is-current');
      if(currentCard)list.scrollLeft=Math.max(0,currentCard.offsetLeft-list.offsetLeft-5);
    } else list.scrollLeft=previousScroll;
    record.initiativeTurnId=currentId;
    if (!participants.length) record.initiative.append(node('p','encounter-empty','Crea il gruppo per preparare le vostre mosse.'));
    record.initiative.append(node('p','encounter-fineprint','Selezionare una scheda non cambia il turno.'));
  }
  function renderCharacter(record) {
    const {state} = record.config;
    const c = currentCharacter(state);
    const combat = state.combat || {};
    const current = array(combat.participants)[combat.turn_index];
    const targetLabel = node('label','encounter-field-label','Bersaglio o interlocutore, se serve');
    targetLabel.htmlFor = 'encounter-target';
    const target = node('select');
    target.id = 'encounter-target';
    const none = node('option','','Lo descrivo nel messaggio');
    none.value = '';
    target.append(none);
    for (const p of array(combat.participants).filter(p => p.id !== c?.id)) {
      const option = node('option','',p.name);
      option.value = p.id;
      target.append(option);
    }
    if (![...target.options].some(option => option.value === record.targetId)) record.targetId = '';
    target.value = record.targetId;
    target.addEventListener('change',() => { record.targetId = target.value; });
    const intro = node('div','encounter-actor-heading');
    intro.append(heading('SCHEDA SELEZIONATA',c?.name || 'Scegli un personaggio'));
    if (c) {
      const metrics = node('div','encounter-actor-metrics');
      metrics.append(node('span','',c.hp + '/' + c.max_hp + ' PF'),node('span','','CA ' + c.ac),node('span','','Velocità base ' + c.speed + ' m'));
      intro.append(metrics);
    }
    record.actor.replaceChildren(intro);
    if (!c) { record.actor.append(node('p','encounter-empty','Le azioni restano libere: racconta al master che cosa vuoi fare.')); return; }
    if (combat.active && current && c.id !== current.id) record.actor.append(node('p','encounter-selection-note','Sta agendo ' + current.name + '. Stai consultando la scheda di ' + c.name + '.'));
    record.actor.append(targetLabel,target);
    const actions = node('div','encounter-action-list');
    const spells = [...array(c.spells?.cantrips),...array(c.spells?.prepared),...array(c.spells?.known)];
    const spellKey = value => normalize(value).split(/[·:]/)[0].trim();
    for (const attack of array(c.attacks)) {
      const row = node('div','encounter-attack');
      const copy = node('div','encounter-attack-copy');
      const kind = spells.some(spell => spellKey(spell) === spellKey(attack.name)) ? 'spell' : 'weapon';
      const title = reference(kind,attack.name,c,{attack,referenceGroup:'encounter-attacks'});
      title.id = idFor('attack-reference',c.id + '|' + attack.name);
      copy.append(title,node('small','',signed(attack.bonus) + ' per colpire · ' + attack.damage + ' danni'));
      const prepare = button('Prepara',() => suggest(record,'Attacco' + targetText(record) + ' con ' + attack.name + '.'),'encounter-small-button');
      prepare.id = idFor('attack',c.id + '|' + attack.name);
      prepare.setAttribute('aria-label','Prepara un attacco con ' + attack.name);
      row.append(copy,prepare);
      actions.append(row);
    }
    if (actions.children.length) record.actor.append(node('h4','encounter-subheading','I tuoi attacchi'),actions);
    if (spells.length) {
      const spellList = node('div','encounter-spells');
      const unique = new Set();
      for (const spell of spells) {
        if (unique.has(spellKey(spell))) continue;
        unique.add(spellKey(spell));
        const row = node('div','encounter-spell');
        const inspect = reference('spell',spell,c,{referenceGroup:'encounter-spells'});
        inspect.id = idFor('spell-reference',c.id + '|' + spell);
        const prepare = button('Prepara',() => suggest(record,'Vorrei lanciare ' + spell + targetText(record,' su ') + '.'),'encounter-small-button');
        prepare.id = idFor('spell',c.id + '|' + spell);
        prepare.setAttribute('aria-label','Prepara ' + spell);
        row.append(inspect,prepare);
        spellList.append(row);
      }
      record.actor.append(node('h4','encounter-subheading','Le tue magie'),spellList);
    }
    if (array(c.resources).length) {
      const resources = node('div','encounter-resources');
      for (const resource of c.resources) {
        const item = node('span','encounter-resource');
        const inspect = reference('feature',resource.id || resource.name,c,{resource});
        // The catalog uses IDs to match resources, while the visible name stays readable.
        inspect.textContent = resource.name;
        inspect.id = idFor('resource',c.id + '|' + (resource.id || resource.name));
        item.append(inspect,node('strong','',resource.current + '/' + resource.max));
        resources.append(item);
      }
      record.actor.append(node('h4','encounter-subheading','Riserve dalla scheda'),resources);
    }
    const free = node('div','encounter-free-actions');
    const suggestions = [
      ['Parlare',() => 'Mi rivolgo' + targetText(record,' a ') + ' e dico: …'],
      ['Spostarmi',() => 'Vorrei spostarmi verso …, passando per …'],
      ['Schivare',() => 'Uso la mia azione per Schivare.'],
      ['Disimpegnarmi',() => 'Uso la mia azione per Disimpegnarmi e vorrei spostarmi verso …'],
      ['Aiutare',() => 'Vorrei aiutare … a …'],
      ['Spingere',() => 'Provo a spingere' + targetText(record,' ') + ' per …'],
      ['Usare un oggetto',() => 'Vorrei usare … per …'],
      ['Concludere il turno',() => 'Concludo il mio turno.']
    ];
    for (const [label,build] of suggestions) {
      const prepare = button(label,() => suggest(record,build()),'encounter-suggestion');
      prepare.id = idFor('suggestion',label);
      free.append(prepare);
    }
    record.actor.append(node('h4','encounter-subheading','Altre idee'),free,node('p','encounter-fineprint','Sono spunti modificabili. Portata, bersagli e prerequisiti si verificano quando dichiari la mossa.'));
  }
  function renderScene(record) {
    const scene = record.config.state.scene || {};
    const text = node('div','encounter-scene-text');
    for (const paragraph of String(scene.text || '').split(/\n\s*\n/).filter(Boolean)) text.append(node('p','',paragraph));
    record.scene.replaceChildren(node('summary','encounter-details-summary','La situazione · '+(scene.title || 'La scena attuale')),text);
    const choices = node('div','encounter-scene-choices');
    array(scene.choices).forEach((choice,index) => {
      const prepare = button(choice,() => suggest(record,choice),'encounter-suggestion');
      prepare.id = 'encounter-scene-choice-' + index;
      choices.append(prepare);
    });
    record.scene.append(choices);
  }
  function renderRecent(record) {
    const rolls = array(record.config.state.rolls).slice(-4).reverse();
    const list = node('div','encounter-rolls');
    for (const roll of rolls) {
      const item = node('article','encounter-roll');
      const copy = node('div');
      copy.append(node('span','',roll.label || 'Tiro pubblico'),node('small','',roll.expression + (array(roll.dice).length ? ' · dadi ' + roll.dice.join(', ') : '')));
      item.append(copy,node('strong','',roll.total));
      list.append(item);
    }
    record.recent.replaceChildren(node('summary','encounter-details-summary','Ultimi tiri · '+rolls.length),list);
    if (!rolls.length) record.recent.append(node('p','encounter-empty','I prossimi tiri pubblici compariranno qui.'));
  }
  function render(config) {
    if (!config?.host || !config.state) return;
    const record = mounted.get(config.host) || mount(config.host);
    record.config = config;
    record.composer.hidden = typeof config.onIntent === 'function';
    record.prepare.hidden = typeof config.onIntent !== 'function';
    renderHero(record);
    renderInitiative(record);
    renderCharacter(record);
    renderScene(record);
    renderRecent(record);
  }
  window.DndEncounter = {render};
})();
