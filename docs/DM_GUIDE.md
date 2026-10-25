# Guida del master

La plancia conserva e mostra lo stato; il master conduce il mondo, applica le
regole e lascia decidere i quattro giocatori. Il demo originale è un punto di
partenza da espandere. Per una campagna diversa fornite le vostre fonti e mantenete
distinte le regole generali, gli adattamenti e gli appunti riservati.

## Ingresso e ripresa

Leggete `AGENTS.md`, gli accordi `rules.md`, `handoff.md`, `master/CURRENT.md` e la
memoria privata. Alcuni file vengono creati al primo avvio. Poi:

```bash
python tools/play.py context
```

Il risultato è riservato al DM: comprende schede, scena, revisione, intenzioni e
diario incrementale. Il salvataggio effettivo prevale su un riepilogo vecchio.
Se il diario segnala eventi omessi, recuperateli con
`python tools/turn_log.py context --limit 0`. Nella stessa chat già informata
`python tools/play.py context --brief` riduce la lettura.

## Un'intenzione alla volta

1. Identificate chi agisce, cosa vuole ottenere e quali prerequisiti contano.
2. Verificate fonte, distanze, copertura, risorse e finestre delle reazioni.
3. Richiedete dadi solo per un'incertezza con conseguenze; usate i dadi reali.
4. Applicate il comando adatto con revisione corrente e ID stabile.
5. Verificate il successo del salvataggio, narrate l'esito e lasciate la prossima scelta.

```bash
python tools/play.py --help
python tools/play.py attack --help
```

Il [playbook](../tools/PLAYBOOK.md) descrive i comandi, i limiti e i casi che
richiedono una decisione intermedia. I nomi e le revisioni nei suoi esempi sono
illustrativi, non dati del demo. Non ripetete un tiro o un commit già riuscito
per correggere un errore successivo del diario.

Gli incontri vengono cercati in `campaigns/<campaign_id>/prepared/encounters.json`
per la campagna corrente. Nel demo, `prepare porto` mostra una preparazione vuota
senza attivare incontri. Nessun catalogo deve predeterminare mosse o risultati.

## Pubblico e privato

Tutto `data/campaign.json`, compresi `flags` e `combat`, e `data/world.json` sono
pubblici nella plancia. Tenete PF nascosti, CD segrete, motivazioni e informazioni
non ancora ottenute solo in `master/`. Le API non servono la cartella del master.
La riservatezza non protegge da chi ha accesso diretto al filesystem.

Le pedine trascinate sono proposte. Il DM salva il movimento risolto, aggiornando
coordinate e distanze coerentemente. Un clic sulla carta non fa viaggiare il gruppo.

## Pausa e continuità

Salvate gli esiti e le risorse; eseguite `python tools/dnd.py snapshot`. Aggiornate
il resoconto pubblico in `sessions/`, la memoria privata e `handoff.md`, includendo
revisione effettiva, posizione, turno, scelte pendenti e ultimo evento incorporato.
Solo dopo marcate il checkpoint del diario. Una nuova chat riprende da qui senza
rigiocare scene, assegnare ricompense doppie o ripristinare risorse.
