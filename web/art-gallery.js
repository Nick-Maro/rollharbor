'use strict';

// These original illustrations are an album, never a source of campaign state.
(() => {
  const catalog=Object.freeze([
    {id:'campfire',title:'Sotto le stelle',kicker:'ACCAMPAMENTO',description:'Il chiarore del fuoco, il silenzio della notte e il tempo di raccontarsi una storia.',alt:'Illustrazione fantasy originale di un accampamento notturno attorno a un fuoco.'},
    {id:'tavern',title:'Il calore della taverna',kicker:'UNA SOSTA AL COPERTO',description:'Legno consumato, luci calde e un angolo in cui il viaggio può prendersi una pausa.',alt:'Illustrazione fantasy originale dell’interno di una taverna medievale.'},
    {id:'forest-road',title:'Il sentiero tra gli alberi',kicker:'STRADE DA IMMAGINARE',description:'Una strada si perde nel verde e nella luce: un invito a immaginare il prossimo cammino.',alt:'Illustrazione fantasy originale di una strada che attraversa un bosco.'},
    {id:'ruined-entrance',title:'La soglia dimenticata',kicker:'PIETRE E MEMORIA',description:'Un ingresso antico, segnato dal tempo, lascia spazio alle domande e all’immaginazione.',alt:'Illustrazione fantasy originale dell’ingresso di una rovina antica.'}
  ]);
  const $=id=>document.getElementById(id),dialog=$('art-dialog');
  const asset=(item,extension)=>'/assets/immersion/extra/'+item.id+'.'+extension;
  let currentIndex=0,previousFocus=null,previousOverflow='';
  function node(tag,cls,text){
    const result=document.createElement(tag);if(cls)result.className=cls;
    if(text!==undefined)result.textContent=String(text);return result;
  }
  function imageFrame(item,{eager=false,preview=false}={}){
    const frame=node('div','art-image-frame');
    const placeholder=node('div','art-placeholder');placeholder.setAttribute('aria-hidden','true');
    placeholder.append(node('span','','✦'),node('p','','L’immagine prende forma…'));
    const image=node('img');image.alt=item.alt;image.loading=eager?'eager':'lazy';image.decoding='async';image.draggable=false;
    let fallback=false;
    image.addEventListener('load',()=>{frame.classList.add('is-loaded');frame.classList.remove('is-error');});
    image.addEventListener('error',()=>{
      if(!fallback){fallback=true;image.src=asset(item,'png');return;}
      frame.classList.remove('is-loaded');frame.classList.add('is-error');placeholder.querySelector('p').textContent='Questa illustrazione non è disponibile. Puoi continuare a sfogliare la galleria.';
    });
    image.src=asset(item,'webp');
    frame.append(placeholder,image);
    if(!preview)frame.append(node('span','art-open-mark','Guarda da vicino ↗'));
    return frame;
  }
  function showImage(index){
    currentIndex=(index+catalog.length)%catalog.length;
    const item=catalog[currentIndex];
    $('art-dialog-title').textContent=item.title;
    $('art-dialog-count').textContent='ILLUSTRAZIONI D’ATMOSFERA · '+(currentIndex+1)+' / '+catalog.length;
    $('art-dialog-caption').textContent=item.description;
    $('art-dialog-frame').replaceChildren(imageFrame(item,{eager:true,preview:true}));
    const download=$('art-dialog-download');download.href=asset(item,'png');download.download=item.id+'.png';
    history.replaceState(null,'','#'+item.id);
  }
  function openImage(index,trigger){
    if(!dialog.open){previousFocus=trigger||document.activeElement;previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';}
    showImage(index);
    if(!dialog.open)dialog.showModal();
    $('art-close').focus({preventScroll:true});
  }
  $('art-grid').replaceChildren(...catalog.map((item,index)=>{
    const article=node('article','art-card'),open=node('button','art-card-open');
    article.id='art-'+item.id;open.type='button';open.setAttribute('aria-label','Apri '+item.title);open.setAttribute('aria-haspopup','dialog');
    open.append(imageFrame(item,{eager:index<2}));open.addEventListener('click',()=>openImage(index,open));
    const copy=node('div','art-card-copy'),title=node('h2','',item.title);title.id='art-title-'+item.id;
    article.setAttribute('aria-labelledby',title.id);
    copy.append(node('p','art-kicker',item.kicker),title,node('p','',item.description));
    const tools=node('div','art-card-tools'),detail=node('button','art-button','Apri illustrazione ↗');detail.type='button';detail.setAttribute('aria-haspopup','dialog');
    detail.addEventListener('click',()=>openImage(index,detail));
    const download=node('a','art-download','Scarica PNG ↓');download.href=asset(item,'png');download.download=item.id+'.png';download.setAttribute('aria-label','Scarica PNG: '+item.title);
    tools.append(detail,download);copy.append(tools);article.append(open,copy);return article;
  }));
  $('art-close').addEventListener('click',()=>dialog.close());
  $('art-previous').addEventListener('click',()=>showImage(currentIndex-1));
  $('art-next').addEventListener('click',()=>showImage(currentIndex+1));
  dialog.addEventListener('keydown',event=>{
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();showImage(currentIndex+(event.key==='ArrowRight'?1:-1));}
  });
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;const bounds=dialog.getBoundingClientRect();
    if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)dialog.close();
  });
  dialog.addEventListener('close',()=>{
    document.body.style.overflow=previousOverflow;history.replaceState(null,'',location.pathname+location.search);
    if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});
  });
  const wanted=location.hash.slice(1),initial=catalog.findIndex(item=>item.id===wanted);
  if(initial>=0)openImage(initial,$('art-grid').querySelectorAll('.art-card-open')[initial]);
  window.addEventListener('hashchange',()=>{
    const index=catalog.findIndex(item=>item.id===location.hash.slice(1));
    if(index>=0)openImage(index,$('art-grid').querySelectorAll('.art-card-open')[index]);
    else if(dialog.open)dialog.close();
  });
})();
