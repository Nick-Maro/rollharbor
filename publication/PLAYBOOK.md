# Comandi pronti del master

Si gioca parlando in chat. Questi comandi sono strumenti privati del DM, da eseguire dalla cartella del tavolo; i loro risultati possono contenere statistiche e informazioni riservate. Per la conduzione valgono `../rules.md`, la fonte 2014 e `../AGENTS.md`.

Leggere una volta `python tools/play.py --help`. Durante un turno normale:

1. `python tools/play.py context` all'ingresso nella chat: acquisire revisione corrente, scena, schede, turno e continuità privata. Nei turni della stessa chat già informata usare `python tools/play.py context --brief`: conserva stato, schede, risorse e combattimento completo, limitando la cronologia agli ultimi quattro eventi senza i vecchi payload ripetuti. La cronologia esclusa resta nel diario ed è segnalata; dopo perdita del contesto tornare alla lettura completa.
2. Eseguire il comando pertinente con `--expected-revision N` e `--id ID_UNIVOCO`, sostituendo i segnaposto con valori reali. Nei ritentativi conservare lo stesso ID e gli stessi argomenti; una nuova operazione richiede un nuovo ID.
3. Leggere l'esito compatto e rispondere con conseguenza e prossima scelta. I comandi gestiscono gli effetti coperti e il diario: non risalvarli o rigiocarli con gli strumenti di basso livello.

Non creare un nuovo script Python, avviare test o riavviare il server per ogni mossa. Una domanda fuori gioco senza conseguenze non richiede un comando che modifica i dati. I riepiloghi Markdown si consolidano a fine scena, pausa o cambio chat.

| Comando | Forma e uso |
| --- | --- |
| Contesto | `python tools/play.py context` |
| Recupero interrotto | `python tools/play.py recover`: completa soltanto una transazione già registrata, senza nuovi dadi o scelte. Anche `context` tenta prima questo recupero. |
| Attacco | `python tools/play.py attack "Attaccante" "Bersaglio" --attack 0 --id ID --expected-revision N` |
| Attacco bonus | Stessa forma con `--bonus`, solo quando la capacità e l'azione precedente lo consentono. |
| Multiattacco PNG | `python tools/play.py npc-multiattack master/piano-png.json --id ID --expected-revision N`: profilo di fonte verificato, bersagli dichiarati prima dei dadi, una transazione e nessun passaggio turno automatico. |
| Scelta a 0 PF | `python tools/play.py knockout "Bersaglio" --nonlethal --id ID --expected-revision N`; usare `--lethal` se è la scelta espressa. Non ripete i tiri del colpo. |
| Fine turno | `python tools/play.py next --actor "Nome" --id ID --expected-revision N` |
| Cura | `python tools/play.py heal "Bersaglio" 5 --id ID --expected-revision N` |
| Danno già determinato | `python tools/play.py damage "Bersaglio" 5 --type contundente --id ID --expected-revision N` |
| Risorsa | `python tools/play.py resource "Nome" "Risorsa" -1 --id ID --expected-revision N` |
| Condizione | `python tools/play.py condition "Bersaglio" "Avvelenato" --id ID --expected-revision N`; aggiungere `--remove` per rimuoverla. |
| Prova di caratteristica | `python tools/play.py check "Nome" --ability str --dc 12 --id ID --expected-revision N` |
| Prova di abilità | `python tools/play.py check "Nome" --skill athletics --dc 12 --id ID --expected-revision N` |
| Tiro salvezza, anche concentrazione | `python tools/play.py check "Nome" --save con --dc 10 --id ID --expected-revision N` |
| Tiro salvezza contro morte nel proprio turno | `python tools/play.py death "Nome" --id ID --expected-revision N` |
| Salvataggio personalizzato | `python tools/play.py save master/effetto.json --id ID --expected-revision N` |
| Cura con incantesimo e slot | `python tools/play.py heal-spell master/cura.json --id ID --expected-revision N` |
| Presa, spinta o liberazione | `python tools/play.py contest master/contesa.json --id ID --expected-revision N` |
| Intralciare, TS e concentrazione | `python tools/play.py entangle master/magia.json --id ID --expected-revision N` |
| Liberarsi dalle piante o interrompere concentrazione | `python tools/play.py effect master/effetto-scelto.json --id ID --expected-revision N` |
| Controlli senza dadi o modifiche | `python tools/play.py preflight heal-spell master/cura.json`; tipi supportati: `heal-spell`, `contest`, `entangle`. |
| Consultare un incontro preparato | `python tools/play.py prepare porto --preflight`: consultazione privata, senza attivare l'incontro. Per gli altri ID vedere il catalogo. |
| Movimento tattico confermato | `python tools/scene_tools.py move master/movimento.json --id ID --expected-revision N` |

Nomi, indici, quantità, risorse, chiavi di abilità e CD sono esempi: usare i dati del contesto. Un nome ambiguo richiede l'ID preciso della creatura. Gli indici degli attacchi partono da zero; `--attack` accetta anche il nome. `--mode advantage` o `--mode disadvantage` si usano soltanto se previsti. Per altri argomenti consultare l'help del singolo comando.

