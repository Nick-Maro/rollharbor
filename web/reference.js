'use strict';

// Player-facing rules only. Opening a card never rolls dice or changes a save.
(() => {
  const kindNames = {
    item:'Equipaggiamento', weapon:'Arma', armor:'Armatura', spell:'Incantesimo',
    feature:'Capacità', resource:'Risorsa', condition:'Condizione', rule:'Regola'
  };
  const abilityNames = {str:'Forza',dex:'Destrezza',con:'Costituzione',int:'Intelligenza',wis:'Saggezza',cha:'Carisma'};
  const attached = new WeakMap();
  let settings = {getCharacter:() => null};
  let current = null;
  let previousFocus = null;
  let previousOverflow = '';

  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined && text !== null) result.textContent = String(text);
    return result;
  }
  function normalized(value) {
    return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toLowerCase().replace(/[’‘]/g, "'").replace(/[\s\u00a0]+/g, ' ').trim();
  }
  function baseName(value) {
    return normalized(value).split(/\s*[·•:]\s*|\s+\(/)[0].trim();
  }
  function entries() {
    return Array.isArray(window.DndRulesCatalog?.entries) ? window.DndRulesCatalog.entries : [];
  }
  function findEntry(request) {
    const desired = normalized(request.name);
    const base = baseName(request.name);
    const permitted = request.kind === 'item' ? ['item','weapon','armor'] :
      (request.kind === 'resource' || (request.kind === 'feature' && request.context?.resource)) ? ['resource','feature','rule'] :
      request.kind === 'condition' ? ['condition','rule'] : [request.kind];
    const candidates = entries().filter(entry => !request.kind || permitted.includes(entry.kind));
    const names = entry => [entry.id,entry.title,...(entry.aliases || [])].filter(Boolean).map(normalized);
    return candidates.find(entry => request.id && entry.id === request.id) ||
      candidates.find(entry => names(entry).includes(desired)) ||
      candidates.find(entry => names(entry).some(name => name === base || baseName(name) === base));
  }
  function characterFor(request) {
    if (request.character === null) return null;
    const id = request.characterId || request.character?.id;
    const recent = settings.getCharacter?.(id);
    if (recent && (!id || recent.id === id)) return recent;
    return request.character || null;
  }
  function matching(list, name) {
    return (Array.isArray(list) ? list : []).find(item =>
      normalized(item.name || item.id || item) === normalized(name) ||
      baseName(item.name || item.id || item) === baseName(name));
  }
  function signed(value) { return Number(value) >= 0 ? '+' + value : String(value); }
  function fact(label, value) {
    const row = node('div','reference-fact');
    row.append(node('dt','',label),node('dd','',value));
    return row;
  }
  function safeSource(source) {
    if (!source?.url) return null;
    try {
      const url = new URL(source.url);
      return ['https:','http:'].includes(url.protocol) ? url.href : null;
    } catch (_) { return null; }
  }
  function currentFacts(request, entry, character) {
    const result = [];
    if (!character) return result;
    const kind = request.kind || entry?.kind;
    const stat = request.context?.stat;
    if (stat) {
      const key = stat.key || stat.ability || stat.name;
      if (stat.type === 'ability') {
        const score = character.abilities?.[key] ?? stat.score;
        const bonus = Number.isFinite(score) ? Math.floor((score - 10) / 2) : stat.bonus;
        if (score !== undefined) result.push(['Punteggio',score]);
        if (bonus !== undefined) result.push(['Modificatore',signed(bonus)]);
      } else if (stat.type === 'skill' || stat.type === 'save') {
        const bonus = stat.type === 'skill' ? (character.skills?.[key] ?? stat.bonus) : (character.saving_throws?.[key] ?? stat.bonus);
        if (bonus !== undefined) result.push(['Bonus della scheda',signed(bonus)]);
      } else {
        const metrics = {
          hp:character.hp + ' / ' + character.max_hp,
          ac:character.ac,speed:character.speed + ' m',gold:character.gold,
          temp:character.temporary_hp || 0,
          death_saves:character.death_saves ? character.death_saves.successes + ' successi, ' + character.death_saves.failures + ' fallimenti' : '0 successi, 0 fallimenti'
        };
        const value = metrics[stat.key] ?? stat.value;
        if (value !== undefined) result.push([stat.name || 'Valore della scheda',value]);
      }
    }
    const inventory = matching(character.inventory,request.name);
    const attack = matching(character.attacks,request.name);
    const resource = matching(character.resources,request.name) ||
      (request.context?.resource?.id && character.resources?.find(item => item.id === request.context.resource.id));
    if (inventory && ['item','armor','weapon'].includes(kind)) result.push(['Quantità nello zaino',inventory.qty]);
    if (attack && ['item','weapon','spell'].includes(kind)) {
      if (Number.isFinite(attack.bonus)) result.push(['Bonus di attacco della scheda',signed(attack.bonus)]);
      if (attack.damage) result.push(['Danni della scheda',attack.damage]);
    }
    if (kind === 'spell') {
      const spells = character.spells || {};
      const cantrip = matching(spells.cantrips,request.name);
      const prepared = matching(spells.prepared,request.name);
      const known = matching(spells.known,request.name);
      if (cantrip) result.push(['Nella tua scheda','Trucchetto: non consuma slot']);
      else if (prepared) result.push(['Nella tua scheda','Incantesimo preparato']);
      else if (known) result.push(['Nella tua scheda','Incantesimo conosciuto']);
      else result.push(['Nella tua scheda','Non elencato tra gli incantesimi di questo personaggio']);
      const racialInt = /messaggio|message/.test(baseName(request.name)) &&
        /elfo alto|intelligenza/i.test(String(cantrip || request.name));
      if (racialInt && Number.isFinite(character.abilities?.int) && Number.isFinite(character.proficiency)) {
        const modifier = Math.floor((character.abilities.int - 10) / 2);
        result.push(['Caratteristica magica','Intelligenza'],['CD del tiro salvezza',8 + character.proficiency + modifier]);
      } else {
        if (spells.ability) result.push(['Caratteristica magica',abilityNames[spells.ability] || spells.ability]);
        if (Number.isFinite(spells.dc)) result.push(['CD degli incantesimi',spells.dc]);
        if (!attack && Number.isFinite(spells.attack_bonus)) result.push(['Attacco magico (se richiesto)',signed(spells.attack_bonus)]);
      }
      if (!cantrip && entry?.mechanics?.level !== 0) {
        const slots = (character.resources || []).filter(item => /^(?:spell|pact)_slot_\d+$/.test(item.id));
        for (const slot of slots) result.push([slot.name,slot.current + ' / ' + slot.max]);
      }
      if (/^(parola guaritrice|healing word|cura ferite|cure wounds)$/.test(baseName(request.name)) && spells.ability && Number.isFinite(character.abilities?.[spells.ability])) {
        const modifier = Math.floor((character.abilities[spells.ability] - 10) / 2);
        const die = /parola guaritrice|healing word/.test(baseName(request.name)) ? '1d4' : '1d8';
        result.push(['Cura con slot di 1° livello',die + signed(modifier) + ' PF']);
      }
    }
    if (resource && ['resource','feature'].includes(kind)) {
      result.push(['Disponibili',resource.current + ' / ' + resource.max]);
      const resetNames = {short:'Riposo breve o lungo',long:'Riposo lungo'};
      if (resource.reset) result.push(['Recupero della scheda',resetNames[resource.reset] || resource.reset]);
    }
    if (kind === 'condition') {
      const has = matching(character.conditions,request.name);
      result.push(['Sulla tua scheda',has ? 'Condizione presente' : 'Condizione non presente']);
    }
    return result;
  }
  function renderLive(request, entry) {
    const host = document.getElementById('reference-live');
    if (!host) return;
    const character = characterFor(request);
    const rows = currentFacts(request,entry,character);
    host.hidden = !rows.length;
    const signature = JSON.stringify([character?.id,character?.name,rows]);
    if (host.dataset.signature === signature) return;
    host.dataset.signature = signature;
    const heading = node('h3','','Nella scheda di ' + (character?.name || 'questo personaggio'));
    const list = node('dl','reference-facts');
    for (const row of rows) list.append(fact(...row));
    host.replaceChildren(heading,list);
  }
  function sheetDescription(request, character) {
    if (request.context?.description) return request.context.description;
    if (request.kind === 'feature') return matching(character?.features,request.name) || null;
    if (request.context?.item?.description) return request.context.item.description;
    if (request.context?.attack?.description) return request.context.attack.description;
    return null;
  }
  function renderCard(request) {
    const entry = findEntry(request);
    const character = characterFor(request);
    const content = document.getElementById('reference-content');
    let fallbackTitle = request.context?.resource?.name || request.label || request.name || 'Dettagli';
    if (request.kind === 'feature') fallbackTitle = fallbackTitle.split(':')[0];
    if ([...fallbackTitle].length > 96) fallbackTitle = [...fallbackTitle].slice(0,95).join('') + '…';
    const displayTitle = entry?.title || fallbackTitle;
    document.getElementById('reference-title').textContent = displayTitle;
    document.getElementById('reference-kind').textContent =
      (kindNames[entry?.kind || request.kind] || 'Il manuale del tavolo') + ' · Regole 2014';
    const fragment = document.createDocumentFragment();
    if (entry?.summary) fragment.append(node('p','reference-summary',entry.summary));
    const live = node('section','reference-live');
    live.id = 'reference-live';
    live.hidden = true;
    fragment.append(live);
    if (entry?.facts?.length) {
      const list = node('dl','reference-facts reference-rules-facts');
      for (const row of entry.facts) list.append(fact(row.label,row.value));
      fragment.append(list);
    }
    if (entry?.details?.length) {
      const details = node('section','reference-details');
      details.append(node('h3','','Come funziona'));
      for (const paragraph of entry.details) details.append(node('p','',paragraph));
      fragment.append(details);
    }
    const description = sheetDescription(request,character);
    if (description) {
      const section = node('section','reference-sheet-note');
      section.append(node('h3','','Descrizione nella tua scheda'),node('p','',description));
      fragment.append(section);
    }
    if (!entry) {
      const fallback = node('section','reference-fallback');
      fallback.append(node('h3','','Dettagli da concordare al tavolo'),node('p','',
        'Questa voce non ha ancora una descrizione delle regole verificata nel manuale rapido. ' +
        'Qui trovi i dati disponibili nella scheda; chiedi al master gli altri dettagli.'));
      fragment.append(fallback);
    }
    const footer = node('footer','reference-footer');
    const sourceUrl = safeSource(entry?.source);
    if (sourceUrl) {
      const source = node('a','reference-source',entry.source.label || 'Leggi la regola nella fonte');
      source.href = sourceUrl;
      source.target = '_blank';
      source.rel = 'noopener noreferrer';
      footer.append(source);
    } else footer.append(node('p','reference-source-missing',entry?.source?.label || 'Fonte specifica non disponibile.'));
    footer.append(node('p','','Leggere questa scheda non usa oggetti, slot o azioni. Descrivi al master ciò che vuoi fare.'));
    const library = node('button','reference-library-link','Sfoglia il manuale rapido');
    library.type = 'button';
    library.dataset.referenceLibrary = 'true';
    footer.append(library);
    fragment.append(footer);
    content.replaceChildren(fragment);
    renderLive(request,entry);
  }
  function ensureOpen(trigger) {
    const dialog = document.getElementById('reference-dialog');
    if (!dialog.open) {
      previousFocus = trigger || document.activeElement;
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      dialog.showModal();
    }
    document.getElementById('reference-content').scrollTop = 0;
    document.getElementById('reference-close').focus({preventScroll:true});
  }
  function open(request = {}, trigger) {
    const character = request.character === null ? null : request.character || settings.getCharacter?.(request.characterId);
    current = {...request,character,characterId:request.characterId || character?.id,originId:trigger?.id};
    renderCard(current);
    ensureOpen(trigger);
  }
  function library(trigger) {
    current = null;
    document.getElementById('reference-title').textContent = 'Il manuale rapido';
    document.getElementById('reference-kind').textContent = 'OGGETTI, MAGIE E REGOLE · 2014';
    const content = document.getElementById('reference-content');
    const intro = node('p','reference-summary','Cerca una magia, un oggetto, una capacità o una condizione. La scheda del personaggio mostra le sue scelte e risorse attuali.');
    const label = node('label','reference-search-label','Cerca nel manuale');
    label.htmlFor = 'reference-search';
    const input = node('input','reference-search');
    input.type = 'search';
    input.id = 'reference-search';
    input.placeholder = 'Es. Intralciare, scimitarra, afferrato…';
    const results = node('div','reference-results');
    const count = node('p','reference-result-count');
    count.setAttribute('aria-live','polite');
    const fill = () => {
      const query = normalized(input.value);
      const found = entries().filter(entry => [entry.title,...(entry.aliases || []),kindNames[entry.kind]].some(value => normalized(value).includes(query)));
      count.textContent = found.length + (found.length === 1 ? ' voce' : ' voci');
      results.replaceChildren(...found.map(entry => {
        const result = button({kind:entry.kind,name:entry.title,id:entry.id});
        result.classList.add('reference-result');
        result.append(node('small','',kindNames[entry.kind] || 'Regola'));
        return result;
      }));
      if (!found.length) results.append(node('p','reference-empty','Nessuna voce trovata. Puoi chiedere al master anche informazioni fuori dal manuale rapido.'));
    };
    input.addEventListener('input',fill);
    content.replaceChildren(intro,label,input,count,results);
    fill();
    ensureOpen(trigger);
    input.focus({preventScroll:true});
  }
  function button(request) {
    const result = node('button','reference-link',request.label || request.name || 'Dettagli');
    result.type = 'button';
    result.dataset.referenceKind = request.kind || 'item';
    result.dataset.referenceName = request.name || '';
    if (request.character?.id || request.characterId) result.dataset.referenceCharacter = request.characterId || request.character.id;
    if (request.id) result.dataset.referenceId = request.id;
    result.setAttribute('aria-haspopup','dialog');
    result.title = 'Leggi i dettagli di ' + (request.name || request.label || 'questa voce');
    attached.set(result,request);
    return result;
  }
  function restoreFocus() {
    document.body.style.overflow = previousOverflow;
    if (!previousFocus) return;
    // The close event can arrive after the player has already focused the
    // action composer. Preserve that explicit choice instead of stealing focus.
    const active = document.activeElement;
    const dialog = document.getElementById('reference-dialog');
    if (active && active !== document.body && active !== previousFocus && !dialog?.contains(active)) return;
    if (previousFocus.isConnected) {
      previousFocus.focus({preventScroll:true});
      return;
    }
    let replacement = previousFocus.id && document.getElementById(previousFocus.id);
    if (!replacement && previousFocus.dataset?.referenceName) {
      replacement = [...document.querySelectorAll('[data-reference-name]')].find(element =>
        element.dataset.referenceName === previousFocus.dataset.referenceName &&
        element.dataset.referenceKind === previousFocus.dataset.referenceKind &&
        element.dataset.referenceCharacter === previousFocus.dataset.referenceCharacter);
    }
    if (replacement) replacement.focus({preventScroll:true});
    else document.querySelector('.nav-item.active')?.focus({preventScroll:true});
  }
  function ready() {
    const dialog = document.getElementById('reference-dialog');
    if (!dialog) return;
    document.getElementById('reference-close').addEventListener('click',() => dialog.close());
    const guide = document.querySelector('#view-guida .guide');
    if (guide) {
      const section = node('section','reference-guide');
      const browse = node('button','outline-button','Apri il manuale rapido');
      browse.type = 'button';
      browse.dataset.referenceLibrary = 'true';
      browse.setAttribute('aria-haspopup','dialog');
      section.append(node('h3','','Regole e oggetti a portata di mano'),
        node('p','','Tocca il nome di un oggetto, una magia o una capacità nella scheda per leggerne i dettagli. Puoi anche sfogliare le regole del 2014 nel manuale rapido.'),browse);
      guide.insertBefore(section,guide.querySelector('.attribution'));
    }
    dialog.addEventListener('close',() => {current = null;restoreFocus();});
    dialog.addEventListener('click',event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    });
    document.addEventListener('click',event => {
      const trigger = event.target.closest?.('[data-reference-name], [data-reference-library]');
      if (!trigger) return;
      event.preventDefault();
      if (trigger.hasAttribute('data-reference-library')) library(trigger);
      else open(attached.get(trigger) || {
        kind:trigger.dataset.referenceKind,name:trigger.dataset.referenceName,
        id:trigger.dataset.referenceId,characterId:trigger.dataset.referenceCharacter
      },trigger);
    });
  }
  window.DndReference = {
    configure(options = {}) {settings = {...settings,...options};},
    open,button,library,
    refresh() {
      if (current && document.getElementById('reference-dialog')?.open) {
        const refreshed = current.originId && attached.get(document.getElementById(current.originId));
        if (refreshed?.context) current.context = refreshed.context;
        renderLive(current,findEntry(current));
      }
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',ready,{once:true});
  else ready();
})();
