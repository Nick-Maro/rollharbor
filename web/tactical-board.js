'use strict';

// This board reads public observations only. Every movement is a proposal;
// previews neither move canonical tokens nor spend an action or spell slot.
// Public input: flags.tactical_scene {location_id,id,title,grid:{columns,rows,
// cell_m,confirmed:true},tokens:[{id,entity_id,x,y,confirmed:true}],cover,areas}.
// Coordinates use zero-based cells; only party/public combat entities get tokens.
// flags.table_scene {location_id,id,objects:[{id,name,description,actions}],
// distances:[{a,b,metres,description}]} also works without a confirmed grid.
(() => {
  const mounted = new WeakMap();
  const NS = 'http://www.w3.org/2000/svg';
  const list = value => Array.isArray(value) ? value : [];
  const str = value => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));
  const fmt = value => Number(value.toFixed(2)).toLocaleString('it-IT');
  let uid = 0;

  function node(tag, cls, content) {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (content !== undefined) element.textContent = str(content);
    return element;
  }
  function svg(tag, attrs = {}) {
    const element = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key,value]) => element.setAttribute(key, String(value)));
    return element;
  }
  function button(text, run, cls = '') {
    const element = node('button', 'tac-button ' + cls, text);
    element.type = 'button';
    element.addEventListener('click', run);
    return element;
  }
  function field(record, labelText, name, values, value, change) {
    const wrapper = node('label', 'tac-field');
    const input = node('select');
    input.id = 'tactical-' + record.uid + '-' + name;
    input.setAttribute('aria-label',labelText);
    values.forEach(([key,text]) => {
      const option = node('option', '', text);
      option.value = key;
      input.append(option);
    });
    input.value = str(value);
    input.addEventListener('change', () => change(input.value));
    wrapper.append(node('span', '', labelText), input);
    return wrapper;
  }
  function perception(item) {
    return item && item.hidden !== true && item.perceived !== false && item.revealed !== false;
  }
  function selectedPC(state) {
    return list(state.party).find(pc => pc.id === state.active_character_id) || state.character || null;
  }
  function backgroundFor(value,grid) {
    // A background is already redacted by the private map tool. Never fetch a
    // full DM plan or an arbitrary URL and try to hide its secrets with CSS.
    if (!grid || !value || value.columns!==grid.columns || value.rows!==grid.rows || value.cell_m!==grid.cell_m) return null;
    if (typeof value.url!=='string' || !/^\/assets\/maps\/(?:[a-z0-9_-]+\/)*[a-z0-9_-]+\.(?:svg|png|webp)$/i.test(value.url)) return null;
    return {url:value.url,alt:str(value.alt || 'Pianta della zona rivelata'),columns:value.columns,rows:value.rows,cell_m:value.cell_m};
  }
  function source(state) {
    const scoped = value => value && (!state.location_id || value.location_id === state.location_id) &&
      (!value.scene_id || !state.scene?.id || value.scene_id === state.scene.id) &&
      (!value.combat_id || !state.combat?.id || value.combat_id === state.combat.id) ? value : {};
    const table = scoped(state.flags?.table_scene);
    const raw = scoped(state.flags?.tactical_scene || table.tactical);
    const candidate = raw.grid || {};
    const columns = candidate.columns ?? candidate.cols;
    const rows = candidate.rows;
    const metres = candidate.cell_m ?? candidate.metres_per_cell;
    const grid = candidate.confirmed === true && Number.isInteger(columns) && columns > 0 && columns <= 100 &&
      Number.isInteger(rows) && rows > 0 && rows <= 100 && finite(metres) && metres > 0
      ? {columns, rows, cell_m:metres, distance_rule:candidate.distance_rule === 'euclidean' ? 'euclidean' : 'grid'} : null;
    const positioned = item => grid && item.confirmed === true && finite(item.x) && finite(item.y) &&
      item.x >= 0 && item.y >= 0 && item.x < grid.columns && item.y < grid.rows;
    const known = new Set([...list(state.party),...list(state.combat?.participants)].filter(perception).map(item=>item.id));
    const tokens = list(raw.tokens).filter(perception).filter(positioned).filter(token=>known.has(token.entity_id || token.id));
    const objects = new Map();
    [...list(table.objects), ...list(raw.objects)].filter(perception).forEach((object,index) => {
      if (str(object.name)) objects.set(str(object.id) || 'object-' + index, object);
    });
    return {
      id:str(raw.id || table.id || state.location_id || 'scene'),
      title:str(raw.title || table.title || 'Il campo della scena'),
      description:str(raw.description || table.description),
      grid, positioned, tokens, background:backgroundFor(raw.background,grid),
      objects:[...objects].map(([id,value]) => ({...value,id})),
      cover:list(raw.cover).filter(perception).filter(positioned),
      areas:list(raw.areas).filter(perception).filter(area => area.confirmed === true),
      distances:list(table.distances).filter(item => perception(item) && finite(item.metres) && item.metres >= 0),
    };
  }
  function actor(record, token) {
    return list(record.args.state.party).find(pc => pc.id === (token?.entity_id || token?.id));
  }
  function tokenName(record, token) {
    return str(token.name || actor(record,token)?.name || 'Creatura percepita');
  }
  function send(record, text, pc = selectedPC(record.args.state)) {
    if (typeof record.args.onIntent === 'function') {
      record.args.onIntent(text, {actorId:pc?.id || null, actorName:pc?.name || ''});
      record.status.textContent = 'Proposta preparata: puoi modificarla e portarla nella chat.';
    } else {
      record.free.closest('details').open=true;
      record.free.value = (pc?.name ? pc.name + ': ' : '') + text;
      record.free.focus();
      record.status.textContent = 'Copia la proposta qui sotto e incollala nella chat con il master.';
    }
  }
  function distance(grid, a, b) {
    const dx = Math.abs(a.x-b.x), dy = Math.abs(a.y-b.y);
    return (grid.distance_rule === 'euclidean' ? Math.hypot(dx,dy) : Math.max(dx,dy)) * grid.cell_m;
  }
  function coordinate(point) { return 'colonna ' + (point.x+1) + ', riga ' + (point.y+1); }
  function tokenConditions(record, token) {
    return list(actor(record,token)?.conditions || list(record.args.state.combat?.participants).find(p=>p.id===(token.entity_id||token.id))?.conditions);
  }
  function turnToken(record, token) {
    const combat=record.args.state.combat;
    return combat?.active && list(combat.participants)[combat.turn_index]?.id===(token.entity_id||token.id);
  }
  function tokenId(record, kind, id) { return 'tactical-'+record.uid+'-'+kind+'-'+encodeURIComponent(str(id)); }
  function details(record,key,label) {
    const section=node('details','tac-tool-group');
    section.open=!!record.expanded[key];
    section.append(node('summary','',label));
    section.addEventListener('toggle',()=>{record.expanded[key]=section.open;});
    return section;
  }
  function objectArt(object) {
    const art=svg('svg',{viewBox:'0 0 100 100','aria-hidden':'true',class:'tac-object-art'});
    const name=str(object.id)+' '+str(object.name);
    if (/carro|cart|wagon/i.test(name)) {
      art.append(svg('path',{d:'M34 10V34M66 10V34',stroke:'#c5a870','stroke-width':4,'stroke-linecap':'round'}));
      [30,65].forEach(y=>[16,76].forEach(x=>art.append(svg('rect',{x,y,width:8,height:16,rx:3,fill:'#2a251e',stroke:'#bd9c65','stroke-width':2}))));
      art.append(svg('rect',{x:24,y:29,width:52,height:56,rx:5,fill:'#755138',stroke:'#d9ba7a','stroke-width':2.5}));
      for(let y=38;y<85;y+=10) art.append(svg('path',{d:`M27 ${y}H73`,stroke:'#392b24','stroke-width':1.5}));
      art.append(svg('rect',{x:33,y:42,width:23,height:24,rx:3,fill:'#b6a37a',stroke:'#e0d2a7','stroke-width':1.5}),svg('ellipse',{cx:61,cy:70,rx:10,ry:11,fill:'#80623c',stroke:'#cab27d','stroke-width':2}),svg('path',{d:'M51 68H70M51 73H70M42 43V65',stroke:'#625439','stroke-width':2}));
    } else if (/buoi|bue|oxen|ox\b/i.test(name)) {
      [29,70].forEach(x=>{
        art.append(svg('ellipse',{cx:x,cy:58,rx:14,ry:23,fill:'#b9aa87',stroke:'#f2e2b6','stroke-width':2}),svg('path',{d:`M${x-10} 38Q${x-21} 29 ${x-17} 23M${x+10} 38Q${x+21} 29 ${x+17} 23`,fill:'none',stroke:'#eddfb6','stroke-width':3,'stroke-linecap':'round'}),svg('ellipse',{cx:x,cy:34,rx:10,ry:12,fill:'#a38d6d',stroke:'#e2cf9d','stroke-width':2}),svg('path',{d:`M${x} 81V92`,stroke:'#a38d6d','stroke-width':2}));
      });
      art.append(svg('path',{d:'M10 49H89',stroke:'#7c5633','stroke-width':5,'stroke-linecap':'round'}));
    } else if (/giavellotto|lancia|javelin|spear/i.test(name)) {
      art.append(svg('path',{d:'M24 85L70 24',stroke:'#a87f4a','stroke-width':4,'stroke-linecap':'round'}),svg('path',{d:'M65 28L80 10L76 34Z',fill:'#d7e1d4',stroke:'#60736a','stroke-width':2}),svg('path',{d:'M21 82L29 89',stroke:'#c6aa72','stroke-width':3}));
    } else {
      art.append(svg('path',{d:'M50 15L82 34V69L50 87L18 69V34Z',fill:'#78603c',stroke:'#d2b77a','stroke-width':2}),svg('path',{d:'M18 34L50 53L82 34M50 53V87',fill:'none',stroke:'#d2b77a','stroke-width':2}));
    }
    return art;
  }
  function mount(host) {
    const frame = node('section', 'tactical-board');
    const heading = node('header','tac-heading');
    const headerText = node('div');
    const title = node('h3');
    const subtitle = node('p','tac-subtitle');
    headerText.append(node('p','tac-kicker','SCENA E POSIZIONI'),title,subtitle);
    const badge=node('p','tac-turn-badge');
    heading.append(headerText,badge);
    const body = node('div','tac-body');
    const objects = node('details','tac-objects');
    const freeWrap = node('details','tac-free');
    const freeLabel = node('label','','Un’altra idea');
    const free = node('textarea');
    const record = {uid:++uid,args:null,frame,title,subtitle,badge,body,objects,free,signature:'',selectedId:'',cursor:null,proposal:null,
      preview:{enabled:false,shape:'square',size:6,angle:0},measureA:'',measureB:'',scene:null,expanded:{},zoom:0};
    free.id = 'tactical-' + record.uid + '-free';
    freeLabel.htmlFor = free.id;
    free.rows = 2;
    free.maxLength = 1600;
    free.placeholder = 'Uso il carro come riparo, tento di distrarre la guardia…';
    const prepare = button('Prepara la proposta', () => {
      if (free.value.trim()) send(record,free.value.trim());
      else free.focus();
    });
    record.status = node('p','tac-status');
    record.status.setAttribute('role','status');
    record.status.setAttribute('aria-live','polite');
    freeWrap.append(node('summary','','Proponi un’altra idea'),freeLabel,free,prepare);
    frame.append(heading,body,objects,freeWrap,record.status);
    host.replaceChildren(frame);
    mounted.set(host,record);
    return record;
  }
  function selectToken(record, token) {
    record.selectedId = str(token.id);
    record.cursor = {x:token.x,y:token.y};
    record.proposal = null;
    redraw(record);
  }
  function pointAt(record,event) {
    const box = record.surface.getBoundingClientRect();
    if (!box.width || !box.height) return record.cursor || {x:0,y:0};
    return {
      x:clamp(Math.floor((event.clientX-box.left)/box.width*record.scene.grid.columns),0,record.scene.grid.columns-1),
      y:clamp(Math.floor((event.clientY-box.top)/box.height*record.scene.grid.rows),0,record.scene.grid.rows-1),
    };
  }
  function proposeAt(record,point) {
    record.cursor = point;
    const token = record.scene.tokens.find(item => str(item.id) === record.selectedId);
    if (token && actor(record,token)) record.proposal = {tokenId:str(token.id),fromX:token.x,fromY:token.y,...point};
    else record.proposal = null;
    paintOverlay(record);
    renderSelection(record);
  }
  function map(record) {
    const {grid,tokens,objects,cover} = record.scene;
    const wrapper = node('div','tac-map-column');
    const instructions = node('p','tac-instructions','Scegli la tua pedina, poi tocca una casella o trascinala per preparare un movimento.');
    instructions.id = 'tactical-' + record.uid + '-instructions';
    const viewport = node('div','tac-viewport');
    const surface = node('div','tac-surface');
    surface.style.aspectRatio = grid.columns + ' / ' + grid.rows;
    surface.style.minWidth = record.zoom===0?'0':Math.max(300,grid.columns*44*record.zoom) + 'px';
    surface.style.setProperty('--tac-cols',grid.columns);
    surface.style.setProperty('--tac-rows',grid.rows);
    surface.tabIndex = 0;
    surface.setAttribute('role','group');
    surface.setAttribute('aria-label','Mappa tattica, '+grid.columns+' colonne e '+grid.rows+' righe');
    surface.setAttribute('aria-describedby',instructions.id);
    surface.id = 'tactical-' + record.uid + '-surface';
    const art = svg('svg',{viewBox:`0 0 ${grid.columns} ${grid.rows}`,'aria-hidden':'true',preserveAspectRatio:'none',class:'tac-map-art'});
    const patternId = 'tac-grid-' + record.uid;
    const defs = svg('defs');
    const pattern = svg('pattern',{id:patternId,width:1,height:1,patternUnits:'userSpaceOnUse'});
    pattern.append(svg('path',{d:'M1 0H0V1',fill:'none',stroke:'#ebe1b5','stroke-width':.015,opacity:.2}));
    const texture=svg('pattern',{id:'tac-ground-'+record.uid,width:2,height:2,patternUnits:'userSpaceOnUse'});
    texture.append(svg('path',{d:'M.18 .2l.08 .02M1.2 .8l.12 -.04M.4 1.6l.08 -.03M1.7 1.5l.03 .06',stroke:'#e3cf9b','stroke-width':.035,opacity:.14,'stroke-linecap':'round'}));
    const vignette=svg('radialGradient',{id:'tac-shade-'+record.uid});
    vignette.append(svg('stop',{offset:'.2','stop-color':'#71826a','stop-opacity':0}),svg('stop',{offset:'1','stop-color':'#101e18','stop-opacity':.62}));
    defs.append(pattern,texture,vignette);
    art.append(defs,svg('rect',{width:grid.columns,height:grid.rows,fill:'#4b5a43'}),svg('rect',{width:grid.columns,height:grid.rows,fill:'url(#tac-ground-'+record.uid+')'}),svg('rect',{width:grid.columns,height:grid.rows,fill:'url(#tac-shade-'+record.uid+')'}),svg('rect',{width:grid.columns,height:grid.rows,fill:'url(#'+patternId+')'}));
    if (record.scene.background) {
      const background=svg('image',{x:0,y:0,width:grid.columns,height:grid.rows,href:record.scene.background.url,
        preserveAspectRatio:'none',class:'tac-cartography-image'});
      const title=svg('title');title.textContent=record.scene.background.alt;background.append(title);
      background.addEventListener('error',()=>{background.remove();art.classList.remove('has-cartography');});
      art.classList.add('has-cartography');art.append(background);
    }
    if (grid.columns<=30 && grid.rows<=30) {
      for(let x=0;x<grid.columns;x++) {
        const label=svg('text',{x:x+.12,y:.24,class:'tac-coordinate'});
        label.textContent=String(x+1);art.append(label);
      }
      for(let y=1;y<grid.rows;y++) {
        const label=svg('text',{x:.1,y:y+.24,class:'tac-coordinate'});
        label.textContent=String(y+1);art.append(label);
      }
    }
    for (const item of cover) {
      const rect = svg('rect',{x:item.x,y:item.y,width:finite(item.width)&&item.width>0?item.width:1,
        height:finite(item.height)&&item.height>0?item.height:1,rx:.08,class:'tac-cover-shape'});
      const title = svg('title');
      title.textContent = str(item.name || 'Copertura') + ': ' + str(item.description);
      rect.append(title);
      art.append(rect);
    }
    const overlay = svg('g');
    art.append(overlay);
    surface.append(art);
    record.surface=surface;
    record.overlay=overlay;
    tokens.forEach(token => {
      const pc = actor(record,token);
      const conditions=tokenConditions(record,token);
      const down=conditions.some(condition=>/privo di sensi|unconscious|morto|dead/i.test(str(condition)));
      const item = button('',()=>selectToken(record,token),'tac-token'+(pc?' tac-pc':' tac-npc')+(str(token.id)===record.selectedId?' is-selected':'')+(turnToken(record,token)?' is-turn':'')+(down?' is-down':''));
      item.id=tokenId(record,'token',token.id);
      const initials=node('span','tac-token-initials',tokenName(record,token).split(/\s+/).map(word=>word[0]).slice(0,2).join('').toLocaleUpperCase('it'));
      initials.setAttribute('aria-hidden','true');
      const name=node('span','tac-token-name',tokenName(record,token).split(/\s+/)[0]);
      name.setAttribute('aria-hidden','true');
      item.append(initials,name);
      if(conditions.length) {
        const marker=node('span','tac-token-condition',down?'☾':'!');
        marker.setAttribute('aria-hidden','true');item.append(marker);
      }
      item.dataset.tokenId=str(token.id);
      item.setAttribute('aria-label',tokenName(record,token)+', '+coordinate(token)+(turnToken(record,token)?', turno attuale':'')+(conditions.length?', '+conditions.join(', '):'')+(pc?', seleziona per proporre un movimento':''));
      item.setAttribute('aria-pressed',String(str(token.id)===record.selectedId));
      item.title=tokenName(record,token)+(conditions.length?' · '+conditions.join(' · '):'');
      item.style.left=(token.x+.5)/grid.columns*100+'%';
      item.style.top=(token.y+.5)/grid.rows*100+'%';
      item.style.setProperty('--token-size',(72/grid.columns)+'%');
      let drag=null;
      item.addEventListener('pointerdown',event=>{
        if (!pc || (event.pointerType==='mouse'&&event.button!==0)) return;
        drag={x:event.clientX,y:event.clientY,moved:false};
        item.setPointerCapture?.(event.pointerId);
      });
      item.addEventListener('pointermove',event=>{
        if (!drag) return;
        if (Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>6) drag.moved=true;
        if (drag.moved) {
          record.selectedId=str(token.id);
          record.cursor=pointAt(record,event);
          record.proposal={tokenId:str(token.id),fromX:token.x,fromY:token.y,...record.cursor};
          paintOverlay(record);
        }
      });
      item.addEventListener('pointerup',event=>{
        if (!drag) return;
        const moved=drag.moved;
        drag=null;
        if (moved) {
          item.addEventListener('click',event=>event.stopImmediatePropagation(),{once:true,capture:true});
          proposeAt(record,pointAt(record,event));
        }
      });
      item.addEventListener('pointercancel',()=>{drag=null;record.proposal=null;paintOverlay(record);renderSelection(record);});
      surface.append(item);
    });
    objects.filter(record.scene.positioned).forEach(object=>{
      const item=button('',()=>openObject(record,object),'tac-object-pin');
      item.id=tokenId(record,'object',object.id);
      item.setAttribute('aria-label','Esamina '+str(object.name));
      item.title=str(object.name);
      const width=finite(object.width)&&object.width>0?Math.min(object.width,grid.columns-object.x):1;
      const height=finite(object.height)&&object.height>0?Math.min(object.height,grid.rows-object.y):1;
      item.style.left=object.x/grid.columns*100+'%';
      item.style.top=object.y/grid.rows*100+'%';
      item.style.width=width/grid.columns*100+'%';
      item.style.height=height/grid.rows*100+'%';
      item.append(objectArt(object));
      surface.append(item);
    });
    surface.addEventListener('click',event=>{
      if (event.target.closest('button')) return;
      proposeAt(record,pointAt(record,event));
    });
    surface.addEventListener('keydown',event=>{
      if (event.target!==surface) return;
      const deltas={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
      if (deltas[event.key]) {
        event.preventDefault();
        const current=record.cursor||{x:0,y:0}, [x,y]=deltas[event.key];
        record.cursor={x:clamp(current.x+x,0,grid.columns-1),y:clamp(current.y+y,0,grid.rows-1)};
        paintOverlay(record);
        renderSelection(record);
      } else if (event.key==='Enter'||event.key===' ') {
        event.preventDefault();
        proposeAt(record,record.cursor||{x:0,y:0});
      } else if (event.key==='Escape') {
        record.proposal=null;
        record.preview.enabled=false;
        syncPreviewToggle(record);
        paintOverlay(record);
        renderSelection(record);
      }
    });
    viewport.append(surface);
    const controls=node('div','tac-map-controls');
    const scale=node('p','tac-scale',`1 casella = ${fmt(grid.cell_m)} m`);
    scale.title=grid.distance_rule==='euclidean'?'Distanze in linea retta':'Una casella anche in diagonale';
    const zoom=node('div','tac-zoom');
    zoom.setAttribute('aria-label','Dimensione della mappa');
    zoom.append(button('−',()=>{record.zoom=Math.max(.75,(record.zoom||1)-.25);redraw(record);}));
    zoom.lastElementChild.setAttribute('aria-label','Riduci la mappa');
    zoom.append(button('Adatta',()=>{record.zoom=0;redraw(record);}));
    zoom.append(button('+',()=>{record.zoom=Math.min(2,(record.zoom||.75)+.25);redraw(record);}));
    zoom.lastElementChild.setAttribute('aria-label','Ingrandisci la mappa');
    [...zoom.children].forEach((control,index)=>{control.id='tactical-'+record.uid+'-zoom-'+index;});
    controls.append(scale,zoom);
    const legend=node('div','tac-legend');
    legend.append(node('span','tac-legend-party','Gruppo'),node('span','tac-legend-npc','Altre creature'),node('span','tac-legend-draft','Proposta'));
    const library=node('a','tac-library-link','Apri la cartoteca ↗');
    library.href='/maps.html';library.target='_blank';library.rel='noopener';legend.append(library);
    wrapper.append(controls,viewport,legend,instructions);
    return wrapper;
  }
  function paintArea(record,area,local=false) {
    const grid=record.scene.grid;
    if (!finite(area.x)||!finite(area.y)||!finite(area.size_m)||area.size_m<=0) return;
    const size=area.size_m/grid.cell_m;
    const x=area.x+.5,y=area.y+.5;
    const common={class:local?'tac-area-preview':'tac-area-confirmed'};
    let shape;
    if (area.shape==='circle') shape=svg('circle',{cx:x,cy:y,r:size,...common});
    else if (area.shape==='cone') {
      const angle=(finite(area.angle)?area.angle:0)*Math.PI/180;
      const endX=x+size*Math.cos(angle),endY=y+size*Math.sin(angle);
      const ax=endX-size/2*Math.sin(angle),ay=endY+size/2*Math.cos(angle);
      const bx=endX+size/2*Math.sin(angle),by=endY-size/2*Math.cos(angle);
      shape=svg('path',{d:`M${x} ${y}L${ax} ${ay}L${bx} ${by}Z`,...common});
    } else if (area.shape==='square') shape=svg('rect',{x:area.x,y:area.y,width:size,height:size,...common});
    if (shape) {
      const title=svg('title');
      title.textContent=local?'Anteprima locale, non è un incantesimo lanciato':str(area.name||'Area confermata dal master');
      shape.append(title);
      record.overlay.append(shape);
    }
  }
  function paintOverlay(record) {
    if (!record.overlay) return;
    record.overlay.replaceChildren();
    record.scene.areas.forEach(area=>paintArea(record,area));
    if (record.preview.enabled && record.cursor) paintArea(record,{...record.preview,x:record.cursor.x,y:record.cursor.y,size_m:record.preview.size},true);
    if (record.cursor) record.overlay.append(svg('rect',{x:record.cursor.x,y:record.cursor.y,width:1,height:1,class:'tac-cursor'}));
    if (record.proposal) {
      const token=record.scene.tokens.find(item=>str(item.id)===record.proposal.tokenId);
      if (token) {
        record.overlay.append(svg('line',{x1:token.x+.5,y1:token.y+.5,x2:record.proposal.x+.5,y2:record.proposal.y+.5,class:'tac-move-line'}));
        record.overlay.append(svg('circle',{cx:record.proposal.x+.5,cy:record.proposal.y+.5,r:.32,class:'tac-move-target'}));
        const label=svg('text',{x:record.proposal.x+.5,y:record.proposal.y+.58,class:'tac-proposal-label'});
        label.textContent=fmt(distance(record.scene.grid,token,record.proposal))+' m';
        record.overlay.append(label);
      }
    }
    if (record.surface) record.surface.setAttribute('aria-label','Mappa tattica'+(record.cursor?', puntatore: '+coordinate(record.cursor):''));
  }
  function syncPreviewToggle(record) {
    if (!record.previewToggle) return;
    record.previewToggle.textContent=record.preview.enabled?'Nascondi anteprima':'Mostra anteprima';
    record.previewToggle.setAttribute('aria-pressed',String(record.preview.enabled));
  }
  function renderSelection(record) {
    const host=record.selection;
    if (!host) return;
    host.replaceChildren();
    const token=record.scene.tokens.find(item=>str(item.id)===record.selectedId);
    if (!token) {
      host.append(node('p','tac-muted','Seleziona una pedina per consultarne la posizione.'));
      return;
    }
    const pc=actor(record,token);
    host.append(node('h4','',tokenName(record,token)),node('p','tac-muted',coordinate(token)));
    if (str(token.description)) host.append(node('p','tac-copy',token.description));
    const conditions=tokenConditions(record,token);
    if (conditions.length) host.append(node('p','tac-condition-copy',conditions.join(' · ')));
    if (pc) host.append(node('p','tac-fineprint','Scegli una casella per proporre dove andare. Le posizioni cambiano dopo la risoluzione in chat.'));
    if (pc && record.proposal?.tokenId===str(token.id)) {
      const d=distance(record.scene.grid,token,record.proposal);
      host.append(node('p','tac-distance','Percorso proposto: '+fmt(d)+' m'));
      host.append(node('p','tac-fineprint','La misura geometrica non verifica ostacoli, terreno difficile, portata o attacchi di opportunità.'));
      const proposal={...record.proposal};
      const submit=button('Proponi movimento',()=>send(record,'Vorrei spostarmi da '+coordinate(token)+' a '+coordinate(proposal)+' ('+fmt(d)+' m sulla mappa).',pc),'tac-primary');
      submit.id='tactical-'+record.uid+'-submit-move';
      const cancel=button('Annulla anteprima',()=>{record.proposal=null;paintOverlay(record);renderSelection(record);});
      cancel.id='tactical-'+record.uid+'-cancel-move';
      host.append(submit,cancel);
    } else if (!pc) host.append(button('Prepara interazione',()=>send(record,'Vorrei interagire con '+tokenName(record,token)+'.')));
  }
  function tools(record) {
    const side=node('aside','tac-tools');
    const roster=node('div','tac-roster');
    record.scene.tokens.forEach(token=>{
      const item=button(tokenName(record,token),()=>selectToken(record,token));
      item.id=tokenId(record,'roster',token.id);
      item.setAttribute('aria-pressed',String(str(token.id)===record.selectedId));
      item.classList.toggle('is-turn',!!turnToken(record,token));
      roster.append(item);
    });
    const selection=node('div','tac-selection');
    selection.setAttribute('aria-live','polite');
    record.selection=selection;
    side.append(node('h4','','Sul campo'),roster,selection);
    const measure=details(record,'measure','Misura una distanza');
    const options=[['','Scegli una pedina'],...record.scene.tokens.map(token=>[str(token.id),tokenName(record,token)])];
    const result=node('p','tac-distance');
    const update=()=>{
      const a=record.scene.tokens.find(t=>str(t.id)===record.measureA),b=record.scene.tokens.find(t=>str(t.id)===record.measureB);
      result.textContent=a&&b?fmt(distance(record.scene.grid,a,b))+' m tra i centri delle caselle':'Scegli le due pedine.';
    };
    measure.append(field(record,'Da','measure-a',options,record.measureA,value=>{record.measureA=value;update();}),field(record,'A','measure-b',options,record.measureB,value=>{record.measureB=value;update();}),result);
    update();
    const area=details(record,'area','Anteprima area di magia');
    area.append(node('p','tac-fineprint','Scegli una forma e tocca il punto di origine sulla mappa. Nessun lancio o consumo di risorse.'));
    const toggle=button(record.preview.enabled?'Nascondi anteprima':'Mostra anteprima',()=>{
      record.preview.enabled=!record.preview.enabled;
      record.cursor=record.cursor||{x:0,y:0};
      syncPreviewToggle(record);
      paintOverlay(record);
    });
    toggle.setAttribute('aria-pressed',String(record.preview.enabled));
    record.previewToggle=toggle;
    area.append(field(record,'Forma','shape',[['square','Quadrato'],['circle','Cerchio'],['cone','Cono schematico']],record.preview.shape,value=>{
      record.preview.shape=value;
      sizeLabel.textContent=value==='circle'?'Raggio (m)':value==='cone'?'Lunghezza (m)':'Lato (m)';
      paintOverlay(record);
    }));
    const sizeWrapper=node('label','tac-field'),sizeLabel=node('span','',record.preview.shape==='circle'?'Raggio (m)':record.preview.shape==='cone'?'Lunghezza (m)':'Lato (m)');
    const size=node('input');
    size.id='tactical-'+record.uid+'-area-size';
    size.type='number';size.min='.5';size.max='300';size.step='.5';size.value=record.preview.size;
    size.addEventListener('input',()=>{if (Number.isFinite(size.valueAsNumber)&&size.valueAsNumber>=.5&&size.valueAsNumber<=300) {record.preview.size=size.valueAsNumber;paintOverlay(record);}});
    sizeWrapper.append(sizeLabel,size);
    area.append(sizeWrapper,field(record,'Direzione del cono','angle',Array.from({length:8},(_,index)=>[index*45,index*45+'°']),record.preview.angle,value=>{record.preview.angle=Number(value);paintOverlay(record);}),toggle,
      node('p','tac-fineprint','Il master conferma origine, forma effettiva, copertura e creature coinvolte. Il cono è un ausilio schematico.'));
    side.append(measure,area);
    if (record.scene.cover.length) {
      const covers=details(record,'cover','Coperture conosciute');
      const labels={half:'Mezza copertura',three_quarters:'Tre quarti di copertura',total:'Copertura totale'};
      record.scene.cover.forEach(cover=>covers.append(node('p','tac-copy',str(cover.name||'Riparo')+' · '+(labels[cover.kind]||'Copertura da valutare')+(cover.description?' — '+str(cover.description):''))));
      side.append(covers);
    }
    const help=details(record,'help','Comandi e lettura della mappa');
    if(record.scene.description) help.append(node('p','tac-copy',record.scene.description));
    help.append(node('p','tac-fineprint','Le pedine piene sono posizioni confermate; il cerchio tratteggiato è una proposta. Frecce: sposta il puntatore. Invio: scegli la destinazione. Esc: annulla le anteprime. Su schermi piccoli puoi scorrere la mappa o premere Adatta.'),node('p','tac-fineprint','La texture del campo è decorativa. Ostacoli e coperture sono soltanto quelli annotati dal master.'));
    side.append(help);
    return side;
  }
  function resolveName(record,id) {
    const entity=[...list(record.args.state.party),...list(record.args.state.combat?.participants),...record.scene.objects,...record.scene.tokens]
      .find(item=>item.id===id || item.entity_id===id);
    return str(entity?.name || id || 'Posizione');
  }
  function noMap(record) {
    const wrapper=node('div','tac-no-map');
    wrapper.append(node('h4','','Le posizioni conosciute'),node('p','tac-copy','La planimetria di questa scena non è ancora definita. Puoi usare le distanze confermate e proporre liberamente movimenti e interazioni.'));
    if (record.scene.distances.length) {
      const relations=node('ul','tac-relations');
      record.scene.distances.forEach(pair=>{
        const item=node('li');
        item.append(node('span','',resolveName(record,pair.a)+' ↔ '+resolveName(record,pair.b)),node('strong','',fmt(pair.metres)+' m'));
        if (str(pair.description)) item.append(node('small','',pair.description));
        relations.append(item);
      });
      wrapper.append(relations,node('p','tac-fineprint','Distanze riportate dal master. Non definiscono orientamento, percorso o una griglia.'));
    }
    wrapper.append(button('Chiedi una planimetria al master',()=>send(record,'Possiamo definire una mappa tattica della scena, con posizioni e distanze confermate?')));
    return wrapper;
  }
  function openObject(record,object) {
    record.objectId=object.id;
    if (!record.dialog) {
      const dialog=node('dialog','tac-object-dialog');
      dialog.setAttribute('aria-labelledby','tactical-'+record.uid+'-object-title');
      record.frame.append(dialog);
      record.dialog=dialog;
      dialog.addEventListener('close',()=>{
        if (record.dialogReturnId) document.getElementById(record.dialogReturnId)?.focus({preventScroll:true});
      });
    }
    const dialog=record.dialog;
    const wasOpen=dialog.open;
    if (!wasOpen) record.dialogReturnId=document.activeElement?.id || '';
    const focusId=dialog.contains(document.activeElement)?document.activeElement.id:'';
    record.objectSnapshot=JSON.stringify(object);
    const head=node('div','tac-dialog-heading');
    const title=node('h3','',object.name);
    title.id='tactical-'+record.uid+'-object-title';
    const close=button('Chiudi',()=>dialog.close());
    close.id='tactical-'+record.uid+'-object-close';
    head.append(title,close);
    const actions=node('div','tac-object-actions');
    actions.append(button('Esamina',()=>{send(record,'Vorrei esaminare '+str(object.name)+'.');dialog.close();}),button('Interagisci',()=>{send(record,'Vorrei interagire con '+str(object.name)+'.');dialog.close();}));
    list(object.actions).slice(0,12).forEach(action=>{
      const label=typeof action==='string'?action:str(action?.label);
      const intent=typeof action==='string'?action:str(action?.intent || label);
      if (label&&intent) actions.append(button(label,()=>{send(record,intent);dialog.close();}));
    });
    dialog.replaceChildren(head,node('p','tac-copy',object.description||'Non avete ancora osservato altri dettagli.'),actions,node('p','tac-fineprint','Descrivi nella chat ciò che vuoi tentare: queste proposte non consumano azioni.'));
    if (!wasOpen) dialog.showModal();
    else if (focusId) document.getElementById(focusId)?.focus({preventScroll:true});
  }
  function renderObjects(record) {
    const host=record.objects;
    host.replaceChildren(node('summary','','Elementi della scena'+(record.scene.objects.length?' · '+record.scene.objects.length:'')));
    if (!record.scene.objects.length) {host.append(node('p','tac-muted','Chiedi al master quali elementi puoi osservare o descrivi direttamente ciò che vuoi cercare.'));return;}
    const cards=node('div','tac-object-list');
    record.scene.objects.forEach(object=>{
      const card=node('article','tac-object-card');
      const inspect=button('Osserva e interagisci',()=>openObject(record,object));
      inspect.id=tokenId(record,'inspect',object.id);
      card.append(objectArt(object),node('h5','',object.name),node('p','tac-copy',object.description||'Osserva più da vicino per saperne di più.'),inspect);
      cards.append(card);
    });
    host.append(cards);
  }
  function redraw(record) {
    const focused=document.activeElement;
    const focusId=record.frame.contains(focused)?focused.id:'';
    const scroll=record.frame.querySelector('.tac-viewport')?.scrollLeft||0;
    const scrollTop=record.frame.querySelector('.tac-viewport')?.scrollTop||0;
    record.title.textContent=record.scene.title;
    record.subtitle.textContent=record.scene.grid?record.scene.grid.columns+' × '+record.scene.grid.rows+' caselle · '+fmt(record.scene.grid.columns*record.scene.grid.cell_m)+' × '+fmt(record.scene.grid.rows*record.scene.grid.cell_m)+' m':'Posizioni e distanze conosciute';
    const combat=record.args.state.combat;
    const current=combat?.active?list(combat.participants)[combat.turn_index]:null;
    record.badge.textContent=current?'Round '+combat.round+' · '+str(current.name):'Mappa della scena';
    record.overlay=null;record.surface=null;record.selection=null;
    record.body.replaceChildren();
    if (record.scene.grid) record.body.append(map(record),tools(record));
    else record.body.append(noMap(record));
    record.body.classList.toggle('has-grid',!!record.scene.grid);
    renderObjects(record);
    if (record.dialog?.open) {
      const object=record.scene.objects.find(item=>item.id===record.objectId);
      if (!object) record.dialog.close();
      else if (JSON.stringify(object)!==record.objectSnapshot) openObject(record,object);
    }
    paintOverlay(record);
    renderSelection(record);
    const viewport=record.frame.querySelector('.tac-viewport');
    if (viewport) {viewport.scrollLeft=scroll;viewport.scrollTop=scrollTop;}
    if (focusId) document.getElementById(focusId)?.focus({preventScroll:true});
  }
  function render(args) {
    if (!args?.host) return;
    const record=mounted.get(args.host)||mount(args.host);
    record.args=args;
    const scene=source(args.state||{});
    const signature=JSON.stringify([scene,args.state?.party?.map(pc=>({id:pc.id,name:pc.name,conditions:pc.conditions})),args.state?.active_character_id,args.state?.combat?.active,args.state?.combat?.round,args.state?.combat?.turn_index,args.state?.combat?.participants?.map(p=>({id:p.id,name:p.name,conditions:p.conditions}))]);
    if (signature===record.signature) return;
    if (record.scene?.id!==scene.id) {
      record.selectedId='';record.cursor=null;record.proposal=null;record.preview.enabled=false;
      if (record.dialog?.open) record.dialog.close();
    }
    if (JSON.stringify(record.scene?.grid)!==JSON.stringify(scene.grid)) {
      record.cursor=null;record.proposal=null;record.preview.enabled=false;
    }
    record.scene=scene;
    record.signature=signature;
    if (!scene.tokens.some(t=>str(t.id)===record.selectedId)) {
      const pc=selectedPC(args.state||{});
      record.selectedId=str(scene.tokens.find(t=>(t.entity_id||t.id)===pc?.id)?.id);
      record.proposal=null;
    }
    if (record.proposal) {
      const token=scene.tokens.find(t=>str(t.id)===record.proposal.tokenId);
      if (!scene.grid || !token || token.x!==record.proposal.fromX || token.y!==record.proposal.fromY || record.proposal.x>=scene.grid.columns || record.proposal.y>=scene.grid.rows) record.proposal=null;
    }
    redraw(record);
  }
  window.DndTactical=Object.freeze({render});
})();