Il DM verifica possibilità, portate, coperture, bersagli, condizioni, resistenze, sorpresa, concentrazione, reazioni e prerequisiti della capacità. `attack` non simula ogni regola del SRD: `--reactions-checked` e `--modifiers-checked` attestano che il DM ha già risolto i casi pertinenti, non autorizzano a saltarli. Se un attacco può essere interrotto da una scelta, rispettare prima l'innesco e chiedere la decisione; usare il percorso manuale quando serve separare tiro per colpire ed effetto. Non consumare automaticamente una reazione o una risorsa dei PG. Nessun comando decide le mosse degli altri tre giocatori o svolge i turni dei PNG.

Per `attack` e `knockout`, `--death-saves` o `--no-death-saves` dichiarano l'arbitraggio già fissato per i TS contro morte di un PNG; senza queste opzioni vale il suo registro privato. Non cambiare l'arbitraggio dopo aver visto i danni per imporre un esito. `attack --martial-arts-eligible` conferma una verifica dell'equipaggiamento realmente indossato, quando gli oggetti trasportati da soli non chiariscono l'uso di Arti Marziali.

Una cura applica PF già determinati: fonte della cura, dado, magia, slot, componenti e tempo vanno risolti secondo le regole. Un cambio di condizione non implementa da solo ogni conseguenza di magie o capacità. `next` avanza l'iniziativa dopo la fine del turno dichiarata: non fa agire automaticamente il prossimo. Le azioni ambientali, i dialoghi e le soluzioni creative restano liberi anche se non esiste un comando dedicato.

## Multiattacco dei PNG

Il catalogo `tools/npc_profiles.py` include un profilo sintetico dimostrativo. Ogni nuovo PNG richiede una voce verificata dalla fonte del master. Il profilo demo non attribuisce azioni a una creatura reale e non avvia uno scontro.

Prima del comando registrare l'arma realmente impugnata, verificare portate, modificatori e finestre di reazione e scegliere l'intenzione letale o non letale. Il comando rifiuta difese speciali e reazioni disponibili registrate, anche degli alleati: in questi casi risolvere i colpi separatamente. Un KO o una prova di concentrazione interrompe la sequenza; i colpi ancora non tirati risultano in `unrolled_attacks` e sono rinunciati definitivamente per questa operazione. Nessun cambio di bersaglio automatico. Se il DM vuole conservare la scelta dei colpi successivi, usare dall'inizio il percorso individuale anziché questo batch.

`tool_elapsed_ms` misura l'operazione locale; `resolution_ms` misura la sua parte di risoluzione. Non comprendono il tempo di ragionamento del modello, le chiamate agli strumenti o la rete. L'ID stabile, il salvataggio atomico e il diario evitano di duplicare tiri e danni nei ritentativi.

Per un effetto non coperto, `save` accetta un oggetto JSON:

```json
{
  "patch": {"scene": {"title": "Titolo pubblico", "text": "Situazione ormai risolta", "choices": []}},
  "public": "Sintesi conosciuta dai PG",
  "dm": "Conseguenze private e fonte verificata",
  "pending": ["Nome: decisione ancora attesa"],
  "references": ["Fonte e pagina già consultate"],
  "resolve": [],
  "private_combat": {}
}
```

Fornire almeno un effetto o un evento reale; i campi vuoti dell'esempio non vanno riempiti con eventi immaginati. La patch pubblica passa dalla validazione e dal controllo di revisione del motore; gli array si sostituiscono interamente. I segreti appartengono a `dm` e `private_combat`: quest'ultimo aggiorna il registro riservato `master/COMBATTIMENTO.json`, per preparare una volta i PNG dalla fonte o salvare le conseguenze private dello stesso effetto. Non pubblicare PF, CA o identità segrete nella patch. `resolve` contiene soltanto ID di intenzioni davvero risolte; `pending` conserva in forma di testi le decisioni ancora aperte, comprese dichiarazioni ricevute solo in chat. Per liberare un blocco operativo risolto, aggiornare esplicitamente anche il relativo campo nel registro pubblico o privato: il testo di un resoconto non lo modifica.

Il risultato compatto indica successo, revisione e conseguenze pertinenti. In caso di conflitto rileggere il contesto: non forzare la revisione e non cambiare ID per aggirare una richiesta già riuscita. Se il tool segnala un salvataggio parziale o un recupero da completare, seguire l'indicazione senza ritirare i dadi. Una registrazione privata mancante non giustifica un secondo attacco.

Restano disponibili `tools/dnd.py` per tiri segreti, batch di iniziativa, premi XP, creazione PG, luoghi e patch di basso livello; `tools/campaign.py` per la campagna; `tools/turn_log.py` per diario e checkpoint. Il percorso manuale è descritto in `../AGENTS.md`. Usarlo quando necessario, senza duplicare operazioni già completate dai comandi pronti.

