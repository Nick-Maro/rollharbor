'use strict';

// The library contains public illustrations only. It never reads or writes a save.
(() => {
  const $ = id => document.getElementById(id);
  const viewport = $('map-viewport'), canvas = $('map-canvas'), image = $('map-image');
  let maps = [], current = null, variant = null, zoom = 1, offset = {x:0,y:0}, drag = null;
  let fit = {width:1,height:1}, loadSerial = 0;
  const validAsset = value => typeof value === 'string' && /^\/assets\/maps\/(?:[a-z0-9_-]+\/)*[a-z0-9_-]+\.(?:svg|png|webp|ds)$/i.test(value);
  const message = value => {$('map-message').textContent=value;$('map-message').hidden=!value;};
  function node(tag, cls, text) {
    const result=document.createElement(tag);
    if(cls)result.className=cls;
    if(text!==undefined)result.textContent=String(text);
    return result;
  }
  function paint() {
    canvas.style.width=fit.width+'px';canvas.style.height=fit.height+'px';
    canvas.style.transform=`translate(calc(-50% + ${offset.x}px),calc(-50% + ${offset.y}px)) scale(${zoom})`;
    $('map-zoom-value').textContent=Math.round(zoom*100)+'%';
    $('map-zoom-out').disabled=zoom<=.5;
    $('map-zoom-in').disabled=zoom>=12;
  }
  function fitMap(reset=true) {
    if(!current)return;
    const ratio=Number(current.columns)>0&&Number(current.rows)>0?current.columns/current.rows:image.naturalWidth/image.naturalHeight;
    if(!Number.isFinite(ratio)||ratio<=0)return;
    const width=Math.max(40,viewport.clientWidth-40),height=Math.max(40,viewport.clientHeight-40);
    fit={width:Math.min(width,height*ratio),height:Math.min(height,width/ratio)};
    if(reset){zoom=1;offset={x:0,y:0};}
    paint();
  }
  function setZoom(value) {zoom=Math.max(.5,Math.min(12,value));paint();}
  function download(id,url) {
    const link=$(id);link.hidden=!validAsset(url);
    if(!link.hidden){link.href=url;link.download=url.split('/').pop();}
    else link.removeAttribute('href');
  }
  function selectVariant(value) {
    variant=current.variants.find(item=>item.id===value)||current.variants[0];
    const serial=++loadSerial;
    message('Stendiamo la carta…');
    image.alt=current.title+' · '+variant.title;
    image.onload=()=>{if(serial!==loadSerial)return;message('');fitMap(true);};
    image.onerror=()=>{if(serial===loadSerial)message('Questa carta non si è caricata. Scegline un’altra o ricarica la pagina.');};
    image.src=variant.svg||variant.png;
    download('map-svg',variant.svg);download('map-png',variant.png);download('map-project',current.project);
  }
  function selectMap(id) {
    const candidate=maps.find(item=>item.id===id);if(!candidate)return;
    current=candidate;
    for(const card of $('map-list').querySelectorAll('button'))card.setAttribute('aria-current',String(card.dataset.mapId===id));
    $('map-title').textContent=current.title;
    $('map-kind').textContent=current.kind||'CARTA ORIGINALE';
    $('map-description').textContent=current.description||'';
    $('map-origin').textContent=current.origin||'';
    $('map-scale').textContent=Number(current.columns)>0&&Number(current.rows)>0?
      `${current.columns} × ${current.rows} caselle`+(Number(current.cell_m)>0?` · ${current.cell_m.toLocaleString('it-IT')} m per casella`:''):'Carta illustrata';
    $('map-style').replaceChildren(...current.variants.map(item=>{const option=node('option','',item.title);option.value=item.id;return option;}));
    $('map-style').disabled=current.variants.length<2;
    history.replaceState(null,'','#'+encodeURIComponent(id));
    selectVariant(current.variants[0].id);
  }
  $('map-fit').addEventListener('click',()=>fitMap(true));
  $('map-zoom-in').addEventListener('click',()=>setZoom(zoom*1.35));
  $('map-zoom-out').addEventListener('click',()=>setZoom(zoom/1.35));
  $('map-style').addEventListener('change',event=>selectVariant(event.target.value));
  viewport.addEventListener('pointerdown',event=>{
    if(event.pointerType==='mouse'&&event.button!==0)return;
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,origin:{...offset}};
    viewport.setPointerCapture(event.pointerId);viewport.classList.add('is-dragging');
  });
  viewport.addEventListener('pointermove',event=>{
    if(!drag||drag.id!==event.pointerId)return;
    offset={x:drag.origin.x+event.clientX-drag.x,y:drag.origin.y+event.clientY-drag.y};paint();
  });
  function stopDrag(event){if(drag?.id===event.pointerId){drag=null;viewport.classList.remove('is-dragging');}}
  viewport.addEventListener('pointerup',stopDrag);viewport.addEventListener('pointercancel',stopDrag);viewport.addEventListener('lostpointercapture',stopDrag);
  viewport.addEventListener('keydown',event=>{
    const directions={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};
    if(directions[event.key]){event.preventDefault();offset.x+=directions[event.key][0];offset.y+=directions[event.key][1];paint();}
    else if(['+','=','-','0'].includes(event.key)){event.preventDefault();if(event.key==='0')fitMap(true);else setZoom(zoom*(event.key==='-'?1/1.35:1.35));}
  });
  if('ResizeObserver'in window)new ResizeObserver(()=>fitMap(false)).observe(viewport);
  else window.addEventListener('resize',()=>fitMap(false));
  (async()=>{
    try{
      const response=await fetch('/assets/maps/library.json',{cache:'no-store'});
      if(!response.ok)throw new Error('library');
      const library=await response.json();
      maps=(Array.isArray(library.maps)?library.maps:[]).filter(item=>item&&typeof item.id==='string'&&Array.isArray(item.variants));
      maps=maps.map(item=>({...item,variants:item.variants.filter(v=>validAsset(v.svg)||validAsset(v.png))})).filter(item=>item.variants.length);
      if(!maps.length)throw new Error('empty');
      $('map-list').replaceChildren(...maps.map(item=>{
        const card=node('button','carto-card');card.type='button';card.dataset.mapId=item.id;
        const preview=node('img');preview.alt='';preview.loading='lazy';preview.src=item.variants[0].svg||item.variants[0].png;
        const copy=node('span','carto-card-copy');copy.append(node('strong','',item.title),node('small','',item.columns&&item.rows?item.columns+' × '+item.rows+' · '+(item.kind||'Carta originale'):item.kind||'Carta originale'));
        card.append(preview,copy);card.addEventListener('click',()=>selectMap(item.id));return card;
      }));
      let desired='';try{desired=decodeURIComponent(location.hash.slice(1));}catch{/* Invalid links use the first public map. */}
      selectMap(maps.some(item=>item.id===desired)?desired:maps[0].id);
    }catch{message('La cartoteca non è disponibile. Riapri il tavolo con AVVIA.cmd e riprova.');}
  })();
})();
