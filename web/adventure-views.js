'use strict';

// Public, read-only adventure views. A suggestion only prepares a chat message.
// No fetch, game mutation, dice, inferred NPC identity, or hidden campaign data.
(() => {
  const sessions = new WeakMap();
  const list = value => Array.isArray(value) ? value : [];
  const text = value => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const signed = value => Number(value) >= 0 ? '+' + value : String(value);
  const normalize = value => text(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('it');

  function node(tag, className, content, attrs = {}) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined && content !== null) element.textContent = text(content);
    for (const [key, value] of Object.entries(attrs)) {
      if (value !== undefined && value !== null) element.setAttribute(key, String(value));
    }
    return element;
  }

  function append(parent, ...children) {
    children.flat(Infinity).filter(Boolean).forEach(child => parent.append(child));
    return parent;
  }

  function label(value) { return node('p', 'av-kicker', value); }
  function empty(value) { return node('p', 'av-empty', value); }
  function paragraphs(value, className = 'av-prose') {
    const root = node('div', className);
    text(value).split(/\n\s*\n/).filter(Boolean).forEach(part => root.append(node('p', '', part)));
    return root;
  }

  function panel(kicker, title, className = '') {
    return append(node('section', 'av-panel ' + className), label(kicker), node('h3', '', title));
  }

  function localId(session, name) {
    return 'adventure-' + session.uid + '-' + name;
  }

  function reference(session, kind, name, character = null, context = {}) {
    if (!window.DndReference?.button) return node('span', '', name);
    const result = window.DndReference.button({kind, name, label:name, character, context});
    let hash = 2166136261;
    for (const letter of [kind, character?.id, name].join('|')) hash = Math.imul(hash ^ letter.charCodeAt(0), 16777619);
    const base = (hash >>> 0).toString(36);
    const occurrence = session.referenceCounts.get(base) || 0;
    session.referenceCounts.set(base, occurrence + 1);
    result.id = localId(session, base + (occurrence ? '-' + occurrence : ''));
    return result;
  }

  function intent(session, title, message = title, className = '') {
    const button = node('button', 'av-intent ' + className, title, {type:'button'});
    button.disabled = typeof session.args.onIntent !== 'function';
    button.addEventListener('click', () => session.args.onIntent?.(message));
    return button;
  }

  function selectedCharacter(state) {
    return list(state.party).find(member => member.id === state.active_character_id) || state.character || null;
  }

  function knownLocations(state, world) {
    const discovered = new Set(list(state.discovered));
    const byId = new Map(list(world.locations).map(place => [place.id, place]));
    list(state.flags?.public_locations).forEach(place => byId.set(place.id, place));
    return [...byId.values()].filter(place => discovered.has(place.id));
  }

  function currentLocation(state, world) {
    return knownLocations(state, world).find(place => place.id === state.location_id) || null;
  }

  function conditions(session, values, character = null) {
    const host = node('div', 'av-conditions');
    list(values).filter(value => typeof value === 'string').forEach(value => {
      const chip = node('span', 'av-condition');
      chip.append(reference(session, 'condition', value, character));
      host.append(chip);
    });
    return host;
  }

  function partyPanel(session) {
    const {state} = session.args;
    const party = list(state.party);
    const host = panel('AVVENTURIERI', 'Il gruppo, adesso', 'av-party-panel');
    host.append(node('p', 'av-small', 'Selezionate una scheda per consultarne strumenti e risorse.'));
    if (!party.length) { host.append(empty('I personaggi compariranno dopo la creazione del gruppo.')); return host; }
    const grid = node('div', 'av-party-grid');
    party.forEach(character => {
      const card = node('article', 'av-party-card' + (character.id === state.active_character_id ? ' is-selected' : ''));
      const select = node('button', 'av-party-select', undefined, {
        type:'button', 'aria-pressed':String(character.id === state.active_character_id),
        'aria-label':'Seleziona la scheda di ' + text(character.name),
        id:localId(session, 'select-' + character.id)
      });
      select.disabled = typeof session.args.onSelectCharacter !== 'function';
      select.addEventListener('click', () => session.args.onSelectCharacter?.(character.id));
      append(select, node('span', 'av-party-initial', text(character.name).slice(0, 1) || '◇'),
        append(node('span', 'av-party-identity'), node('strong', '', character.name),
          node('small', '', [character.class, character.level ? 'Livello ' + character.level : ''].filter(Boolean).join(' · '))));
      const max = Number(character.max_hp), hp = Number(character.hp);
      const metrics = node('div', 'av-party-metrics');
      append(metrics, node('span', '', Number.isFinite(hp) && Number.isFinite(max) ? hp + '/' + max + ' PF' : 'PF non registrati'),
        node('span', '', character.ac !== undefined ? 'CA ' + character.ac : ''));
      append(card, select, metrics);
      if (max > 0 && Number.isFinite(hp)) {
        const meter = node('div', 'av-health', undefined, {
          role:'meter', 'aria-label':'Punti ferita di ' + character.name,
          'aria-valuemin':0, 'aria-valuemax':max, 'aria-valuenow':Math.max(0, Math.min(max, hp))
        });
        const fill = node('span', hp / max <= 0.3 ? 'is-low' : '');
        fill.style.width = Math.max(0, Math.min(100, 100 * hp / max)) + '%';
        meter.append(fill);
        card.append(meter);
      }
      card.append(conditions(session, character.conditions, character));
      grid.append(card);
    });
    host.append(grid);
    return host;
  }

  function toolkit(session) {
    const character = selectedCharacter(session.args.state);
    const host = panel('A PORTATA DI MANO', character ? 'Gli strumenti di ' + character.name : 'Strumenti del gruppo');
    if (!character) { host.append(empty('Scegliete un personaggio per consultarne la scheda.')); return host; }
    const resourceList = list(character.resources);
    const spells = [...new Set([...list(character.spells?.cantrips), ...list(character.spells?.prepared), ...list(character.spells?.known)])];
    const inventory = list(character.inventory).filter(item => Number(item.qty) > 0);
    const tools = inventory.filter(item => /torcia|lanterna|corda|razione|otre|pozione|acciarino|attrezzi|strumenti|kit|simbolo|focus|grimorio/i.test(item.name || ''));
    const usefulSkills = [['perception','Percezione'], ['investigation','Indagare'], ['insight','Intuizione'], ['persuasion','Persuasione'], ['stealth','Furtività'], ['survival','Sopravvivenza']];
    const skills = usefulSkills.filter(([key]) => Number.isFinite(character.skills?.[key]));
    if (skills.length) {
      host.append(node('h4', 'av-subtitle', 'Abilità utili'));
      const grid = node('div', 'av-skill-list');
      skills.forEach(([key, name]) => {
        const bonus = character.skills[key];
        append(grid, append(node('div', 'av-detail-row'),
          reference(session, 'rule', name, character, {stat:{type:'skill',key,name,bonus}}), node('strong', '', signed(bonus))));
      });
      host.append(grid);
    }
    if (resourceList.length) {
      host.append(node('h4', 'av-subtitle', 'Riserve'));
      resourceList.forEach(resource => host.append(append(node('div', 'av-detail-row'),
        reference(session, 'feature', resource.name || resource.id, character, {resource}),
        node('span', '', text(resource.current) + '/' + text(resource.max)))));
    }
    if (tools.length) {
      host.append(node('h4', 'av-subtitle', 'Nello zaino'));
      tools.slice(0, 8).forEach(item => host.append(append(node('div', 'av-detail-row'),
        reference(session, 'item', item.name, character, {item}), node('span', '', '× ' + item.qty))));
    }
    if (spells.length) {
      host.append(node('h4', 'av-subtitle', 'Magie della scheda'));
      const chips = node('div', 'av-reference-list');
      spells.forEach(name => chips.append(reference(session, 'spell', name, character)));
      host.append(chips);
    }
    if (!skills.length && !resourceList.length && !tools.length && !spells.length) host.append(empty('Gli oggetti e le capacità sono consultabili nella scheda del personaggio.'));
    host.append(node('p', 'av-small av-bottom-hint', 'Toccate un nome per leggere le regole. La consultazione non consuma risorse.'));
    return host;
  }

  function scenePanel(session) {
    const {state, world} = session.args;
    const place = currentLocation(state, world);
    const scene = state.scene || {};
    const host = panel('IL MASTER RACCONTA', scene.title || 'La scena attuale', 'av-scene-panel av-paper');
    const meta = [place?.name, state.clock?.day ? 'Giorno ' + state.clock.day : '', state.clock?.time].filter(Boolean).join(' · ');
    if (meta) host.append(node('p', 'av-scene-meta', meta));
    host.append(paragraphs(scene.text || 'La descrizione della scena comparirà qui quando il master la aggiorna.'));
    if (state.combat?.active) {
      const current = list(state.combat.participants)[Number(state.combat.turn_index)];
      const banner = node('div', 'av-combat-notice');
      append(banner, node('strong', '', 'Combattimento · Round ' + (state.combat.round || 1)),
        node('span', '', current ? 'La parola è a ' + current.name + '.' : 'Seguite l’ordine di iniziativa.'),
        node('small', '', 'Anche parlare, ritirarsi o inventare un piano sono possibilità da descrivere al master.'));
      host.append(banner);
    }
    return host;
  }

  function contacts(session) {
    const {state} = session.args;
    const partyIds = new Set(list(state.party).map(member => member.id));
    const battleFigures = state.combat?.active ? list(state.combat.participants).filter(person => !partyIds.has(person.id)) : [];
    const explicitContacts = [...list(state.contacts), ...list(state.flags?.public_contacts)].filter(contact => contact && typeof contact === 'object' && contact.name && !contact.hidden);
    const entries = new Map(explicitContacts.map(contact => [contact.id || contact.name, contact]));
    battleFigures.forEach(person => entries.set(person.id || person.name, {...entries.get(person.id || person.name), ...person, inCurrentCombat:true}));
    const host = panel('VOLTI CONOSCIUTI', battleFigures.length ? 'Figure percepite nello scontro' : 'Persone annotate');
    if (!entries.size) {
      append(host, empty('Nessun contatto è ancora annotato qui. Potete chiedere in chat chi vedete o con chi parlare.'),
        intent(session, 'Chiedi chi è presente', 'Chi vediamo qui e con chi possiamo parlare?'));
      return host;
    }
    for (const contact of entries.values()) {
      const card = node('article', 'av-contact');
      append(card, node('h4', '', contact.name));
      if (contact.description) card.append(node('p', 'av-small', contact.description));
      card.append(conditions(session, contact.conditions));
      // A known contact is not necessarily in the same location.
      if (contact.inCurrentCombat || contact.location_id === state.location_id || contact.present === true) {
        const unableToRespond = list(contact.conditions).some(value => /privo di sensi|incosciente|morto/i.test(text(value)));
        if (!unableToRespond) card.append(intent(session, 'Prova a parlare con ' + contact.name, 'Cerco di parlare con ' + contact.name + '.'));
      }
      host.append(card);
    }
    return host;
  }

  function suggestions(session) {
    const {state, world} = session.args;
    const mode = session.sceneMode;
    const host = panel('LE VOSTRE POSSIBILITÀ', mode === 'dialogo' ? 'La parola a voi' : 'Guardarsi intorno');
    host.append(node('p', 'av-small', 'Sono spunti: potete descrivere qualsiasi altra idea nella chat con il master.'));
    const choices = mode === 'dialogo' ? [
      ['Fai una domanda', 'Vorrei fare una domanda a chi ho davanti.'],
      ['Cerca un accordo', 'Cerco un accordo: vorrei spiegare la mia proposta.'],
      ['Ascolta e osserva', 'Ascolto quello che viene detto e osservo il comportamento di chi parla.'],
      ['Descrivi le tue parole', 'Vorrei dire queste parole: ']
    ] : [
      ['Osserva la scena', 'Osservo con attenzione ciò che mi circonda.'],
      ['Esamina un dettaglio', 'Vorrei esaminare un dettaglio della scena: '],
      ['Ascolta', 'Mi fermo e ascolto i suoni intorno a noi.'],
      ['Usa un oggetto', 'Vorrei usare un oggetto del mio inventario: ']
    ];
    const grid = node('div', 'av-intent-grid');
    choices.forEach(([title, message]) => grid.append(intent(session, title, message)));
    host.append(grid);
    const sceneChoices = list(state.scene?.choices).filter(value => typeof value === 'string');
    const placeChoices = mode !== 'dialogo' ? list(currentLocation(state, world)?.actions).filter(value => typeof value === 'string') : [];
    const extra = [...new Set([...sceneChoices, ...placeChoices])].slice(0, 7);
    if (extra.length) {
      host.append(node('h4', 'av-subtitle', 'Spunti della scena e del luogo'));
      const listHost = node('div', 'av-suggestions');
      extra.forEach(choice => listHost.append(intent(session, choice, choice)));
      host.append(listHost);
    }
    return host;
  }

  function recentNarration(session) {
    const entries = list(session.args.state.journal).filter(entry => ['master', 'story', 'scene'].includes(entry.kind) && text(entry.text));
    const host = panel('ULTIMI SVILUPPI', 'Quello che è appena successo');
    const meaningful = entries.slice(-4).reverse();
    if (!meaningful.length) host.append(empty('Le conseguenze descritte dal master compariranno nel diario di viaggio.'));
    meaningful.forEach(entry => host.append(append(node('article', 'av-recent-event'), node('p', '', entry.text))));
    return host;
  }

  function renderScene(session) {
    const root = node('div', 'av-root av-scene-view');
    const heading = node('div', 'av-view-heading');
    append(heading, append(node('div'), label('OLTRE LA MAPPA'), node('h2', '', 'Dentro l’avventura'),
      node('p', 'av-small', 'La scena, il gruppo e le vostre idee per il prossimo passo.')));
    const tabs = node('div', 'av-mode-switch', undefined, {role:'group','aria-label':'Scegli gli spunti da consultare'});
    [['esplorazione', 'Esplorare'], ['dialogo', 'Parlare']].forEach(([value, title]) => {
      const button = node('button', session.sceneMode === value ? 'is-active' : '', title, {
        type:'button','aria-pressed':String(session.sceneMode === value),id:localId(session, 'mode-' + value)
      });
      button.addEventListener('click', () => { session.sceneMode = value; paint(session); });
      tabs.append(button);
    });
    heading.append(tabs);
    const columns = node('div', 'av-columns');
    const main = node('div', 'av-main-column');
    const aside = node('aside', 'av-side-column', undefined, {'aria-label':'Risorse e persone conosciute'});
    append(main, scenePanel(session), partyPanel(session), suggestions(session));
    append(aside, session.sceneMode === 'dialogo' ? contacts(session) : toolkit(session),
      session.sceneMode === 'dialogo' ? toolkit(session) : recentNarration(session));
    append(columns, main, aside);
    return append(root, heading, columns);
  }

  function formatTime(value) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleString('it-IT', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  }

  function questPanel(session) {
    const host = panel('OBIETTIVI ANNOTATI', 'Fili aperti e conseguenze');
    const quests = list(session.args.state.quests);
    if (!quests.length) host.append(empty('Nessun incarico è ancora annotato. Potete definire i vostri obiettivi parlando con il master.'));
    const statuses = {active:'In corso', completed:'Completato', failed:'Non riuscito', paused:'In sospeso'};
    quests.forEach(quest => {
      const card = node('article', 'av-quest');
      append(card, node('span', 'av-quest-status', statuses[quest.status] || text(quest.status)),
        node('h4', '', quest.title || 'Obiettivo'), paragraphs(quest.description, 'av-small'));
      if (quest.status === 'active') card.append(intent(session, 'Parla di questo obiettivo', 'Vorrei fare il punto su «' + text(quest.title) + '».'));
      host.append(card);
    });
    return host;
  }

  function knownPlacesPanel(session) {
    const {state, world} = session.args;
    const host = panel('LA VOSTRA GEOGRAFIA', 'Luoghi conosciuti');
    const places = knownLocations(state, world);
    if (!places.length) host.append(empty('I luoghi conosciuti verranno annotati durante l’avventura.'));
    places.forEach(place => {
      const card = node('article', 'av-known-place');
      append(card, node('h4', '', place.name), node('span', 'av-place-status', place.id === state.location_id ? 'Posizione del gruppo' : 'Luogo conosciuto'));
      if (place.description) card.append(node('p', 'av-small', place.description));
      card.append(intent(session, place.id === state.location_id ? 'Esplora qui' : 'Proponi il viaggio',
        place.id === state.location_id ? 'Vorrei esplorare il luogo in cui ci troviamo.' : 'Vorrei organizzare un viaggio verso ' + text(place.name) + '.'));
      host.append(card);
    });
    return host;
  }

  function renderDiary(session) {
    const root = node('div', 'av-root av-diary-view');
    const heading = append(node('div', 'av-view-heading'), append(node('div'), label('MEMORIA DEL GRUPPO'),
      node('h2', '', 'La vostra storia'), node('p', 'av-small', 'Ritrovate scene, decisioni, appunti e obiettivi già annotati.')));
    const columns = node('div', 'av-columns');
    const main = panel('IL DIARIO CONDIVISO', 'Tracce del viaggio', 'av-paper');
    const toolbar = node('div', 'av-journal-toolbar');
    const searchLabel = node('label', 'av-search-label', 'Cerca nel diario', {for:localId(session, 'journal-search')});
    const search = node('input', 'av-journal-search', undefined, {
      id:localId(session, 'journal-search'),type:'search',placeholder:'Un nome, una scelta, un luogo…',maxlength:200
    });
    search.value = session.query;
    const filterLabel = node('label', 'av-search-label', 'Mostra', {for:localId(session, 'journal-filter')});
    const filter = node('select', 'av-journal-filter', undefined, {id:localId(session, 'journal-filter')});
    [['all','Tutto il diario'],['story','Racconto del master'],['note','Appunti'],['character','Personaggi']].forEach(([value,title]) => filter.append(node('option', '', title, {value})));
    filter.value = session.journalFilter;
    const searchField = append(node('div', 'av-search-field'), searchLabel, search);
    const filterField = append(node('div', 'av-filter-field'), filterLabel, filter);
    append(toolbar, searchField, filterField);
    const count = node('p', 'av-result-count', '', {role:'status','aria-live':'polite'});
    const timeline = node('div', 'av-timeline');
    const fill = () => {
      const query = normalize(session.query);
      const entries = list(session.args.state.journal).filter(entry => {
        const kindMatches = session.journalFilter === 'all' || (session.journalFilter === 'story' ? ['story','master','scene'].includes(entry.kind) : entry.kind === session.journalFilter);
        return kindMatches && (!query || normalize([entry.title, entry.text].join(' ')).includes(query));
      }).slice().reverse();
      count.textContent = entries.length + (entries.length === 1 ? ' voce trovata' : ' voci trovate');
      timeline.replaceChildren();
      if (!entries.length) timeline.append(empty(query || session.journalFilter !== 'all' ? 'Nessuna voce corrisponde alla ricerca.' : 'Il vostro diario comincerà con i primi eventi della partita.'));
      entries.forEach(entry => {
        const article = node('article', 'av-timeline-entry');
        const categories = {note:'Appunto',master:'Master',story:'Storia',scene:'Scena',character:'Personaggio'};
        append(article, node('p', 'av-entry-meta', [formatTime(entry.at), categories[entry.kind] || 'Diario'].filter(Boolean).join(' · ')),
          node('h4', '', entry.title || 'Dal diario'), paragraphs(entry.text, 'av-entry-text'));
        timeline.append(article);
      });
    };
    search.addEventListener('input', () => { session.query = search.value; fill(); });
    filter.addEventListener('change', () => { session.journalFilter = filter.value; fill(); });
    append(main, toolbar, count, timeline);
    fill();
    const aside = node('aside', 'av-side-column', undefined, {'aria-label':'Obiettivi e luoghi conosciuti'});
    append(aside, questPanel(session), knownPlacesPanel(session));
    append(columns, main, aside);
    return append(root, heading, columns);
  }

  function paint(session) {
    const {host} = session.args;
    session.referenceCounts = new Map();
    const active = document.activeElement;
    const focusId = host.contains(active) ? active.id : '';
    const selection = active && typeof active.selectionStart === 'number' ? [active.selectionStart, active.selectionEnd] : null;
    host.replaceChildren(session.mode === 'diario' ? renderDiary(session) : renderScene(session));
    if (focusId) {
      const replacement = document.getElementById(focusId);
      replacement?.focus({preventScroll:true});
      if (selection && replacement?.setSelectionRange) {
        try { replacement.setSelectionRange(...selection); } catch { /* Non-text fields have no text selection. */ }
      }
    }
  }

  let nextUid = 0;
  /**
   * render({mode, state, world, status, host, onIntent, onSelectCharacter})
   * mode: 'scena' | 'esplorazione' | 'dialogo' | 'diario'.
   * onIntent(text): prepare an editable chat message; never apply it automatically.
   * onSelectCharacter(id): use the app's existing character-selection handler.
   * No callbacks are required for read-only use. Returns the host element.
   */
  function render(args = {}) {
    const {host} = args;
    if (!host || typeof host.replaceChildren !== 'function') return null;
    const mode = args.mode === 'diario' ? 'diario' : 'scena';
    let session = sessions.get(host);
    if (!session) {
      session = {uid:++nextUid, args, mode, sceneMode:args.mode === 'dialogo' ? 'dialogo' : 'esplorazione', query:'', journalFilter:'all', key:null, requestedMode:args.mode};
      sessions.set(host, session);
    }
    if (session.requestedMode !== args.mode && ['esplorazione','dialogo'].includes(args.mode)) session.sceneMode = args.mode;
    session.requestedMode = args.mode;
    session.args = {...args,state:args.state || {},world:args.world || {}};
    session.mode = mode;
    const key = JSON.stringify([mode, args.mode, session.args.state, session.args.world,
      typeof args.onIntent === 'function', typeof args.onSelectCharacter === 'function']);
    if (key === session.key && host.firstChild) return host;
    session.key = key;
    paint(session);
    return host;
  }

  window.DndAdventure = Object.freeze({render});
})();