## Preparazione aperta e strumenti della scena

`campaigns/<campaign_id>/prepared/encounters.json` è un catalogo riservato con schede, capacità, reazioni, motivazioni, varianti possibili e riferimenti verificati. È una preparazione: non concede informazioni ai PG, non determina iniziativa o risultati e non fa comparire incontri saltati altrove. Consultarlo prima della sessione o all'ingresso in una nuova area, senza rileggere l'intera campagna a ogni mossa. Per aggiungere altri profili verificare il blocco della fonte originale e registrare pagina e controlli; non inventare numeri per completare un catalogo.

I piani dei nuovi comandi sono oggetti JSON. `checks` contiene verifiche effettivamente concluse dal DM, tra cui dichiarazione del giocatore, componenti, portata, modificatori e reazioni: `true` registra una verifica, non la sostituisce. Mancanze e casi non supportati devono fermare il comando prima dei dadi. Gli esempi preparati in `tools/examples/` vanno adattati alla scena e alle scelte reali; non si eseguono come azioni già avvenute.

`heal-spell` supporta Parola Guaritrice e Cura Ferite con consumo dello slot, economia del turno, dado e applicazione della cura nella stessa transazione. `contest` richiede esplicitamente la difesa scelta e applica presa, spinta prona, spinta di 1,5 m o liberazione; i casi con attacchi extra e capacità speciali restano da arbitrare. `entangle` applica soltanto i TS iniziali delle creature dichiarate nell'area, slot, azione, concentrazione, terreno difficile e scadenza; entrare dopo non genera un nuovo TS. Per liberarsi dalle piante usare una prova di Forza, non Atletica. Reazioni e casi con difese speciali richiedono un percorso individuale.

I comandi ordinari di `play.py` riconciliano nello stesso salvataggio gli effetti gestiti, anche quando termina la concentrazione, il lanciatore scende a zero PF o arriva la scadenza. Le durate sconosciute o le fonti sovrapposte richiedono l'arbitraggio esplicito, senza rimuovere condizioni di altre fonti. `timings_ms` riporta intervalli locali misurati: `read_validate`, `resolve`, `validate_persist`, `total`; nei ritentativi riporta `replay_total`. Non sono tempi del modello o della rete.

La mappa pubblica si trova in `flags.tactical_scene`: `location_id`, `grid:{columns,rows,cell_m,confirmed:true}`, pedine `tokens:[{id,entity_id,name,x,y,confirmed:true}]`, oggetti e coperture percepiti. Le coordinate sono caselle a partire da zero; di norma le diagonali costano una casella, come nella griglia 2014. Non ricavare una planimetria certa soltanto da poche distanze. Dichiarare al tavolo eventuali dettagli fissati dal DM per completare una scena. `flags.table_scene` conserva oggetti, distanze confermate e oggetti a terra; quando luogo o posizioni cambiano, aggiornare o invalidare i dati pertinenti.

Per disegnare mappe grandi usare il tool dedicato [dungeon_maps.py](DUNGEON_MAPS.md): piante ed esportazioni complete in `campaigns/<campaign_id>/maps/`, soltanto versioni `players` già ritagliate sotto `web/assets/maps/`. Un fondale si collega con `flags.tactical_scene.background:{url:"/assets/maps/NOME.svg",columns:N,rows:M,cell_m:1.5,alt:"Descrizione pubblica"}`. Dimensioni e scala devono coincidere esattamente con la griglia confermata; i file non hanno margini esterni. Salvare questo metadato tramite `play.py save`, senza muovere pedine o scoprire zone. La cartoteca pubblica `/maps.html` contiene soltanto mappe condivise e un esempio originale fuori partita: non aggiungervi le future aree della campagna. Per una mappa di fonte verificare prima l'immagine originale e le parti pertinenti; il disegno schematico non sostituisce quote, dislivelli e dettagli del PDF.

Esempio di piano di movimento da compilare dopo avere risolto eventuali reazioni:

```json
{"actor":"ID_PG","x":3,"y":5,"cost_m":1.5,"mode":"walk","reactions_checked":true,"terrain_checked":true,"obstacles_checked":true}
```

`scene_tools.py move` controlla attore di turno, condizioni, casella, costo minimo e movimento residuo, poi aggiorna coordinate pubbliche, distanze e registro privato insieme. `mode:"dash"` usa l'azione per Scatto. Il costo effettivo include terreno e percorso già verificati: il tool non risolve attacchi di opportunità o prove di arrampicata. Le azioni che spostano una creatura senza fissarne la nuova casella devono invalidare la vecchia posizione, evitando di lasciare sulla plancia coordinate false.

Prima di una nuova run assegnare un nuovo `flags.run_id`, conservare la precedente come snapshot e ricreare soltanto ciò che il giocatore ha richiesto di ricominciare. Il taccuino locale usa quell'ID per separare le conoscenze fra partite.
