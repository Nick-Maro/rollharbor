"""Private, deterministic dungeon cartography; SVG geometry is redacted before export.

This is a local cartography tool, not a Dungeon Scrawl API. Shapely performs
geometric unions/clipping; Playwright is optional and only rasterizes our SVG.
Nothing in this module changes the campaign, discovers rooms or moves tokens.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from html import escape
import json
import math
from pathlib import Path
import random
import sys

try:
    from shapely.affinity import rotate, scale
    from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box
    from shapely.ops import unary_union
except ImportError as exc:
    raise SystemExit("Il tool cartografico richiede Shapely (python -m pip install shapely). Il gioco non ne dipende.") from exc


ROOT = Path(__file__).resolve().parents[1]
STYLES = {
    'parchment': {'paper':'#dfd4b9','floor':'#f4eddb','ink':'#3c3932','grid':'#877d69','shadow':'#84745d','water':'#8baeb6','detail':'#7a6950'},
    'blueprint': {'paper':'#31576b','floor':'#e7edf0','ink':'#254559','grid':'#7394a5','shadow':'#193c50','water':'#78a6bb','detail':'#4d6b78'},
    'town': {'paper':'#c9c3ad','floor':'#ddd8c5','ink':'#4e5147','grid':'#777e70','shadow':'#777963','water':'#85a3a6','detail':'#7e765e'},
}


class MapError(ValueError):
    pass


def _number(value, name, lo=-1000, hi=1000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise MapError(f'{name}: numero finito fra {lo} e {hi}.')
    return value


def _points(value, name, minimum=2):
    if not isinstance(value, list) or not minimum <= len(value) <= 2048:
        raise MapError(f'{name}: servono da {minimum} a 2048 punti.')
    return [(_number(p[0],name),_number(p[1],name)) if isinstance(p,(list,tuple)) and len(p)==2 else
            (_ for _ in ()).throw(MapError(f'{name}: ogni punto deve contenere x e y.')) for p in value]


def validate(plan):
    if not isinstance(plan, dict):
        raise MapError('La pianta deve essere un oggetto JSON.')
    result = deepcopy(plan)
    grid = result.get('grid', {})
    for key in ('columns','rows'):
        value = grid.get(key)
        if isinstance(value,bool) or not isinstance(value,int) or not 1 <= value <= 200:
            raise MapError(f'grid.{key}: intero fra 1 e 200.')
    _number(grid.get('cell_m',1.5),'grid.cell_m',.1,100)
    if result.get('style','parchment') not in STYLES:
        raise MapError('Stile sconosciuto: parchment, blueprint o town.')
    ids = set()
    total_points=0
    for group in ('rooms','corridors','doors','props','labels'):
        values=result.setdefault(group,[])
        if not isinstance(values,list) or len(values)>2500:
            raise MapError(f'{group}: lista di massimo 2500 elementi.')
        for index,item in enumerate(values):
            if not isinstance(item,dict):
                raise MapError(f'{group}: gli elementi devono essere oggetti.')
            for key in ('hidden','secret','open','dm_only'):
                if key in item and not isinstance(item[key],bool):
                    raise MapError(f'{group}.{index}.{key}: usare true o false, non stringhe.')
            ident=item.get('id')
            if not isinstance(ident,str) or not ident or len(ident)>100 or ident in ids:
                raise MapError(f'{group}: ID non vuoto, univoco e lungo al massimo 100 caratteri.')
            ids.add(ident)
            if 'points' in item:
                _points(item['points'],f'{group}.{index}.points',3 if group=='rooms' else 2)
                total_points+=len(item['points'])
            if group=='rooms':
                shape=item.get('shape','rect')
                if shape not in ('rect','polygon','ellipse'):
                    raise MapError(f'{ident}: forma non supportata.')
                if shape=='polygon':
                    _points(item.get('points'),ident,3)
                else:
                    for key in ('x','y'):_number(item.get(key),ident+'.'+key)
                    for key in ('width','height'):_number(item.get(key),ident+'.'+key,.05,400)
            elif group=='corridors':
                _points(item.get('points'),ident)
                _number(item.get('width',1),ident+'.width',.1,50)
            elif group in ('props','doors','labels'):
                if 'points' not in item:
                    for key in ('x','y'):_number(item.get(key),ident+'.'+key)
                for key in ('width','height'):
                    if key in item:_number(item[key],ident+'.'+key,.05,400)
                if 'rotation' in item:_number(item['rotation'],ident+'.rotation',-360,360)
    if total_points>100000:
        raise MapError('Pianta troppo complessa: oltre 100000 vertici.')
    result.setdefault('id','local-map')
    result.setdefault('title','Mappa del dungeon')
    result.setdefault('seed',0)
    return result


def _room(item):
    shape=item.get('shape','rect')
    if shape=='polygon':
        geometry=Polygon(item['points'])
    elif shape=='ellipse':
        geometry=scale(Point(item['x']+item['width']/2,item['y']+item['height']/2).buffer(1,resolution=24),
                       item['width']/2,item['height']/2)
    else:
        geometry=box(item['x'],item['y'],item['x']+item['width'],item['y']+item['height'])
    if not geometry.is_valid:
        raise MapError(f"{item['id']}: poligono non valido o auto-intersecato.")
    return geometry


def _corridor(item):
    return LineString(item['points']).buffer(item.get('width',1)/2,cap_style=2,join_style=2)


def _eligible(item, audience, reveal_secrets):
    return audience=='dm' or reveal_secrets or not (item.get('hidden') is True or item.get('secret') is True or item.get('kind')=='secret')


def _n(value):
    return f'{value:.4f}'.rstrip('0').rstrip('.') or '0'


def _path(geometry):
    parts=[]
    if geometry.is_empty:return ''
    if geometry.geom_type=='Polygon':
        for ring in [geometry.exterior,*geometry.interiors]:
            coords=list(ring.coords)
            parts.append('M'+'L'.join(_n(x)+','+_n(y) for x,y in coords)+'Z')
    elif geometry.geom_type in ('MultiPolygon','GeometryCollection'):
        parts.extend(_path(part) for part in geometry.geoms)
    elif geometry.geom_type in ('LineString','LinearRing'):
        parts.append('M'+'L'.join(_n(x)+','+_n(y) for x,y in geometry.coords))
    elif geometry.geom_type=='MultiLineString':
        parts.extend(_path(part) for part in geometry.geoms)
    return ''.join(parts)


def _geometry(plan,audience,reveal,reveal_all,reveal_secrets,reveal_cells):
    bounds=box(0,0,plan['grid']['columns'],plan['grid']['rows'])
    known={item['id'] for item in plan['rooms']+plan['corridors']}
    unknown=set(reveal)-known
    if unknown:raise MapError('ID da rivelare non trovato: '+', '.join(sorted(unknown)))
    rooms=[item for item in plan['rooms'] if _eligible(item,audience,reveal_secrets)]
    corridors=[item for item in plan['corridors'] if _eligible(item,audience,reveal_secrets)]
    all_floor=unary_union([_room(item) for item in rooms]+[_corridor(item) for item in corridors]).intersection(bounds)
    if audience=='dm' or reveal_all:
        visible=all_floor
    else:
        shapes=[_room(item) for item in rooms if item['id'] in reveal]
        shapes += [_corridor(item) for item in corridors if item['id'] in reveal]
        for cell in reveal_cells:
            if not isinstance(cell,list) or len(cell)!=2 or any(isinstance(v,bool) or not isinstance(v,int) for v in cell):
                raise MapError('Le celle rivelate devono essere coppie di interi [x,y].')
            x,y=cell
            if not 0<=x<plan['grid']['columns'] or not 0<=y<plan['grid']['rows']:
                raise MapError('Cella rivelata fuori dai limiti.')
            shapes.append(box(x,y,x+1,y+1))
        visible=all_floor.intersection(unary_union(shapes))
    all_closed=unary_union([_room(item) for item in rooms if not item.get('open')]+[_corridor(item) for item in corridors if not item.get('open')])
    closed=all_closed.intersection(visible)
    # Only walls belonging to the displayed geometry exist in the output.
    # No hidden path, mask, source title or label is retained behind a fog layer.
    # A revelation frontier is not a new wall. Serialize only portions of real
    # boundaries intersecting the revealed geometry; never embed hidden paths.
    boundary=all_floor.boundary if not all_floor.is_empty else GeometryCollection()
    walls=boundary.intersection(all_closed.buffer(.00001)).intersection(visible.buffer(.00001))
    return visible,closed,walls,bounds


def _prop(item,visible,palette,audience,reveal_secrets,selected,all_visible):
    if not _eligible(item,audience,reveal_secrets):return ''
    if audience=='players' and item.get('room_id') and not all_visible and item['room_id'] not in selected:return ''
    kind=item.get('type','crate')
    ink=palette['ink'];wood=palette['detail']
    x=item.get('x',0);y=item.get('y',0);w=item.get('width',1);h=item.get('height',1)
    if kind=='water':
        water=LineString(item['points']).buffer(w/2,cap_style=1,join_style=1) if item.get('points') else box(x,y,x+w,y+h)
        water=water.intersection(visible)
        if water.is_empty:return ''
        d=_path(water)
        return f'<path d="{d}" fill="{palette["water"]}" stroke="{ink}" stroke-width=".035"/><path d="{d}" fill="url(#water-ripples)"/>'
    footprint=box(x,y,x+w,y+h)
    if item.get('rotation'):footprint=rotate(footprint,item['rotation'],origin=(x+w/2,y+h/2))
    if footprint.is_empty or not visible.buffer(.03).covers(footprint):return ''
    common=f'fill="{wood}" stroke="{ink}" stroke-width=".05" stroke-linejoin="round"'
    pieces=[]
    if kind=='stairs':
        pieces.append(f'<rect x=".04" y=".04" width="{_n(w-.08)}" height="{_n(h-.08)}" fill="none" stroke="{ink}" stroke-width=".05"/>')
        count=max(4,round(h*4))
        for index in range(count):
            yy=h*(index+.5)/count;inset=.06+index/count*min(.32,w*.2)
            pieces.append(f'<path d="M{_n(inset)},{_n(yy)}H{_n(w-inset)}" fill="none" stroke="{ink}" stroke-width=".035"/>')
        pieces.append(f'<path d="M{_n(w/2)},{_n(h*.15)}V{_n(h*.85)}m-.13,-.2 .13,.2 .13,-.2" fill="none" stroke="{ink}" stroke-width=".045"/>')
    elif kind=='bridge':
        for index in range(max(3,round(h*4))):
            yy=h*index/max(3,round(h*4))
            pieces.append(f'<rect x=".03" y="{_n(yy)}" width="{_n(w-.06)}" height="{_n(h/max(3,round(h*4))-.035)}" rx=".035" {common} fill-opacity=".55"/>')
        pieces.append(f'<path d="M.12,0V{_n(h)}M{_n(w-.12)},0V{_n(h)}" fill="none" stroke="{ink}" stroke-width=".065"/>')
    elif kind in ('pillar','barrel'):
        pieces.append(f'<ellipse cx="{_n(w/2)}" cy="{_n(h/2)}" rx="{_n(w*.44)}" ry="{_n(h*.44)}" {common} fill-opacity=".35"/>')
        if kind=='pillar':
            pieces.append(f'<ellipse cx="{_n(w/2)}" cy="{_n(h/2)}" rx="{_n(w*.3)}" ry="{_n(h*.3)}" fill="{palette["floor"]}" stroke="{ink}" stroke-width=".035"/>')
        else:
            for yy in (.28,.72):pieces.append(f'<path d="M{_n(w*.15)},{_n(h*yy)}H{_n(w*.85)}" stroke="{ink}" stroke-width=".04"/>')
    elif kind=='rubble':
        rng=random.Random(str(item['id']))
        for _ in range(max(5,int(w*h*4))):
            xx=rng.uniform(.1,max(.11,w-.1));yy=rng.uniform(.1,max(.11,h-.1));r=rng.uniform(.06,.17)
            pieces.append(f'<path d="M{_n(xx-r)},{_n(yy)}l{_n(r*.6)},{_n(-r)} { _n(r*1.2)},{_n(r*.15)} {_n(r*.35)},{_n(r)} {_n(-r)},{_n(r*.5)}Z" {common} fill-opacity=".4"/>')
    elif kind in ('table','altar','bed','minecart','crate','chest','bookcase','coffin'):
        pieces.append(f'<rect x=".06" y=".06" width="{_n(max(.05,w-.12))}" height="{_n(max(.05,h-.12))}" rx=".08" {common} fill-opacity=".38"/>')
        if kind=='bed':
            pieces.append(f'<rect x="{_n(w*.15)}" y="{_n(h*.12)}" width="{_n(w*.7)}" height="{_n(h*.24)}" rx=".09" fill="{palette["floor"]}" stroke="{ink}" stroke-width=".03"/><path d="M{_n(w*.12)},{_n(h*.42)}H{_n(w*.88)}" stroke="{ink}" stroke-width=".04"/>')
        elif kind=='altar':
            pieces.append(f'<path d="M{_n(w*.3)},{_n(h/2)}H{_n(w*.7)}M{_n(w/2)},{_n(h*.25)}V{_n(h*.75)}" stroke="{ink}" stroke-width=".055"/>')
        elif kind=='bookcase':
            for offset in (.32,.66):
                pieces.append(f'<path d="M.1,{_n(h*offset)}H{_n(w-.1)}" stroke="{ink}" stroke-width=".035"/>')
            for index in range(max(3,int(w*5))):
                xx=(index+.5)*w/max(3,int(w*5))
                pieces.append(f'<path d="M{_n(xx)},.12V{_n(h*.27)}M{_n(xx+.025)},{_n(h*.4)}V{_n(h*.6)}M{_n(xx-.015)},{_n(h*.73)}V{_n(h-.12)}" stroke="{ink}" stroke-width=".025"/>')
        elif kind=='coffin':
            pieces.append(f'<path d="M{_n(w*.5)},{_n(h*.25)}V{_n(h*.75)}M{_n(w*.3)},{_n(h*.4)}H{_n(w*.7)}" stroke="{ink}" stroke-width=".045"/>')
        elif kind in ('crate','chest'):
            pieces.append(f'<path d="M.1,.1L{_n(w-.1)},{_n(h-.1)}M.1,{_n(h-.1)}L{_n(w-.1)},.1" fill="none" stroke="{ink}" stroke-width=".035"/>')
        elif kind=='table':
            pieces.append(f'<ellipse cx="{_n(w*.3)}" cy="{_n(h*.5)}" rx=".13" ry=".13" fill="{palette["floor"]}" stroke="{ink}" stroke-width=".03"/><path d="M{_n(w*.62)},{_n(h*.25)}l.15,.07 -.07,.3 -.15,-.07Z" fill="{palette["floor"]}" stroke="{ink}" stroke-width=".03"/>')
        else:
            pieces.append(f'<path d="M.03,{_n(h*.2)}H{_n(w-.03)}M.03,{_n(h*.8)}H{_n(w-.03)}" stroke="{ink}" stroke-width=".1"/>')
    else:
        return ''
    transform=f'translate({_n(x)} {_n(y)})'
    if item.get('rotation'):transform+=f' rotate({_n(item["rotation"])} {_n(w/2)} {_n(h/2)})'
    return '<g transform="'+transform+'">'+''.join(pieces)+'</g>'


def render_svg(plan, *, audience='dm', reveal=(), reveal_all=False, reveal_secrets=False, reveal_cells=(), cell_px=64):
    plan=validate(plan)
    if audience not in ('dm','players'):raise MapError('Audience non valida.')
    if not isinstance(cell_px,int) or isinstance(cell_px,bool) or not 8<=cell_px<=160:raise MapError('cell_px deve essere un intero fra 8 e 160.')
    if len(reveal_cells)>40000:raise MapError('Troppe celle rivelate.')
    visible,closed,walls,bounds=_geometry(plan,audience,set(reveal),reveal_all,reveal_secrets,reveal_cells)
    cols=plan['grid']['columns'];rows=plan['grid']['rows'];palette=STYLES[plan.get('style','parchment')]
    ink=palette['ink'];floor=palette['floor'];path=_path(visible);wall_path=_path(walls)
    title=str(plan.get('player_title','Mappa esplorata') if audience=='players' else plan['title'])
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols*cell_px}" height="{rows*cell_px}" viewBox="0 0 {cols} {rows}" role="img" aria-label="{escape(title,quote=True)}">',
        '<title>'+escape(title)+'</title>',
        f'<defs><pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M1 0H0V1" fill="none" stroke="{palette["grid"]}" stroke-width=".012" opacity=".48"/></pattern>',
        f'<pattern id="hatch" width=".48" height=".48" patternUnits="userSpaceOnUse" patternTransform="rotate(-27)"><path d="M.05,-.15V.64M.19,-.1V.6M.36,-.14V.66" stroke="{ink}" stroke-width=".025" opacity=".7"/></pattern>',
        f'<pattern id="paper" width="2.4" height="2.4" patternUnits="userSpaceOnUse"><path d="M.12,.36h.025M1.5,1.1h.035M.7,1.8h.025M2,2.1h.035" stroke="{ink}" stroke-width=".035" opacity=".11"/></pattern>',
        f'<pattern id="paving" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M0,.33H1M0,.67H1M.27,0V.33M.76,0V.33M.1,.33V.67M.6,.33V.67M.36,.67V1M.86,.67V1" fill="none" stroke="{palette["grid"]}" stroke-width=".017" opacity=".35"/></pattern>',
        f'<pattern id="water-ripples" width="1.3" height=".6" patternUnits="userSpaceOnUse"><path d="M.06,.2q.12,-.055 .25,0m.22,.19q.2,-.06 .38,0" fill="none" stroke="{floor}" stroke-width=".045" opacity=".55"/></pattern>',
        f'<clipPath id="visible-floor"><path d="{path}" fill-rule="evenodd"/></clipPath></defs>',
        f'<rect width="{cols}" height="{rows}" fill="{palette["paper"]}"/><rect width="{cols}" height="{rows}" fill="url(#paper)"/>']
    if not walls.is_empty:
        band=walls.buffer(.66,join_style=2,cap_style=2).difference(visible).intersection(bounds)
        # Clipped geometry is derived from revealed space only.
        parts.append(f'<path d="{_path(band)}" fill="url(#hatch)"/>')
        parts.append(f'<path d="{wall_path}" fill="none" stroke="{palette["shadow"]}" stroke-width=".31" opacity=".22" stroke-linejoin="round"/>')
    parts.append(f'<path d="{path}" fill="{floor}" fill-rule="evenodd"/>')
    paving=visible if plan.get('style')=='town' else unary_union([
        _room(item).intersection(visible) for item in plan['rooms'] if item.get('floor')=='cobblestone'
        and _eligible(item,audience,reveal_secrets) and (audience=='dm' or reveal_all or item['id'] in reveal)])
    if not paving.is_empty:
        parts.append(f'<path d="{_path(paving)}" fill="url(#paving)"/>')
    parts.append(f'<path d="{path}" fill="url(#paper)"/>')
    # Geometry has already been redacted; this clip just keeps props within floors.
    warnings=[]
    props=sorted(plan['props'],key=lambda p:0 if p.get('type')=='water' else 1)
    for item in props:
        rendered=_prop(item,visible,palette,audience,reveal_secrets,set(reveal),audience=='dm' or reveal_all)
        parts.append(rendered)
        if audience=='dm' and not rendered:
            warnings.append({'id':item['id'],'code':'prop_not_rendered','detail':'Arredo fuori dal pavimento o tipo non supportato: verificare posizione, dimensioni e rotazione.'})
    parts.append(f'<path d="{path}" fill="url(#grid)"/>')
    if not walls.is_empty:
        parts.append(f'<path d="{wall_path}" fill="none" stroke="{ink}" stroke-width=".12" stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<path d="{wall_path}" fill="none" stroke="{floor}" stroke-width=".025" opacity=".42" stroke-linejoin="round"/>')
    for item in plan['doors']:
        if not _eligible(item,audience,reveal_secrets):continue
        if audience=='players' and item.get('room_id') and not reveal_all and item['room_id'] not in reveal:continue
        x=item['x'];y=item['y'];w=item.get('width',1)
        angle=90 if item.get('orientation')=='vertical' else 0
        door_line=LineString([(x,y-w/2),(x,y+w/2)]) if angle else LineString([(x-w/2,y),(x+w/2,y)])
        if not visible.buffer(.15).covers(door_line):continue
        if item.get('kind')=='secret' and audience=='players' and not reveal_secrets:continue
        parts.append(f'<g transform="translate({_n(x)} {_n(y)}) rotate({angle})"><path d="M{_n(-w/2)},0H{_n(w/2)}" stroke="{floor}" stroke-width=".3"/>')
        parts.append(f'<rect x="{_n(-w/2+.04)}" y="-.09" width="{_n(w-.08)}" height=".18" fill="{palette["detail"]}" stroke="{ink}" stroke-width=".045"/>')
        if item.get('kind')=='secret':
            parts.append(f'<text x="0" y="-.23" text-anchor="middle" font-family="Georgia,serif" font-size=".38" fill="{ink}">S</text>')
        parts.append('</g>')
    for label in plan['labels']:
        if not _eligible(label,audience,reveal_secrets):continue
        if audience=='players' and label.get('room_id') and not reveal_all and label['room_id'] not in reveal:continue
        if not visible.covers(Point(label['x'],label['y'])):continue
        # DM labels and source references never sneak into a player file.
        if audience=='players' and label.get('dm_only',False):continue
        size=_number(label.get('size',.5),'label.size',.15,3)
        parts.append(f'<text x="{_n(label["x"])}" y="{_n(label["y"])}" text-anchor="middle" font-family="Georgia,serif" font-size="{_n(size)}" fill="{ink}" stroke="{floor}" stroke-width=".08" paint-order="stroke">{escape(str(label.get("text","")))}</text>')
    parts.append('</svg>')
    svg=''.join(parts)
    metadata={'format':'dnd-dungeon-map-v1','audience':audience,'title':title,
              'grid':{**plan['grid'],'confirmed':False},'cell_px':cell_px,
              'width_px':cols*cell_px,'height_px':rows*cell_px,'visible_floor_area':round(visible.area,3),
              'svg_sha256':hashlib.sha256(svg.encode('utf-8')).hexdigest(),
              'renderer':'local-shapely-svg','canonical':False}
    if audience=='dm':metadata.update(id=plan['id'],source=plan.get('source'),note=plan.get('note'),warnings=warnings)
    return svg,metadata


def write_png(svg_path,png_path,width,height):
    if max(width,height)>16384 or width*height>64000000:
        raise MapError('PNG oltre 16384 pixel per lato o 64 megapixel: ridurre --cell-px. SVG resta scalabile.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise MapError('Per il PNG serve Playwright con Chromium. SVG non richiede Playwright.') from exc
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':min(width,1200),'height':min(height,900)},device_scale_factor=1)
            page.set_content('<!doctype html><meta charset="utf-8"><style>body{margin:0}svg{display:block;max-width:none}</style>'+svg_path.read_text(encoding='utf-8'))
            page.locator('svg').screenshot(path=str(png_path),timeout=60000)
        finally:browser.close()


def export(plan,out,**options):
    png=options.pop('png',False)
    svg,metadata=render_svg(plan,**options)
    out=Path(out)
    if out.suffix in ('.svg','.png','.json'):out=out.with_suffix('')
    # A private export must not be accidentally written into the HTTP document root.
    if options.get('audience','dm')=='dm' and out.resolve().is_relative_to((ROOT/'web').resolve()):
        raise MapError('La mappa DM completa non può essere esportata dentro web/.')
    out.parent.mkdir(parents=True,exist_ok=True)
    svg_path=out.with_suffix('.svg');json_path=out.with_suffix('.map.json')
    svg_path.write_text(svg,encoding='utf-8')
    json_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'svg':str(svg_path),'metadata':str(json_path),**metadata}
    if png:
        png_path=out.with_suffix('.png')
        write_png(svg_path,png_path,metadata['width_px'],metadata['height_px'])
        result['png']=str(png_path)
    return result


def example_plan():
    """An original, optional 80×60 map. It is not a location in Phandelver."""
    rooms=[];corridors=[];props=[];labels=[];doors=[]
    def room(ident,name,x,y,w,h,**extra):
        rooms.append({'id':ident,'name':name,'shape':'rect','x':x,'y':y,'width':w,'height':h,**extra})
        labels.append({'id':'label-'+ident,'room_id':ident,'x':x+w/2,'y':y+1.1,'text':name,'size':.43})
    def prop(ident,kind,room_id,x,y,w,h,**extra):
        props.append({'id':ident,'type':kind,'room_id':room_id,'x':x,'y':y,'width':w,'height':h,**extra})
    def passage(ident,points,width=2):
        corridors.append({'id':ident,'points':points,'width':width})
    room('library','Archivio',4,4,13,9)
    room('scriptorium','Scrittorio',5,17,10,8)
    room('gate','Ingresso',3,29,12,9)
    room('kitchen','Cucine',4,43,12,10)
    room('chapel','Cappella',23,4,18,14)
    rooms.append({'id':'apse','shape':'ellipse','x':29,'y':1,'width':6,'height':6})
    room('sacristy','Sagrestia',45,4,10,7)
    room('cells','Celle',45,14,9,7)
    room('north-gallery','Galleria',19,20,22,3)
    room('south-gallery','Portico',19,39,22,3)
    room('west-gallery','',18,23,3,16)
    room('east-gallery','',39,23,3,16)
    room('courtyard','Cortile',24,26,11,9,open=True,floor='cobblestone')
    room('refectory','Refettorio',22,46,18,9)
    room('crypt','Cripta',46,43,11,11)
    rooms.append({'id':'rotunda','name':'Rotonda','shape':'ellipse','x':46,'y':27,'width':10,'height':10})
    labels.append({'id':'label-rotunda','room_id':'rotunda','x':51,'y':29,'text':'Rotonda','size':.43})
    # Looped galleries and genuinely distinct side rooms.
    for ident,points,width in [
        ('archive-link',[[17,9],[20,9],[20,21]],2),
        ('chapel-link',[[32,18],[32,21]],3),
        ('scriptorium-link',[[10,25],[10,27],[19.5,27]],2),
        ('gate-link',[[15,33.5],[19.5,33.5]],3),
        ('kitchen-link',[[10,43],[10,40],[19.5,40]],2),
        ('refectory-link',[[31,42],[31,46]],3),
        ('sacristy-link',[[41,8],[45,8]],2),
        ('cells-link',[[41,16.5],[45,17.5]],1.5),
        ('court-west',[[21,30.5],[24,30.5]],2),
        ('court-east',[[35,30.5],[39,30.5]],2),
        ('rotunda-link',[[42,32],[46,32]],2),
        ('crypt-link',[[40,50],[46,50]],2),
        ('rotunda-crypt',[[51,37],[51,43]],1.5)]:passage(ident,points,width)
    # Furniture belongs to each room's function and sits in useful clusters.
    for i,xx in enumerate((4.5,8.4,12.3)):
        prop('shelf-'+str(i),'bookcase','library',xx,4.5,3.1,1.4)
        prop('shelf-bottom-'+str(i),'bookcase','library',xx,10.8,3.1,1.4)
    prop('archive-desk','table','library',8.8,7.5,3.2,1.5)
    for i,xx in enumerate((5.7,10.3)):
        for j,yy in enumerate((18.6,22.1)):
            prop(f'desk-{i}-{j}','table','scriptorium',xx,yy,3,1.5)
    prop('entry-stairs','stairs','gate',3.4,31.5,2.4,4.8)
    prop('gate-bench','table','gate',9,35.9,4.8,1)
    prop('gate-stores','crate','gate',12.5,30.3,1.4,1.4)
    for i,xx in enumerate((5,7.3,9.6,12)):
        prop('kitchen-barrel-'+str(i),'barrel','kitchen',xx,50.8,1,1.4)
    prop('kitchen-counter','table','kitchen',4.7,44.9,1.6,4.6)
    prop('kitchen-table','table','kitchen',9.2,46,4.8,1.7)
    for i,xx in enumerate((24.5,37)):
        for j,yy in enumerate((8,12,15)):
            prop(f'nave-column-{i}-{j}','pillar','chapel',xx,yy,1,1)
    prop('chapel-altar','altar','chapel',29.3,4.3,5.2,1.6)
    for i,xx in enumerate((27,33.5)):
        for j,yy in enumerate((9,12.2,15.3)):
            prop(f'pew-{i}-{j}','table','chapel',xx,yy,3.7,.7)
    prop('sacristy-chest','chest','sacristy',46,5.7,2,1.3)
    prop('sacristy-desk','table','sacristy',51.8,6,1.6,3)
    for i,xx in enumerate((45.6,48.2,50.8)):
        prop('cell-bed-'+str(i),'bed','cells',xx,15.9,1.5,3.5)
    prop('court-fountain','water','courtyard',27.5,28.5,4,3.8)
    for i,xx in enumerate((25.1,33.1)):
        for j,yy in enumerate((26.5,33)):
            prop(f'court-column-{i}-{j}','pillar','courtyard',xx,yy,.8,.8)
    for i,yy in enumerate((48,51.5)):
        prop('refectory-table-'+str(i),'table','refectory',24,yy,13,1.7)
    for i,xx in enumerate((46.6,54.1)):
        for j,yy in enumerate((45.5,49.4)):
            prop(f'coffin-{i}-{j}','coffin','crypt',xx,yy,2.2,3.3)
    prop('crypt-stairs','stairs','crypt',50,50,2.1,3.4)
    for i,xx in enumerate((48.1,52.8)):
        prop('rotunda-pillar-'+str(i),'pillar','rotunda',xx,31.1,1,1)
    # Curving cisterns east of the abbey form a second route through the map.
    for i,(x,y,w,h) in enumerate([(62,4,13,11),(64,21,11,10),(59,35,14,11),(63,49,12,8)]):
        ident='cave-'+str(i)
        points=[[x+w*.1,y+h*.2],[x+w*.4,y],[x+w*.8,y+h*.08],[x+w,y+h*.4],
                [x+w*.9,y+h*.8],[x+w*.6,y+h],[x+w*.2,y+h*.88],[x,y+h*.5]]
        rooms.append({'id':ident,'name':'Grotta','shape':'polygon','points':points})
        prop('rubble-'+ident,'rubble',ident,x+w*.6,y+h*.5,2,2)
    for i,points in enumerate([[[55,8],[63,9]],[[69,14],[69,22]],[[69,30],[69,36]],
                               [[56,32],[61,39]],[[57,50],[64,52]],[[68,45],[68,50]]]):passage('cave-link-'+str(i),points,2)
    props.extend([{'id':'long-pool','room_id':'cave-2','type':'water','points':[[64,36],[65,39],[68,42],[69,44]],'width':3},
                  {'id':'cistern-upper','room_id':'cave-0','type':'water','points':[[66,7],[68,9],[71,10]],'width':3.4},
                  {'id':'bridge','room_id':'cave-2','type':'bridge','x':62.5,'y':39,'width':7,'height':1.4,'rotation':12}])
    # Doors only where rooms actually connect, never unexplained exits to void.
    for i,(x,y,orientation,room_id) in enumerate([(17,9,'vertical','library'),(10,25,'horizontal','scriptorium'),
            (15,33.5,'vertical','gate'),(10,43,'horizontal','kitchen'),(32,18,'horizontal','chapel'),
            (45,8,'vertical','sacristy'),(45,17.5,'vertical','cells'),(31,46,'horizontal','refectory'),
            (46,50,'vertical','crypt'),(51,43,'horizontal','crypt')]):
        doors.append({'id':'door-'+str(i),'x':x,'y':y,'orientation':orientation,'room_id':room_id})
    return {'id':'original-abbey-80x60','title':'L\u2019abbazia della Bussola — esempio originale','player_title':'L\u2019abbazia e le cisterne',
            'grid':{'columns':80,'rows':60,'cell_m':1.5},'style':'parchment','seed':742,
            'rooms':rooms,'corridors':corridors,'doors':doors,'props':props,'labels':labels,
            'source':{'kind':'original','author':'Codex','campaign_location':False},
            'note':'Mappa di esempio facoltativa: nessun luogo, incontro o segreto della campagna attiva.'}


def main():
    parser=argparse.ArgumentParser(description='Cartografia locale per il master: grandi mappe SVG e PNG con redazione delle parti non rivelate.')
    sub=parser.add_subparsers(dest='command',required=True)
    render=sub.add_parser('render',help='Disegna una pianta privata JSON.')
    render.add_argument('plan',type=Path)
    render.add_argument('--out',type=Path,required=True,help='Prefisso dei file di uscita.')
    render.add_argument('--audience',choices=('dm','players'),default='dm')
    render.add_argument('--reveal',action='append',default=[],help='ID di stanza o corridoio effettivamente conosciuto; ripetibile.')
    render.add_argument('--reveal-all',action='store_true',help='Esplicita che tutte le aree non segrete sono visibili.')
    render.add_argument('--reveal-secrets',action='store_true',help='Consente elementi hidden/secret; riservato alle scoperte già risolte dal DM.')
    render.add_argument('--reveal-cells',type=Path,help='JSON con coppie [x,y] delle caselle rivelate.')
    render.add_argument('--cell-px',type=int,default=64)
    render.add_argument('--png',action='store_true')
    example=sub.add_parser('example',help='Scrive soltanto una pianta originale di esempio 80×60.')
    example.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='example':
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(json.dumps(example_plan(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            result={'plan':str(args.out),'campaign_changed':False}
        else:
            plan=json.loads(args.plan.read_text(encoding='utf-8-sig'))
            cells=json.loads(args.reveal_cells.read_text(encoding='utf-8-sig')) if args.reveal_cells else []
            if not isinstance(cells,list):raise MapError('Le celle devono essere una lista.')
            result=export(plan,args.out,audience=args.audience,reveal=args.reveal,reveal_all=args.reveal_all,
                          reveal_secrets=args.reveal_secrets,reveal_cells=cells,cell_px=args.cell_px,png=args.png)
        print(json.dumps({'ok':True,**result},ensure_ascii=True))
    except (MapError,OSError,ValueError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=True),file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
