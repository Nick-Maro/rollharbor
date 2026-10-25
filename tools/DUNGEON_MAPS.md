# Cartografia del master

`dungeon_maps.py` è il tool locale dedicato alle mappe del tavolo. Produce pareti unite geometricamente, tratteggio esterno, griglia, pavimenti, porte, scale, arredi, grotte poligonali e corsi d'acqua. La direzione visiva richiama la cartografia di Dungeon Scrawl; il generatore è nostro e **non è un'API né un esportatore `.ds` di Dungeon Scrawl**.


## Uso

```powershell
python tools/dungeon_maps.py render campaigns/demo/maps/PIANTA.json --out campaigns/demo/maps/private/NOME-dm --audience dm --png
python tools/dungeon_maps.py render campaigns/demo/maps/PIANTA.json --out web/assets/maps/NOME-player --audience players --reveal stanza-1 --reveal corridoio-1 --png
```

Il master indica soltanto stanze e corridoi già rivelati nella fiction. Non basta aprire il file per scoprire un luogo. `--reveal` è ripetibile; `--reveal-cells FILE` legge un array di coppie intere `[x,y]` per rivelazioni parziali. Senza selezione il file giocatori è vuoto, non l'intera mappa. `--reveal-all` è un'opzione esplicita per mostrare tutte le parti ordinarie; **non mostra elementi `hidden`/`secret`**. Questi richiedono anche `--reveal-secrets`, da usare soltanto dopo la relativa scoperta.

Gli output sono `NOME.svg`, `NOME.map.json` e, con `--png`, `NOME.png`. I PNG usano 64 pixel per casella per impostazione iniziale: 80×60 caselle producono **5120×3840 px**. `--cell-px 96` o `128` permette risoluzioni maggiori entro 64 megapixel e 16384 pixel per lato. L'SVG resta vettoriale a qualsiasi zoom. La griglia arriva fino a 200×200; per grandi PNG può servire ridurre la densità pixel.

Il `viewBox` dell'SVG coincide esattamente con `0 0 columns rows`: non contiene margini o titoli esterni che spostino le pedine. I metadati hanno scala, dimensioni, audience e SHA-256 dell'SVG. `confirmed:false` e `canonical:false` ricordano che esportare non approva una posizione, non cambia la campagna e non assegna geometria canonica alla fonte. Nei metadati privati `warnings` elenca gli arredi non disegnati perché fuori dal pavimento o di tipo non supportato.

## Formato della pianta

```json
{
  "id": "mappa-privata",
  "title": "Titolo completo del master",
  "player_title": "Titolo già noto ai giocatori",
  "style": "parchment",
  "grid": {"columns": 40, "rows": 30, "cell_m": 1.5},
  "rooms": [
    {"id": "sala", "shape": "rect", "x": 2, "y": 2, "width": 8, "height": 6},
    {"id": "grotta", "shape": "polygon", "points": [[15,4],[18,2],[23,4],[22,9],[16,10]]}
  ],
  "corridors": [{"id": "passaggio", "points": [[10,5],[16,5]], "width": 2}],
  "doors": [{"id": "porta", "room_id": "sala", "x": 10, "y": 5, "orientation": "vertical"}],
  "props": [{"id": "tavolo", "room_id": "sala", "type": "table", "x": 4, "y": 4, "width": 3, "height": 1.5}],
  "labels": [{"id": "numero-sala", "room_id": "sala", "x": 6, "y": 3, "text": "1", "dm_only": true}],
  "source": {"kind": "original", "note": "Oppure riferimenti verificati della fonte."}
}
```

Ogni elemento richiede un ID univoco. Le coordinate sono caselle, da zero; i poligoni possono avere coordinate frazionarie. `ellipse` usa `x/y/width/height` come `rect`. `open:true` disegna un pavimento senza inventare un muro perimetrale: utile per piazze, strade e cortili. `floor:"cobblestone"` aggiunge la pavimentazione soltanto alla stanza pertinente. Stili: `parchment`, `blueprint`, `town`.

Arredi: `stairs`, `table`, `bookcase`, `pillar`, `barrel`, `crate`, `chest`, `altar`, `bed`, `coffin`, `minecart`, `rubble`, `bridge`, `water`. `rotation` ruota un arredo intorno al suo centro. L'acqua può essere un rettangolo oppure un percorso `points` con larghezza `width`. Un ponte è disegnato dopo l'acqua. Gli arredi solidi il cui ingombro non entra nel pavimento visibile sono omessi; il master riceve un avviso nel file privato.

`hidden`, `secret`, `open` e `dm_only` sono booleani veri, non stringhe. `room_id` lega un arredo/etichetta/porta alla scoperta della stanza. Per le etichette DM usare `dm_only:true`. Le porte segrete usano `kind:"secret"`; non vengono mostrate per il solo `--reveal-all`.

## Segreti e fonte

La geometria dei giocatori viene **ritagliata prima di serializzare SVG/PNG**: il layout completo non è nascosto sotto un rettangolo, una maschera CSS o dentro l'immagine scaricabile. Titolo privato, fonte, nomi di stanze non rivelate, oggetti e label riservati non vengono aggiunti all'output pubblico. Il limite tra spazio rivelato e spazio ignoto non crea un falso muro; vengono esportati soltanto tratti di pareti reali visibili. Il tool rifiuta un export DM direttamente sotto `web/`.

Conservare piante complete e export DM in `campaigns/demo/maps/`; copiare sotto `web/assets/maps/` soltanto output `players` già verificati. Le mappe della fonte si ricostruiscono dopo averne letto le immagini originali, mantenendo riferimenti e distinzione tra geometria verificata e approssimazione grafica. Non pubblicare in anticipo il catalogo dei dungeon della campagna.

`campaigns/demo/maps/examples/original-abbey-80x60.*` è una grande **mappa originale facoltativa**, non un luogo già scoperto. Non implica missioni, incontri, risorse o luoghi scoperti. La pianta si rigenera con:

```powershell
python tools/dungeon_maps.py example --out campaigns/demo/maps/examples/original-abbey-80x60.json
```

## Dipendenze e verifica

Il generatore richiede **Shapely**. Per PNG serve anche **Playwright con Chromium**. Queste dipendenze appartengono al tool cartografico del master; il tavolo continua ad avviarsi con la sola libreria standard. Non servono chiavi API.

```powershell
python -m unittest discover -s tests -p test_dungeon_maps.py -v
```

I controlli coprono redazione dei segreti anche nel sorgente SVG, selezione delle aree, porte segrete, pavimenti aperti, frontiere di esplorazione, limiti di dimensione, avvisi sugli arredi, isolamento della directory pubblica e dimensioni effettive dei PNG.
