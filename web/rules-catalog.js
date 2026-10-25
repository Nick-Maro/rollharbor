/* Original Italian rules summaries. SRD 5.1, CC BY 4.0: see ATTRIBUZIONI.md.
 * Public reference only: no adventure contents, NPC statistics or save mutations.
 * Distances use the usual 5 feet = 1.5 metres game conversion.
 */
(function () {
  'use strict';
  const entries = [];
  const srd = 'https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf';
  const source = page => ({label: `SRD 5.1 · regole 2014${page ? `, p. ${page}` : ''}`, url: srd + (page ? `#page=${page}` : '')});
  const add = (id, kind, title, aliases, summary, facts = [], details = [], page = null, mechanics = {}) => {
    entries.push({id, kind, title, aliases, summary,
      facts: facts.map(([label, value]) => ({label, value: String(value)})), details,
      source: source(page), mechanics});
  };
  const spell = (id, title, english, page, spec, summary, details = [], aliases = []) => {
    const {level = 1, school, time = '1 azione', range, components = 'V, S', duration = 'Istantanea', concentration = false, ritual = false, effect, upcast} = spec;
    const facts = [['Livello', level ? `${level}° livello · ${school}` : `Trucchetto · ${school}`], ['Lancio', time], ['Gittata / area', range], ['Componenti', components], ['Durata', duration], ['Concentrazione', concentration ? 'Sì' : 'No'], ['Costo', level ? (ritual ? 'Uno slot; come rituale consentito non consuma slot' : 'Uno slot del livello usato') : 'Nessuno slot']];
    if (effect) facts.push(['Effetto / tiro', effect]);
    if (ritual) facts.push(['Rituale', 'Sì: +10 minuti, se la classe consente il rituale']);
    if (upcast) details = [...details, `Slot superiori: ${upcast}`];
    add(`spell-${id}`, 'spell', title, [english, ...aliases], summary, facts, details, page,
      {level, concentration, ritual, casting_time: time, range, components, duration});
  };

  spell('entangle', 'Intralciare', 'Entangle', 140,
    {school: 'Evocazione', range: '27 m; quadrato di terreno di 6 × 6 m', components: 'V, S', duration: 'Fino a 1 minuto', concentration: true, effect: 'TS Forza iniziale; poi prova di Forza per liberarsi'},
    'Rampicanti rendono difficile il terreno e possono trattenere le creature presenti quando lanci la magia.',
    ['Ogni creatura nell’area al lancio, compresi gli alleati, fa un TS Forza contro la tua CD. Se fallisce è trattenuta fino alla fine dell’incantesimo.', 'Una creatura trattenuta può usare la propria azione per una prova di Forza contro la tua CD: un successo la libera. È una prova di caratteristica, non un nuovo tiro salvezza.', 'L’area resta terreno difficile anche per chi supera il tiro. Entrarvi dopo il lancio non provoca un nuovo TS iniziale.', 'Trattenere non impedisce di agire e non interrompe da solo una presa su un’altra creatura.']);
  spell('healing-word', 'Parola Guaritrice', 'Healing Word', 153,
    {school: 'Invocazione', time: '1 azione bonus', range: '18 m; una creatura che vedi', components: 'V', effect: 'Recupera 1d4 + modificatore da incantatore PF', upcast: '+1d4 PF per ogni livello di slot oltre il 1°.'},
    'Una parola restituisce punti ferita a un bersaglio visibile, anche a distanza.',
    ['Non influenza non morti o costrutti. Recuperare PF può far riprendere conoscenza a una creatura a 0 PF.', 'Poiché si lancia come azione bonus, nello stesso turno puoi lanciare un altro incantesimo solo se è un trucchetto con tempo di lancio di un’azione. Puoi comunque usare l’azione per attaccare.']);
  spell('goodberry', 'Bacche Benefiche', 'Goodberry', 150,
    {school: 'Trasmutazione', range: 'Contatto; fino a 10 bacche nella tua mano', components: 'V, S, M (rametto di vischio)', effect: 'Ogni bacca mangiata cura 1 PF'},
    'Crei fino a dieci bacche magiche: ciascuna nutre una creatura per un giorno e ripristina 1 PF.',
    ['La creatura usa la propria azione per mangiare una bacca. Le bacche perdono il potere dopo 24 ore.', 'Il testo non concede automaticamente di far mangiare una bacca a chi è incosciente: una simile manovra si decide con il master.', 'Non richiede concentrazione; usare uno slot superiore non aumenta il numero di bacche o la cura.']);
  spell('detect-magic', 'Individuazione del Magico', 'Detect Magic', 134,
    {school: 'Divinazione', range: 'Personale; magia entro 9 m', duration: 'Fino a 10 minuti', concentration: true, ritual: true, effect: 'Percepisci la presenza della magia'},
    'Avverti la magia vicina; con un’azione osservi l’aura di una creatura o di un oggetto visibile e ne riconosci l’eventuale scuola.',
    ['Non rivela automaticamente proprietà, funzionamento o maledizioni di un oggetto magico.', 'Il rilevamento è bloccato da 30 cm di pietra, 2,5 cm di metallo comune, un sottile foglio di piombo o 90 cm di legno o terra.'], ['Individuazione Magico']);
  spell('guidance', 'Guida', 'Guidance', 151,
    {level: 0, school: 'Divinazione', range: 'Contatto; una creatura consenziente', duration: 'Fino a 1 minuto', concentration: true, effect: '+1d4 a una prova di caratteristica'},
    'Tocchi un alleato: una volta, prima che la magia finisca, può aggiungere 1d4 a una prova di caratteristica.',
    ['Il d4 può essere tirato prima o dopo la prova, quindi l’incantesimo termina. Non si aggiunge agli attacchi o ai tiri salvezza.', 'La magia deve essere attiva mentre si effettua la prova. Richiede concentrazione, componenti udibili e gesti.']);
  spell('produce-flame', 'Produrre Fiamma', 'Produce Flame', 172,
    {level: 0, school: 'Evocazione', range: 'Personale; lancio contro una creatura entro 9 m', duration: '10 minuti', effect: 'Attacco a distanza con incantesimo; 1d8 fuoco'},
    'Una fiamma innocua per te e per il tuo equipaggiamento illumina la mano; puoi scagliarla per attaccare.',
    ['Luce intensa entro 3 m e fioca per altri 3 m. Non richiede concentrazione.', 'Puoi scagliare la fiamma quando lanci il trucchetto, oppure usando un’azione in un turno successivo. L’attacco termina la magia.', 'Danni: 2d8 al livello del personaggio 5, 3d8 all’11, 4d8 al 17.']);
  spell('animal-friendship', 'Amicizia con gli Animali', 'Animal Friendship', 115,
    {school: 'Ammaliamento', range: '9 m; una bestia che vedi', components: 'V, S, M (un boccone di cibo)', duration: '24 ore', effect: 'TS Saggezza o affascinata', upcast: 'Una bestia aggiuntiva per ogni livello di slot oltre il 1°.'},
    'Convinci una bestia che non vuoi farle del male; deve vederti e sentirti e avere Intelligenza inferiore a 4.',
    ['Una bestia con Intelligenza 4 o più non viene influenzata. Se tu o un compagno le fate del male, la magia termina.', 'Affascinata non significa controllata: non permette di impartire qualunque ordine.']);
  spell('thunderwave', 'Onda Tonante', 'Thunderwave', 187,
    {school: 'Invocazione', range: 'Personale; cubo di 4,5 m originato da te', effect: 'TS Costituzione; 2d8 tuono e spinta di 3 m; metà danni se supera', upcast: '+1d8 danni per ogni livello di slot oltre il 1°.'},
    'Un’onda di forza tonante investe tutte le creature nel cubo, alleati compresi.',
    ['Chi supera il TS subisce metà danni e non viene spinto. Gli oggetti non fissati interamente nell’area vengono spinti automaticamente di 3 m.', 'Il boato si sente fino a 90 m. Il cubo parte da te: non è una sfera centrata su di te.']);
  spell('longstrider', 'Passo Veloce', 'Longstrider', 160,
    {school: 'Trasmutazione', range: 'Contatto', components: 'V, S, M (un pizzico di terra)', duration: '1 ora', effect: 'Velocità +3 m', upcast: 'Una creatura aggiuntiva per ogni livello di slot oltre il 1°.'},
    'Aumenti di 3 metri la velocità di una creatura toccata, senza concentrazione.');
  spell('vicious-mockery', 'Beffa Crudele', 'Vicious Mockery', 189,
    {level: 0, school: 'Ammaliamento', range: '18 m; una creatura che vedi e che può sentirti', components: 'V', effect: 'TS Saggezza; 1d4 psichici e svantaggio al prossimo attacco'},
    'Un insulto infuso di magia ferisce e distrae il bersaglio; non deve comprendere la tua lingua.',
    ['Se fallisce il TS, ha svantaggio al prossimo attacco effettuato prima della fine del suo prossimo turno. Se supera, non subisce effetti.', 'Danni: 2d4 al livello 5, 3d4 all’11, 4d4 al 17.']);
  spell('mage-hand', 'Mano Magica', 'Mage Hand', 160,
    {level: 0, school: 'Evocazione', range: '9 m', duration: '1 minuto', effect: 'Mano spettrale; carico massimo circa 4,5 kg'},
    'Crei una mano a distanza per manipolare oggetti, aprire contenitori non chiusi a chiave o versare una boccetta.',
    ['Per controllarla usi un’azione; puoi muoverla fino a 9 m ogni volta. Non attacca e non attiva oggetti magici.', 'Scompare se supera 9 m da te o se lanci nuovamente il trucchetto. Non scassina automaticamente serrature.']);
  spell('sacred-flame', 'Fiamma Sacra', 'Sacred Flame', 176,
    {level: 0, school: 'Invocazione', range: '18 m; una creatura che vedi', effect: 'TS Destrezza; 1d8 radiosi'},
    'Un bagliore scende sul bersaglio: se non supera il tiro salvezza subisce danni radiosi.',
    ['Il bersaglio non beneficia della copertura per questo TS; devi comunque poterlo vedere e poterlo bersagliare.', 'Danni: 2d8 al livello 5, 3d8 all’11, 4d8 al 17.']);
  spell('thaumaturgy', 'Taumaturgia', 'Thaumaturgy', 187,
    {level: 0, school: 'Trasmutazione', range: '9 m', components: 'V', duration: 'Fino a 1 minuto', effect: 'Piccoli prodigi, senza danni'},
    'Produci un segno soprannaturale: voce amplificata, fiamme alterate, tremori innocui, un suono, occhi insoliti o una porta non chiusa a chiave che si apre o chiude.',
    ['Puoi mantenere fino a tre effetti da un minuto contemporaneamente, rilanciando il trucchetto. I singoli effetti possono essere interrotti con un’azione.', 'Non sostituisce scasso, danni o controllo mentale.']);
  spell('fire-bolt', 'Dardo di Fuoco', 'Fire Bolt', 144,
    {level: 0, school: 'Invocazione', range: '36 m; una creatura o un oggetto', effect: 'Attacco a distanza con incantesimo; 1d10 fuoco'},
    'Scagli una scintilla rovente contro un bersaglio.',
    ['Un oggetto infiammabile colpito prende fuoco se non è indossato o trasportato.', 'Danni: 2d10 al livello 5, 3d10 all’11, 4d10 al 17.']);
  spell('ray-of-frost', 'Raggio di Gelo', 'Ray of Frost', 174,
    {level: 0, school: 'Invocazione', range: '18 m; una creatura', effect: 'Attacco a distanza con incantesimo; 1d8 freddo, velocità −3 m'},
    'Un raggio gelido infligge danni e riduce di 3 m la velocità del bersaglio fino all’inizio del tuo prossimo turno.',
    ['Danni: 2d8 al livello 5, 3d8 all’11, 4d8 al 17.']);
  spell('eldritch-blast', 'Deflagrazione Occulta', 'Eldritch Blast', 139,
    {level: 0, school: 'Invocazione', range: '36 m; una creatura per raggio', effect: 'Attacco a distanza con incantesimo; 1d10 forza per raggio'},
    'Scagli un raggio di energia crepitante.',
    ['Hai due raggi al livello del personaggio 5, tre all’11 e quattro al 17; ognuno richiede un attacco separato e può colpire un bersaglio diverso.', 'Non aggiungi automaticamente il modificatore di Carisma ai danni: servirebbe una capacità che lo permetta.']);
  spell('minor-illusion', 'Illusione Minore', 'Minor Illusion', 164,
    {level: 0, school: 'Illusione', range: '9 m', components: 'S, M (un po’ di vello)', duration: '1 minuto', effect: 'Un suono oppure immagine di un oggetto in un cubo di 1,5 m'},
    'Crei un suono o l’immagine immobile di un oggetto. L’immagine non produce rumore, luce, odore o altre sensazioni.',
    ['Il contatto fisico rivela che l’immagine non è solida. Un osservatore può usare l’azione per una prova di Intelligenza (Indagare) contro la tua CD e riconoscere l’illusione.', 'Chi la riconosce può vedere attraverso l’immagine. La magia termina se la rilanci o la interrompi con un’azione.']);
  spell('message', 'Messaggio', 'Message', 164,
    {level: 0, school: 'Trasmutazione', range: '36 m', components: 'V, S, M (un pezzetto di filo di rame)', duration: '1 round', effect: 'Messaggio sussurrato e risposta privata'},
    'Indichi una creatura e sussurri un messaggio: solo lei lo sente e può risponderti con un sussurro udibile solo da te.',
    ['Può aggirare angoli e attraversare ostacoli se conosci il bersaglio e sai che è oltre la barriera. Silenzio magico, 30 cm di pietra, 2,5 cm di metallo, piombo sottile o 90 cm di legno lo bloccano.', 'Il trucchetto razziale dell’elfo alto usa Intelligenza, anche se la classe usa un’altra caratteristica.']);
  spell('sleep', 'Sonno', 'Sleep', 180,
    {school: 'Ammaliamento', range: '27 m; raggio di 6 m dal punto scelto', components: 'V, S, M (sabbia fine, petali di rosa o un grillo)', duration: '1 minuto', effect: '5d8 PF complessivi; nessun tiro salvezza', upcast: '+2d8 al totale per ogni livello di slot oltre il 1°.'},
    'Addormenti creature cominciando da quella con meno PF attuali, ignorando quelle già incoscienti.',
    ['Sottrai dal totale i PF attuali di ogni creatura influenzata. Non puoi scegliere di escludere gli alleati presenti nell’area.', 'Un dormiente si sveglia subendo danni, alla fine della magia o se qualcuno usa un’azione per scuoterlo. Non morti e creature immuni ad affascinato sono immuni.']);
  spell('faerie-fire', 'Luminescenza', 'Faerie Fire', 141,
    {school: 'Invocazione', range: '18 m; cubo di 6 m', components: 'V', duration: 'Fino a 1 minuto', concentration: true, effect: 'TS Destrezza; contorno luminoso'},
    'Contorni gli oggetti e, se falliscono il TS iniziale, le creature nell’area con luce colorata.',
    ['Contro un bersaglio illuminato gli attacchi hanno vantaggio se l’attaccante lo vede; il bersaglio non beneficia dell’invisibilità.', 'Luce fioca entro 3 m da ciascun bersaglio. Può influenzare gli alleati.']);
  spell('shield-of-faith', 'Scudo della Fede', 'Shield of Faith', 179,
    {school: 'Abiurazione', time: '1 azione bonus', range: '18 m', components: 'V, S, M (piccola pergamena con testo sacro)', duration: 'Fino a 10 minuti', concentration: true, effect: '+2 alla CA di una creatura'},
    'Un campo scintillante protegge il bersaglio finché mantieni la concentrazione.');
  spell('guiding-bolt', 'Dardo Tracciante', 'Guiding Bolt', 151,
    {school: 'Invocazione', range: '36 m; una creatura', duration: '1 round', effect: 'Attacco a distanza con incantesimo; 4d6 radiosi', upcast: '+1d6 danni per ogni livello di slot oltre il 1°.'},
    'Un lampo ferisce e rivela il bersaglio: il prossimo attacco contro di lui prima della fine del tuo prossimo turno ha vantaggio.');
  spell('sanctuary', 'Santuario', 'Sanctuary', 176,
    {school: 'Abiurazione', time: '1 azione bonus', range: '9 m', components: 'V, S, M (piccolo specchio d’argento)', duration: '1 minuto', effect: 'TS Saggezza per chi bersaglia il protetto'},
    'Chi tenta di colpire la creatura protetta con un attacco o un incantesimo dannoso deve prima superare un TS Saggezza.',
    ['Se fallisce deve cambiare bersaglio oppure perdere l’attacco o l’incantesimo. Non protegge dagli effetti ad area.', 'Termina se il protetto attacca o lancia un incantesimo che influenza un nemico, secondo il testo SRD 5.1.']);
  spell('protection-evil-good', 'Protezione dal Bene e dal Male', 'Protection from Evil and Good', 173,
    {school: 'Abiurazione', range: 'Contatto; una creatura consenziente', components: 'V, S, M (acqua santa o polvere d’argento e ferro: consumati)', duration: 'Fino a 10 minuti', concentration: true, effect: 'Protezione da sei tipi di creature'},
    'Aberrazioni, celestiali, elementali, folletti, immondi e non morti hanno svantaggio agli attacchi contro il protetto.',
    ['Quelle creature non possono affascinarlo, spaventarlo o possederlo. Se un simile effetto è già attivo, il protetto ha vantaggio ai nuovi TS contro di esso.', 'Il componente materiale viene consumato: un focus non lo sostituisce. Non protegge indistintamente da ogni nemico di allineamento malvagio.']);
  spell('command', 'Comando', 'Command', 125,
    {school: 'Ammaliamento', range: '18 m; una creatura che vedi', components: 'V', duration: '1 round', effect: 'TS Saggezza; obbedisce a una parola nel prossimo turno', upcast: 'Un bersaglio aggiuntivo per ogni livello di slot oltre il 1°; entro 9 m l’uno dall’altro.'},
    'Pronunci un ordine di una parola, come «Fermo», «Fuggi», «Lascia» o «Prono».',
    ['Non influenza non morti, chi non capisce la tua lingua o chi riceve un ordine direttamente dannoso per sé.', 'Per ordini diversi dagli esempi, il master stabilisce un comportamento coerente. Non permette un controllo illimitato.']);
  spell('bless', 'Benedizione', 'Bless', 122,
    {school: 'Ammaliamento', range: '9 m; fino a tre creature scelte', components: 'V, S, M (poca acqua santa)', duration: 'Fino a 1 minuto', concentration: true, effect: '+1d4 ad attacchi e TS', upcast: 'Una creatura aggiuntiva per ogni livello di slot oltre il 1°.'},
    'I bersagli aggiungono 1d4 ai propri tiri per colpire e tiri salvezza per tutta la durata.',
    ['Non si applica alle prove di caratteristica, come Atletica o Percezione.'], ['Benedizione · dominio']);
  spell('cure-wounds', 'Cura Ferite', 'Cure Wounds', 132,
    {school: 'Invocazione', range: 'Contatto', effect: 'Recupera 1d8 + modificatore da incantatore PF', upcast: '+1d8 PF per ogni livello di slot oltre il 1°.'},
    'Tocchi una creatura per curarne le ferite. Non influenza non morti o costrutti.', [], ['Cura Ferite · dominio']);
  spell('magic-missile', 'Dardo Incantato', 'Magic Missile', 161,
    {school: 'Invocazione', range: '36 m; creature che vedi', effect: 'Tre dardi simultanei: 1d4+1 forza ciascuno', upcast: 'Un dardo aggiuntivo per ogni livello di slot oltre il 1°.'},
    'Tre dardi colpiscono automaticamente una o più creature visibili, senza tiro per colpire.',
    ['Puoi distribuire i dardi. La magia Scudo annulla il danno di Dardo Incantato contro chi ne beneficia.']);
  spell('shield', 'Scudo', 'Shield', 179,
    {school: 'Abiurazione', time: '1 reazione quando un attacco ti colpisce o sei bersaglio di Dardo Incantato', range: 'Personale', duration: 'Fino all’inizio del tuo prossimo turno', effect: '+5 CA, incluso contro l’attacco che lo innesca'},
    'Una barriera magica può trasformare il colpo appena subito in un attacco mancato e protegge fino al tuo turno successivo.',
    ['Per la durata non subisci danni da Dardo Incantato. Servono una reazione disponibile, uno slot e la possibilità di fornire le componenti V e S.', 'È un incantesimo distinto dallo scudo dell’equipaggiamento. Non aumenta retroattivamente la CA contro attacchi precedenti.'], ['Scudo (incantesimo)']);
  spell('burning-hands', 'Mani Brucianti', 'Burning Hands', 123,
    {school: 'Invocazione', range: 'Personale; cono di 4,5 m', effect: 'TS Destrezza; 3d6 fuoco, metà se supera', upcast: '+1d6 danni per ogni livello di slot oltre il 1°.'},
    'Un ventaglio di fuoco investe tutte le creature nel cono.',
    ['Incendia oggetti infiammabili nell’area che non sono indossati o trasportati. Include eventuali alleati.']);
  spell('mage-armor', 'Armatura Magica', 'Mage Armor', 160,
    {school: 'Abiurazione', range: 'Contatto; creatura consenziente senza armatura', components: 'V, S, M (un pezzo di cuoio conciato)', duration: '8 ore', effect: 'CA base 13 + modificatore Destrezza'},
    'Un’armatura di forza sostituisce il calcolo base della CA del bersaglio.',
    ['Non si somma ad altri calcoli base come Difesa senza armatura. Uno scudo può aggiungere normalmente il suo bonus.', 'Termina se il bersaglio indossa un’armatura o se la interrompi con un’azione.']);
  spell('find-familiar', 'Trova Famiglio', 'Find Familiar', 143,
    {school: 'Evocazione', time: '1 ora', range: '3 m', components: 'V, S, M (10 mo di carbone, incenso ed erbe, consumati in un braciere d’ottone)', ritual: true, effect: 'Evoca uno spirito in una forma animale consentita'},
    'Ottieni un famiglio celestiale, folletto o immondo in forma di piccolo animale; non richiede concentrazione.',
    ['Il famiglio ha la propria iniziativa, obbedisce ai tuoi ordini e può compiere azioni ma non attaccare. A 0 PF scompare; serve rilanciare la magia per riaverlo.', 'Entro 30 m puoi comunicare telepaticamente e usare un’azione per percepire con i suoi sensi fino all’inizio del turno successivo, rinunciando temporaneamente ai tuoi.', 'Entro 30 m può consegnare un tuo incantesimo a contatto usando la propria reazione. Puoi avere un solo famiglio.', 'Il rituale richiede 1 ora e 10 minuti e consuma comunque le 10 mo di componenti: il focus non le sostituisce.']);
  spell('armor-agathys', 'Armatura di Agathys', 'Armor of Agathys', null,
    {school: 'Abiurazione', range: 'Personale', components: 'V, S, M (una tazza d’acqua)', duration: '1 ora', effect: '5 PF temporanei; 5 freddo a chi ti colpisce in mischia', upcast: '+5 PF temporanei e +5 danni per ogni livello di slot oltre il 1°.'},
    'Un gelo magico ti protegge: finché possiedi questi PF temporanei, una creatura che ti colpisce con un attacco in mischia subisce i danni da freddo.',
    ['Versione del 2014: l’effetto di risposta dipende dai PF temporanei concessi da questa magia. I PF temporanei di fonti diverse non si sommano.', 'Questa magia del Manuale del Giocatore 2014 è presente nel creatore del tavolo, ma non nel documento SRD 5.1.']);
  entries[entries.length - 1].source = {label: 'Manuale del Giocatore 2014 · Armatura di Agathys', url: 'https://www.dndbeyond.com/sources/dnd/phb-2014/spells#ArmorofAgathys'};

  const weapon = (id, title, english, damage, properties, range = 'Mischia: portata 1,5 m', details = [], aliases = []) => add(`weapon-${id}`, 'weapon', title, [english, ...aliases],
    'Usa l’azione Attaccare; il bonus per colpire e i danni del tuo personaggio sono indicati nella sua scheda.',
    [['Danno base', damage], ['Proprietà', properties], ['Portata / gittata', range]], details, 65);
  weapon('longsword', 'Spada lunga', 'Longsword', '1d8 taglienti; 1d10 con due mani', 'Da guerra; versatile', undefined,
    ['Usa normalmente Forza. Con uno scudo impugnato la usi a una mano.', 'Duellare, quando applicabile, aggiunge +2 danni. Il bonus già presente nell’attacco della scheda non va aggiunto una seconda volta.']);
  weapon('shortsword', 'Spada corta', 'Shortsword', '1d6 perforanti', 'Da guerra; accurata; leggera', undefined,
    ['Accurata: scegli Forza o Destrezza sia per colpire sia per i danni. È un’arma da monaco.'], ['Seconda spada corta']);
  weapon('scimitar', 'Scimitarra', 'Scimitar', '1d6 taglienti', 'Da guerra; accurata; leggera');
  weapon('rapier', 'Stocco', 'Rapier', '1d8 perforanti', 'Da guerra; accurata');
  weapon('dagger', 'Pugnale', 'Dagger', '1d4 perforanti', 'Semplice; accurata; leggera; lancio', 'Mischia 1,5 m; lancio 6/18 m');
  weapon('javelin', 'Giavellotto', 'Javelin', '1d6 perforanti', 'Semplice; lancio', 'Mischia 1,5 m; lancio 9/36 m',
    ['Usa Forza anche quando lo lanci. Il primo numero è la gittata normale, il secondo quella massima: oltre la prima attacchi con svantaggio.', 'Un giavellotto lanciato lascia il tuo inventario disponibile; recuperarlo dipende da dove è finito e dalla situazione.']);
  weapon('handaxe', 'Ascia', 'Handaxe', '1d6 taglienti', 'Semplice; leggera; lancio', 'Mischia 1,5 m; lancio 6/18 m', [], ['Ascia a mano']);
  weapon('greataxe', 'Ascia bipenne', 'Greataxe', '1d12 taglienti', 'Da guerra; pesante; due mani', undefined,
    ['Le creature Piccole hanno svantaggio agli attacchi con un’arma pesante nelle regole del 2014.']);
  weapon('battleaxe', 'Ascia da battaglia', 'Battleaxe', '1d8 taglienti; 1d10 con due mani', 'Da guerra; versatile');
  weapon('mace', 'Mazza', 'Mace', '1d6 contundenti', 'Semplice');
  weapon('quarterstaff', 'Bastone ferrato', 'Quarterstaff', '1d6 contundenti; 1d8 con due mani', 'Semplice; versatile', undefined,
    ['È un’arma da monaco; non possiede la proprietà due mani solo perché decidi di usarla con entrambe.']);
  weapon('dart', 'Dardo', 'Dart', '1d4 perforanti', 'Semplice a distanza; accurata; lancio', 'Lancio 6/18 m');
  weapon('shortbow', 'Arco corto', 'Shortbow', '1d6 perforanti', 'Semplice; munizioni; due mani', '24/96 m',
    ['Consuma una freccia per attacco. Puoi recuperare metà delle munizioni spese dopo lo scontro dedicando un minuto a cercarle.']);
  weapon('longbow', 'Arco lungo', 'Longbow', '1d8 perforanti', 'Da guerra; munizioni; pesante; due mani', '45/180 m');
  weapon('light-crossbow', 'Balestra leggera', 'Light Crossbow', '1d8 perforanti', 'Semplice; munizioni; ricarica; due mani', '24/96 m',
    ['Ricarica: puoi sparare una sola munizione per ciascuna azione, azione bonus o reazione usata per sparare, anche se avresti più attacchi. Richiede quadrelli.']);
  weapon('unarmed', 'Colpo senz’armi', 'Unarmed Strike', 'Normalmente 1 + Forza contundenti', 'Attacco in mischia; competenza inclusa', 'Portata 1,5 m',
    ['Pugni, calci e testate sono modi narrativi di effettuare colpi senz’armi. Il monaco può applicare Arti marziali: al livello 1 usa 1d4 + il modificatore pertinente.', 'Un colpo senz’armi non diventa automaticamente una seconda azione o un attacco gratuito.'], ["Colpo senz'armi", 'Pugno', 'Testata', 'Calcio']);

  add('armor-leather', 'armor', 'Armatura di cuoio', ['Leather Armor', 'Cuoio'], 'Armatura leggera: la CA è 11 + il tuo modificatore di Destrezza.',
    [['CA', '11 + Destrezza'], ['Furtività', 'Nessuno svantaggio dovuto a questa armatura'], ['Indossare / togliere', '1 minuto / 1 minuto']], [], 64);
  add('armor-chain-mail', 'armor', 'Cotta di maglia', ['Chain Mail'], 'Armatura pesante di CA 16: non aggiungi Destrezza.',
    [['CA', '16'], ['Forza', '13, altrimenti velocità −3 m salvo eccezioni'], ['Furtività', 'Svantaggio'], ['Indossare / togliere', '10 minuti / 5 minuti']],
    ['Serve competenza nelle armature pesanti. Senza competenza hai svantaggio a prove, TS e attacchi che usano Forza o Destrezza e non puoi lanciare incantesimi.'], 64);
  add('armor-shield', 'armor', 'Scudo', ['Shield', 'Scudo di legno', 'Scudo (oggetto)'], 'Uno scudo impugnato in una mano aggiunge +2 alla CA.',
    [['CA', '+2'], ['Indossare / togliere', '1 azione / 1 azione'], ['Mani', 'Una occupata']],
    ['Puoi beneficiare di un solo scudo. Lo scudo di legno ha lo stesso bonus ed è compatibile con il druido.', 'È compatibile con Duellare; impedisce le normali Arti marziali e la Difesa senza armatura del monaco.'], 64);

  const item = (id, title, aliases, summary, facts = [], details = [], page = 69) => add(`item-${id}`, 'item', title, aliases, summary, facts, details, page);
  item('healing-potion', 'Pozione di guarigione', ['Potion of Healing', 'Pozione di guarigione (2d4+2)', 'Pozione di cura'], 'Bere questa pozione magica restituisce 2d4 + 2 PF.',
    [['Uso', 'Un’azione per berla o somministrarla'], ['Cura', '2d4 + 2 PF'], ['Consumo', 'Una pozione']],
    ['Versione 2014: non si beve normalmente con un’azione bonus. Può far riprendere conoscenza a una creatura a 0 PF.']);
  item('torch', 'Torcia', ['Torch'], 'Una torcia accesa dura un’ora: luce intensa entro 6 m e fioca per altri 6 m.',
    [['Durata', '1 ora'], ['Luce', '6 m intensa + 6 m fioca']], ['Se colpisci con una torcia accesa in un attacco in mischia, infligge 1 danno da fuoco.'], 70);
  item('tinderbox', 'Acciarino', ['Tinderbox'], 'Contiene pietra focaia, acciaio ed esca per accendere un fuoco.',
    [['Accendere una torcia', 'Un’azione'], ['Altri fuochi', 'In genere 1 minuto']], [], 70);
  item('rope', 'Corda di canapa da 15 metri', ['Corda da 15 metri', 'Corda', 'Hempen Rope', 'Corda di canapa'], 'Una corda lunga circa 15 m, utile per scalare, assicurarsi o legare oggetti.',
    [['Lunghezza', '15 m'], ['Resistenza', '2 PF; prova di Forza CD 17 per spezzarla']],
    ['Una corda non lega automaticamente un avversario: servono tempo, accesso al bersaglio e una manovra possibile nella scena.'], 69);
  item('rations', 'Razione giornaliera', ['Razioni', 'Rations'], 'Cibo secco adatto ai viaggi, sufficiente normalmente per un giorno.', [['Consumo', 'Una razione al giorno']], [], 69);
  item('waterskin', 'Otre pieno', ['Otre', 'Waterskin'], 'Contenitore da viaggio per l’acqua: pieno contiene circa 1,9 litri.',
    [['Capacità', 'Circa 1,9 litri']], ['Acqua e cibo si consumano nella fiction; una quantità in inventario non si riempie da sola.'], 71);
  item('backpack', 'Zaino', ['Backpack'], 'Sacca da viaggio per trasportare l’equipaggiamento; una corda o un giaciglio possono essere fissati fuori.',
    [['Capacità', 'Circa 28 litri / 13,5 kg']], [], 71);
  item('bedroll', 'Giaciglio', ['Bedroll'], 'Letto da viaggio arrotolabile. Offre un posto dove dormire, senza concedere da solo un riposo sicuro.');
  item('mess-kit', 'Gavetta', ['Mess Kit'], 'Scatola con tazza e posate; le due metà fungono da padella e piatto.');
  item('candle', 'Candela', ['Candle'], 'Una candela accesa dura un’ora; luce intensa entro 1,5 m e fioca per altri 1,5 m.', [['Durata', '1 ora']], [], 68);
  item('arrow', 'Freccia', ['Frecce', 'Arrow', 'Arrows'], 'Munizione per archi. Ogni attacco ne usa una.', [],
    ['Dopo lo scontro puoi recuperarne metà dedicando un minuto alla ricerca, se la situazione lo permette.'], 66);
  item('bolt', 'Quadrello', ['Quadrelli', 'Crossbow Bolt'], 'Munizione per balestre, consumata a ogni attacco.', [],
    ['Non è intercambiabile con una freccia. Dopo lo scontro puoi recuperare metà delle munizioni spese cercandole per un minuto.'], 66);
  item('quiver', 'Faretra', ['Quiver'], 'Contenitore che può contenere fino a 20 frecce.', [['Capacità', '20 frecce']], [], 71);
  item('arcane-focus', 'Focus arcano', ['Arcane Focus'], 'Cristallo, globo, verga, bastone o bacchetta impiegato come focus da mago, stregone o warlock.', [],
    ['Sostituisce le componenti materiali senza costo indicato e non consumate. Non sostituisce componenti consumate o con un prezzo esplicito.', 'Occorre una mano per usarlo; la stessa può fornire componenti somatiche quando l’incantesimo richiede anche quelle materiali.'], 67);
  item('druidic-focus', 'Focus druidico', ['Druidic Focus'], 'Un oggetto naturale rituale, come vischio o un bastone di legno, usato dal druido per le componenti materiali.', [],
    ['Non sostituisce componenti consumate o con un costo indicato. Non concede lanci gratuiti e non sostituisce gli slot.'], 68);
  item('holy-symbol', 'Simbolo sacro', ['Holy Symbol'], 'Emblema della fede usato come focus da chierici e paladini.', [],
    ['Per il focus può essere impugnato, indossato in vista o portato sullo scudo. Non sostituisce componenti consumate o con costo.', 'Le componenti somatiche di una magia priva di componenti materiali richiedono comunque una mano libera.'], 69);
  item('spellbook', 'Grimorio', ['Spellbook'], 'Libro di magia del mago: contiene gli incantesimi da studiare e preparare.',
    [['Copiare un incantesimo da mago', '2 ore e 50 mo per livello dell’incantesimo']],
    ['Deve essere un livello di incantesimo che puoi preparare. I trucchetti non vengono copiati nel grimorio.', 'Un rituale da mago nel grimorio si può lanciare come rituale anche se non è preparato. Le sei magie iniziali non sono tutte necessariamente preparate.'], 53);
  item('thieves-tools', 'Arnesi da scasso', ['Thieves’ Tools', "Thieves' Tools", 'Attrezzi da scasso'], 'Attrezzi per serrature e trappole meccaniche; la competenza permette di aggiungere il relativo bonus alle prove pertinenti.', [],
    ['La prova e la caratteristica dipendono dal lavoro. Possederli non garantisce di aprire qualsiasi serratura.'], 71);
  item('herbalism-kit', 'Strumenti da erborista', ['Herbalism Kit'], 'Strumenti per identificare e applicare erbe e preparati; la competenza si aggiunge alle prove pertinenti.', [],
    ['La competenza è richiesta per creare antitossine e pozioni di guarigione secondo le regole di creazione, con tempo e materiali.'], 71);
  item('tinker-tools', 'Arnesi da inventore', ['Tinker’s Tools', "Tinker's Tools"], 'Utensili da artigiano per lavori meccanici. Le prove pertinenti beneficiano della competenza.', [],
    ['Lo gnomo delle rocce può usarli con la sua capacità Inventore per congegni semplici: non concedono tecnologia illimitata.'], 71);
  item('mason-tools', 'Utensili da muratore', ['Mason’s Tools', "Mason's Tools"], 'Attrezzi da artigiano per lavorare pietra e muratura; il master determina la prova adatta.', [], [], 71);
  for (const [id, title, english] of [['lute', 'Liuto', 'Lute'], ['flute', 'Flauto', 'Flute'], ['drum', 'Tamburo', 'Drum']]) {
    item(id, title, [english], 'Strumento musicale. La competenza si aggiunge alle prove appropriate per suonarlo.', [], ['Il bardo può usare uno strumento musicale come focus per i propri incantesimi. Possedere competenza non aggiunge automaticamente lo strumento all’inventario.'], 71);
  }
  for (const [id, title, summary, aliases] of [
    ['ink', 'Inchiostro (boccetta)', 'Boccetta d’inchiostro da circa 30 ml, da usare con pennino o penna.', ['Inchiostro']],
    ['pen', 'Pennino', 'Utensile per scrivere con inchiostro su carta o pergamena.', []],
    ['parchment', 'Pergamena (foglio)', 'Un foglio da scrittura: non è una pergamena magica e non contiene un incantesimo.', ['Pergamena']],
    ['study-book', 'Libro di studio', 'Libro del tuo equipaggiamento da studioso. L’argomento e le informazioni disponibili dipendono da ciò che è stato stabilito al tavolo.', ['Book']],
    ['sand', 'Sacchetto di sabbia', 'Sabbia fine del kit da studioso, utile per asciugare l’inchiostro o per usi plausibili nella scena.', []],
    ['small-knife', 'Coltellino', 'Piccolo coltello del kit da studioso. Non ha automaticamente le statistiche di un’arma da combattimento.', []],
    ['clothes', 'Abito comune', 'Abbigliamento quotidiano del personaggio; non è un’armatura.', ['Abiti comuni']],
    ['costume', 'Costume di scena', 'Abito da esibizione del kit da intrattenitore; non equivale da solo a un travestimento perfetto.', []],
    ['face-paint', 'Trucchi per il volto', 'Cosmetici del kit da intrattenitore. Eventuali travestimenti richiedono una preparazione e una prova adatte.', []],
    ['pouch', 'Borsa da cintura', 'Piccola borsa per monete e oggetti. La borsa vuota non contiene denaro aggiuntivo.', ['Pouch']]
  ]) item(id, title, aliases, summary);
  item('background-diary', 'Diario del passato', ['Diario'], 'Oggetto del background personalizzato del tavolo: può raccogliere ricordi e appunti del tuo personaggio.', [],
    ['Non contiene indizi, segreti o capacità automatiche non ancora stabiliti nella fiction.']);
  entries[entries.length - 1].source = {label: 'Background originale del tavolo · regola SRD sui background personalizzati', url: srd + '#page=60'};

  const feature = (id, title, aliases, summary, facts = [], details = [], page = null) => add(`feature-${id}`, 'feature', title, aliases, summary, facts, details, page);
  feature('second-wind', 'Recuperare energie', ['Second Wind', 'second_wind', 'wind'], 'Come azione bonus recuperi 1d10 + il tuo livello da guerriero PF, fino al massimo.',
    [['Costo', '1 azione bonus; un uso'], ['Recupero', 'Riposo breve o lungo']], ['Al livello 1 cura 1d10+1 PF. Non richiede uno slot e non è un incantesimo.'], 24);
  feature('dueling', 'Duellare', ['Dueling', 'Stile iniziale', 'Stile Duellare'], 'Ottieni +2 ai danni con un’arma da mischia impugnata in una mano, quando non impugni altre armi.',
    [['Costo', 'Passivo']], ['Uno scudo è compatibile. Non aggiunge +2 ai tiri per colpire.', 'Il creatore include già il bonus nella spada lunga del guerriero: non aggiungerlo una seconda volta.'], 24);
  feature('martial-arts', 'Arti marziali', ['Martial Arts', 'martial_arts'], 'Senza armatura né scudo, usando solo armi da monaco, puoi usare Destrezza per colpire e per i danni dei colpi senz’armi e delle armi da monaco.',
    [['Al livello 1', 'Il dado di Arti marziali è 1d4'], ['Attacco bonus', 'Un colpo senz’armi come azione bonus dopo l’azione Attaccare appropriata']],
    ['Puoi sostituire il danno normale con il dado di Arti marziali. Le armi da monaco sono spade corte e armi da mischia semplici prive delle proprietà pesante o due mani.', 'Quando usi l’azione Attaccare con un colpo senz’armi o un’arma da monaco, puoi effettuare un colpo senz’armi come azione bonus. Non è una seconda azione Attaccare.', 'Il ki e Raffica di colpi arrivano al livello 2: un monaco di livello 1 non può spendere ki.'], 26);
  feature('unarmored-defense', 'Difesa senza armatura', ['Unarmored Defense'], 'È un modo alternativo per calcolare la CA: scegli il calcolo consentito dalla tua classe, senza sommarlo ad altri calcoli base.',
    [['Monaco', 'CA 10 + Destrezza + Saggezza; niente armatura né scudo'], ['Barbaro', 'CA 10 + Destrezza + Costituzione; niente armatura, scudo consentito']], [], 8);
  feature('rage', 'Ira', ['Rage', 'rage'], 'Il barbaro entra in ira con un’azione bonus per un massimo di un minuto; al livello 1 ha due usi per riposo lungo.',
    [['Benefici', 'Vantaggio a prove e TS Forza; resistenza a contundente, perforante e tagliente'], ['Danni al livello 1', '+2 agli attacchi in mischia che usano Forza']],
    ['I benefici elencati richiedono di non indossare armatura pesante. Durante l’ira non puoi lanciare magie né mantenere concentrazione.', 'Termina se diventi incosciente, se la interrompi con un’azione bonus o se finisci il turno senza aver attaccato un nemico né subito danni dal turno precedente.'], 8);
  feature('bardic-inspiration', 'Ispirazione bardica', ['Bardic Inspiration', 'bardic_inspiration', 'inspiration'], 'Con un’azione bonus dai un d6 a un’altra creatura entro 18 m che possa sentirti.',
    [['Durata', '10 minuti, fino al suo utilizzo'], ['Usi', 'Modificatore di Carisma, minimo 1; riposo lungo']],
    ['La creatura può aggiungerlo a una prova, un attacco o un TS dopo aver visto il d20 ma prima di conoscere l’esito.', 'Una creatura può possedere un solo dado di Ispirazione bardica alla volta.'], 12);
  feature('life-domain', 'Dominio della Vita', ['Dominio iniziale SRD', 'Discepolo della Vita', 'Disciple of Life'], 'Il dominio iniziale del chierico del tavolo concede armature pesanti e cure migliorate.',
    [['Cure', '+2 + livello dell’incantesimo a una creatura curata da una magia di livello 1 o superiore'], ['Dominio al livello 1', 'Benedizione e Cura Ferite sempre preparati']],
    ['Le magie di dominio non contano nel numero di incantesimi preparabili. Incanalare Divinità si ottiene al livello 2.'], 17);
  feature('druidic', 'Druidico', ['Druidic'], 'Conosci la lingua segreta dei druidi e puoi usarla per lasciare messaggi nascosti.',
    [['Messaggi', 'Chi conosce il Druidico li nota automaticamente']],
    ['Chi non lo conosce nota la presenza del messaggio con Saggezza (Percezione) CD 15 ma non lo decifra senza magia.', 'Il druido è competente negli strumenti da erborista e non usa armature o scudi di metallo. Forma Selvatica arriva al livello 2.'], 19);
  feature('lay-on-hands', 'Imposizione delle mani', ['Lay on Hands', 'lay_on_hands'], 'Con un’azione tocchi una creatura e spendi punti dalla riserva per ripristinare altrettanti PF.',
    [['Riserva', '5 × livello da paladino PF; riposo lungo'], ['Malattia / veleno', '5 punti per curare una malattia o neutralizzare un veleno']],
    ['Non influenza non morti o costrutti. Puoi distribuire i punti fra più cure senza spendere tutta la riserva insieme.'], 31);
  feature('divine-sense', 'Percezione del divino', ['Divine Sense', 'divine_sense'], 'Con un’azione percepisci celestiali, immondi e non morti entro 18 m fino alla fine del tuo prossimo turno.',
    [['Usi', '1 + modificatore Carisma; riposo lungo']],
    ['Non attraversa copertura totale. Conosci posizione e tipo, non l’identità individuale. Rileva anche luoghi e oggetti consacrati o sconsacrati come da Santificare.', 'Non è un rilevatore generale di bugie, allineamento o intenzioni.'], 30);
  feature('favored-enemy', 'Nemico prescelto', ['Nemico prescelto iniziale', 'Favored Enemy'], 'Nel creatore il ranger sceglie le bestie come nemico prescelto.',
    [['Benefici', 'Vantaggio a Sopravvivenza per seguirne le tracce e prove di Intelligenza per ricordarne informazioni']],
    ['Non concede bonus automatici ai danni e non rivela la presenza di nemici senza una prova o indizi.'], 35);
  feature('natural-explorer', 'Esploratore nato', ['Natural Explorer'], 'Il terreno iniziale del ranger è la foresta; raddoppia la competenza alle prove pertinenti di Intelligenza e Saggezza se sei competente.',
    [['Viaggio nel terreno', 'Benefici dopo almeno un’ora di viaggio']],
    ['Il terreno difficile non rallenta il gruppo; non vi perdete salvo magia; resti allerta mentre svolgi un’altra attività; da solo puoi avanzare furtivo a passo normale.', 'Trovi il doppio del cibo foraggiando e, seguendo tracce, ne ricavi numero, taglia e tempo trascorso.'], 35);
  feature('expertise', 'Maestria', ['Expertise', 'Maestrie iniziali', 'Maestrie'], 'Raddoppi il bonus di competenza per le prove che usano le competenze selezionate.',
    [['Creatore del ladro', 'Prime due abilità di classe scelte']], ['Il bonus è già incluso nella scheda; non raddoppiare il modificatore di caratteristica o il totale della prova.'], 39);
  feature('sneak-attack', 'Attacco furtivo', ['Sneak Attack'], 'Una volta per turno, il ladro di livello 1 può aggiungere 1d6 a un colpo con un’arma accurata o a distanza quando soddisfa i requisiti.',
    [['Requisito', 'Vantaggio all’attacco, oppure un altro nemico del bersaglio entro 1,5 m']],
    ['Nell’alternativa con un altro nemico, quel nemico non deve essere incapacitato e tu non devi avere svantaggio.', 'Una volta per turno non equivale a una volta per round. Il dado extra si raddoppia su un critico.'], 39);
  feature('draconic-ancestry', 'Discendenza draconica', ['Origine iniziale SRD', 'Draconic Ancestry'], 'L’origine del creatore è un drago rosso, associato al fuoco; impari il Draconico.', [],
    ['Alle prove di Carisma per interagire con draghi, raddoppi la competenza se è applicabile. Al livello 1 non hai ancora resistenza al fuoco.'], 44);
  feature('draconic-resilience', 'Resilienza draconica', ['Draconic Resilience'], 'Il massimo dei tuoi PF aumenta di 1 per ogni livello da stregone; senza armatura la CA base è 13 + Destrezza.', [],
    ['I PF sono già inclusi nella scheda del creatore. Il calcolo della CA non si somma a un’armatura o a Difesa senza armatura.'], 45);
  feature('dark-blessing', 'Benedizione dell’Oscuro', ["Benedizione dell'Oscuro", 'Patrono iniziale SRD', 'Dark One’s Blessing'], 'Quando riduci una creatura ostile a 0 PF, ottieni PF temporanei pari al tuo livello da warlock + Carisma, minimo 1.', [],
    ['I PF temporanei non si sommano a un’altra riserva: scegli quale mantenere. Non sono una cura e non fanno riprendere conoscenza a 0 PF.'], 50);
  feature('pact-magic', 'Magia del patto', ['Pact Magic', 'pact_slot_1', 'pact_slot', 'pact_slots'], 'Gli slot del warlock tornano al termine di un riposo breve o lungo.',
    [['Livello 1', 'Uno slot di 1° livello']], ['Puoi spendere gli slot per le magie conosciute appropriate. La lista ampliata del patrono offre scelte: non concede magie conosciute gratuitamente.'], 47);
  feature('arcane-recovery', 'Recupero Arcano', ['Arcane Recovery', 'arcane_recovery'], 'Una volta al giorno, quando termini un riposo breve, recuperi slot fino a metà del tuo livello da mago arrotondata in eccesso.',
    [['Al livello 1', 'Un solo slot di 1° livello']], ['La somma dei livelli degli slot recuperati non supera il limite; nessuno slot recuperato può essere di livello 6 o superiore.'], 53);
  feature('spellcasting', 'Incantesimi', ['Incantesimi di Saggezza', 'Incantesimi di Carisma', 'Incantesimi di Intelligenza', 'Spellcasting', 'spell_slot_1', 'spell_slots', 'slots1', 'Slot di 1° livello'], 'Per una magia di livello 1 o superiore spendi uno slot adatto, salvo rituali o capacità che dicano diversamente. I trucchetti non consumano slot.',
    [['CD', '8 + competenza + modificatore da incantatore'], ['Attacco con incantesimo', 'Competenza + modificatore da incantatore']],
    ['La scheda distingue trucchetti, magie conosciute o nel grimorio, e magie preparate. La lista della classe non rende automaticamente tutte le magie preparate.', 'Chierico, druido e mago preparano normalmente livello di classe + modificatore della caratteristica magica, minimo 1. Le magie di dominio del chierico sono extra.', 'Per chierici, druidi, bardi e maghi gli slot ordinari tornano con il riposo lungo; Magia del patto segue una regola diversa.'], 100);
  feature('hit-dice', 'Dadi vita', ['Dado vita', 'hit_die', 'Hit Dice', 'Dado vita d6', 'Dado vita d8', 'Dado vita d10', 'Dado vita d12'], 'Durante un riposo breve puoi spendere uno o più dadi vita, uno alla volta, per curarti.',
    [['Cura per dado', 'Risultato del dado + Costituzione, minimo 0 PF']],
    ['Al termine di un riposo lungo recuperi fino a metà del numero totale di dadi vita, arrotondato per difetto, minimo un dado. Non sono gli slot degli incantesimi.'], 87);
  feature('human', 'Umano SRD standard', ['Umano', 'Human'], 'La specie del creatore è l’umano standard del 2014: +1 a tutte e sei le caratteristiche, taglia Media e velocità base 9 m.', [], ['Non è l’umano variante e non concede un talento gratuito.'], 5);
  feature('darkvision', 'Scurovisione', ['Darkvision', 'Taglia Media'], 'Le specie del creatore che la possiedono vedono entro 18 m nella luce fioca come in luce intensa e nell’oscurità come in luce fioca.', [],
    ['Nell’oscurità distingui solo sfumature di grigio. La scurovisione non rivela di per sé creature nascoste e non permette normalmente di vedere nel buio magico.'], 4);
  feature('fey-ancestry', 'Retaggio fatato', ['Fey Ancestry'], 'Gli elfi hanno vantaggio ai TS contro affascinato e non possono essere addormentati dalla magia.', [],
    ['Trance: gli elfi meditano profondamente per quattro ore anziché dormire. I riposi seguono la regola del tavolo e i requisiti della fonte 2014 adottata.'], 4);
  feature('elf-training', 'Addestramento con le armi elfiche', ['Addestramento con spada lunga, spada corta, arco lungo e arco corto', 'Elf Weapon Training'], 'L’elfo alto è competente in spada lunga, spada corta, arco lungo e arco corto; il creatore aggiunge Messaggio come trucchetto razziale di Intelligenza.', [], [], 4);
  feature('dwarven-toughness', 'Robustezza nanica', ['Dwarven Toughness'], 'Il nano delle colline aumenta il massimo dei PF di 1 per livello; il bonus è già incluso nella scheda.', [],
    ['La velocità nanica non viene ridotta dall’armatura pesante. La resistenza nanica concede vantaggio ai TS contro veleno e resistenza ai danni da veleno.'], 4);
  feature('dwarven-training', 'Addestramento nanico e pietra', ['Competenza in ascia da battaglia, ascia, martello leggero e martello da guerra', 'Stonecunning'], 'Il nano conosce asce e martelli previsti dalla specie e gli utensili da muratore nel creatore.', [],
    ['Per una prova di Storia sull’origine di un’opera in pietra sei considerato competente e aggiungi il doppio della competenza.'], 4);
  feature('small', 'Taglia Piccola', ['Small'], 'Halfling e gnomi sono Piccoli e hanno svantaggio agli attacchi con armi pesanti nelle regole del 2014.', [],
    ['La taglia non impedisce automaticamente di muoversi o usare armi a due mani. Le altre capacità dipendono dalla specie.', 'Halfling: Fortunato permette di ritirare un 1 naturale a un attacco, una prova o un TS, usando il nuovo d20. Gnomo: Astuzia gnomesca dà vantaggio ai TS Intelligenza, Saggezza e Carisma contro magia.'], 6);
  feature('lucky', 'Fortunato', ['Lucky'], 'L’halfling può ritirare un 1 naturale a un tiro per colpire, una prova di caratteristica o un tiro salvezza; deve usare il nuovo d20.', [], ['Gli gnomi non possiedono questa capacità.'], 4);
  feature('halfling-brave', 'Coraggioso', ['Brave', 'Agilità', 'Furtività naturale'], 'L’halfling ha vantaggio ai TS contro spaventato; può attraversare lo spazio di creature più grandi.', [],
    ['Un halfling piedelesto può tentare di nascondersi anche se è oscurato solo da una creatura di almeno una taglia più grande. Nascondersi richiede comunque la prova e l’azione appropriate.'], 6);
  feature('gnome-lore', 'Conoscenze dell’artefice', ["Conoscenze dell'artefice", 'Artificer’s Lore', 'Inventore'], 'Lo gnomo delle rocce raddoppia la competenza nelle prove di Storia relative a oggetti magici, alchemici e tecnologici.',
    [['Congegno', '1 ora + 10 mo; massimo 3 attivi; durata 24 ore']],
    ['Con gli arnesi da inventore può creare un piccolo giocattolo meccanico, un accendino o un carillon: non armi o macchine di potenza arbitraria.', 'Astuzia gnomesca: vantaggio ai TS di Intelligenza, Saggezza e Carisma contro la magia.'], 6);
  feature('background-custom', 'Background personalizzato', ['Background', 'La Percezione duplicata', 'Maestrie iniziali'], 'Il background definisce esperienze, due competenze e le altre scelte concordate per il tuo personaggio.', [],
    ['I pacchetti del tavolo aggiungono abito, diario, borsa e 15 mo. I contatti sono legami narrativi, non garantiscono aiuti o informazioni automatici.', 'Una competenza duplicata si sostituisce con un’altra dello stesso tipo secondo la regola della fonte, concordandola con il master.'], 60);

  const condition = (id, title, aliases, summary, details) => add(`condition-${id}`, 'condition', title, aliases, summary, [], details, 358);
  condition('grappled', 'Afferrato', ['Grappled', 'In lotta'], 'La tua velocità diventa 0 e non beneficia di bonus.',
    ['Puoi continuare ad attaccare e agire. La condizione non impone di per sé svantaggio agli attacchi.', 'Finisce se chi ti afferra è incapacitato o un effetto vi separa oltre la sua portata. Puoi usare un’azione per tentare la fuga con Atletica o Acrobazia contro Atletica.']);
  condition('restrained', 'Trattenuto', ['Restrained', 'Intralciato'], 'Velocità 0; attacchi con svantaggio e gli attacchi contro di te hanno vantaggio.',
    ['Hai svantaggio ai TS Destrezza. Puoi agire, e l’effetto che ti trattiene specifica come liberarti.', 'Non è la stessa condizione di afferrato: Intralciare applica trattenuto.']);
  condition('unconscious', 'Privo di sensi', ['Unconscious', 'Incosciente', 'KO'], 'Sei incapacitato, non puoi muoverti o parlare e non percepisci ciò che ti circonda.',
    ['Lasci ciò che impugni e cadi prono. Fallisci automaticamente i TS di Forza e Destrezza.', 'Gli attacchi contro di te hanno vantaggio; un attacco che colpisce da entro 1,5 m è critico.', 'A 0 PF stabile normalmente recuperi 1 PF dopo 1d4 ore se non ricevi cure; essere privi di sensi non significa automaticamente essere stabili.']);
  condition('prone', 'Prono', ['Prone', 'A terra'], 'Puoi strisciare; rialzarti costa metà della tua velocità.',
    ['Attacchi con svantaggio. Gli attacchi da entro 1,5 m contro di te hanno vantaggio; quelli da più lontano hanno svantaggio.', 'Se la velocità è 0, per esempio perché sei afferrato, non puoi rialzarti.']);
  condition('incapacitated', 'Incapacitato', ['Incapacitated'], 'Non puoi compiere azioni né reazioni.', ['Non puoi usare azioni bonus e non puoi mantenere la concentrazione.']);
  condition('blinded', 'Accecato', ['Blinded'], 'Non vedi e fallisci automaticamente le prove che richiedono la vista.', ['I tuoi attacchi hanno svantaggio e gli attacchi contro di te hanno vantaggio.']);
  condition('charmed', 'Affascinato', ['Charmed'], 'Non puoi attaccare chi ti ha affascinato né bersagliarlo con capacità o magie dannose.', ['Chi ti ha affascinato ha vantaggio alle prove sociali per interagire con te. La condizione non implica obbedienza a qualunque ordine.']);
  condition('deafened', 'Assordato', ['Deafened'], 'Non senti e fallisci automaticamente le prove che richiedono l’udito.', ['La condizione non rende automaticamente incapaci di parlare o di fornire componenti verbali.']);
  condition('frightened', 'Spaventato', ['Frightened'], 'Finché vedi la fonte della paura, hai svantaggio a prove di caratteristica e attacchi.', ['Non puoi avvicinarti volontariamente alla fonte della paura.']);
  condition('invisible', 'Invisibile', ['Invisible'], 'Non sei visibile senza magia o sensi speciali, ma rumori e tracce possono rivelare la tua posizione.', ['I tuoi attacchi hanno vantaggio e gli attacchi contro di te hanno svantaggio secondo le interazioni della condizione 2014.', 'Essere invisibile non equivale automaticamente a essere nascosto.']);
  condition('paralyzed', 'Paralizzato', ['Paralyzed'], 'Sei incapacitato, non puoi muoverti o parlare e fallisci i TS Forza e Destrezza.', ['Gli attacchi contro di te hanno vantaggio; un attacco che ti colpisce da entro 1,5 m è critico.']);
  condition('petrified', 'Pietrificato', ['Petrified'], 'Tu e gli oggetti non magici indossati o trasportati diventate sostanza solida inanimata; il peso aumenta di dieci volte e non invecchi.', ['Sei incapacitato, immobile e inconsapevole. Fallisci i TS Forza e Destrezza; gli attacchi contro di te hanno vantaggio.', 'Hai resistenza a tutti i danni e sei immune a veleno e malattie, che restano sospesi se già presenti.']);
  condition('poisoned', 'Avvelenato', ['Poisoned'], 'Hai svantaggio ai tiri per colpire e alle prove di caratteristica.', ['Non impone di per sé svantaggio ai tiri salvezza e non infligge automaticamente danni ogni turno.']);
  condition('stunned', 'Stordito', ['Stunned'], 'Sei incapacitato, non puoi muoverti e parli solo a fatica.', ['Fallisci i TS Forza e Destrezza. Gli attacchi contro di te hanno vantaggio.']);
  condition('exhaustion', 'Indebolimento', ['Exhaustion', 'Sfinimento'], 'È una condizione cumulativa di sei livelli; i livelli si sommano.',
    ['1: svantaggio alle prove. 2: velocità dimezzata. 3: svantaggio ad attacchi e TS. 4: massimo PF dimezzato. 5: velocità 0. 6: morte.', 'Un riposo lungo con cibo e acqua riduce normalmente il livello di uno. Si applicano anche gli effetti dei livelli inferiori.']);

  const rule = (id, title, aliases, summary, facts = [], details = [], page = null) => add(`rule-${id}`, 'rule', title, aliases, summary, facts, details, page);
  rule('hp', 'Punti ferita', ['PF', 'hp', 'max_hp', 'Punti vita'], 'Misurano quanto puoi ancora resistere. Le cure non superano normalmente il massimo dei PF.', [],
    ['A 0 PF puoi diventare incosciente e dover effettuare TS morte. Danni residui pari o superiori al tuo massimo PF possono ucciderti immediatamente.', 'Un colpo in mischia che porta a 0 PF può lasciare il bersaglio privo di sensi e stabile se l’attaccante sceglie di metterlo KO.'], 96);
  rule('ac', 'Classe Armatura', ['CA', 'ac', 'Armor Class'], 'È il numero che un attacco deve raggiungere o superare per colpirti.', [],
    ['Armature e capacità definiscono diversi calcoli base: non si sommano tra loro. Copertura, scudi e altri bonus si applicano quando le loro regole lo consentono.', 'Un 20 naturale a un tiro per colpire colpisce ed è critico; un 1 naturale manca.'], 94);
  rule('speed', 'Velocità e movimento', ['Velocità', 'speed', 'Movimento'], 'Nel tuo turno puoi muoverti fino alla tua velocità, suddividendo il movimento prima e dopo le azioni.', [],
    ['Terreno difficile costa un metro aggiuntivo per ogni metro percorso. Scattare aggiunge movimento pari alla tua velocità per quel turno.', 'Uscire volontariamente dalla portata di un avversario può provocare un attacco di opportunità. Disimpegnarsi lo evita per quel turno.'], 91);
  rule('proficiency', 'Bonus di competenza', ['Competenza', 'proficiency'], 'Aggiungi il bonus quando possiedi la competenza pertinente: abilità, TS, arma o strumenti.', [['Livelli 1–4', '+2']],
    ['Normalmente non lo aggiungi più di una volta alla stessa prova e non si aggiunge ai danni delle armi. Maestria può raddoppiarlo nei casi specificati.'], 76);
  rule('ability-check', 'Prove di caratteristica', ['Prova', 'Abilità', 'Skill', 'ability-check', 'Prove', 'str', 'dex', 'con', 'int', 'wis', 'cha', 'Forza', 'Destrezza', 'Costituzione', 'Intelligenza', 'Saggezza', 'Carisma'], 'Tira 1d20 e aggiungi il modificatore della caratteristica e l’eventuale competenza; raggiungere la CD significa riuscire.', [],
    ['Per una prova contrapposta confronti i totali: a parità la situazione resta invariata.', 'Un 1 o un 20 naturale non impongono automaticamente fallimento o successo alle normali prove di caratteristica.'], 77);
  rule('saving-throw', 'Tiri salvezza', ['TS', 'Saving Throw', 'saving_throw', 'saving_throws'], 'Un tiro salvezza resiste a un pericolo: 1d20 + caratteristica + competenza se sei competente in quel TS.', [],
    ['Raggiungere la CD è un successo. L’effetto determina cosa accade in caso di successo o fallimento.', 'Nelle regole base un 1 o un 20 naturale non sono successi o fallimenti automatici ai TS ordinari. I TS morte hanno regole proprie.'], 84);
  rule('advantage', 'Vantaggio e svantaggio', ['Vantaggio', 'Svantaggio', 'Advantage', 'Disadvantage'], 'Tira due d20: con vantaggio usa il più alto; con svantaggio usa il più basso.', [],
    ['Più fonti non fanno tirare dadi ulteriori. Se hai sia vantaggio sia svantaggio si annullano, indipendentemente dal numero delle fonti.'], 76);
  rule('grapple', 'Afferrare e liberarsi', ['Presa', 'Afferrare', 'Grapple', 'Liberarsi'], 'Una presa sostituisce uno degli attacchi dell’azione Attaccare. Serve una mano libera e un bersaglio a portata, non più di una taglia più grande.',
    [['Prova', 'Atletica dell’attaccante contro Atletica o Acrobazia del difensore']],
    ['Se riesci il bersaglio è afferrato: velocità 0, ma può agire e attaccare. Un pareggio conserva la situazione precedente.', 'Per liberarsi, il bersaglio usa un’azione e contrappone Atletica o Acrobazia ad Atletica di chi lo trattiene. A parità una presa già esistente continua.', 'Chi afferra può lasciare la presa senza un’azione. Spostare una delle creature oltre la portata della presa termina la condizione.'], 95);
  rule('shove', 'Spingere', ['Spinta', 'Shove', 'Spingere via'], 'Una spinta sostituisce uno degli attacchi dell’azione Attaccare; non è normalmente un’azione bonus.',
    [['Prova', 'Atletica contro Atletica o Acrobazia a scelta del bersaglio'], ['Successo', 'Bersaglio prono oppure spinto di 1,5 m lontano da te']],
    ['Il bersaglio deve essere a portata e al massimo una taglia più grande. A parità la situazione non cambia.', 'Spingere chi afferra un compagno oltre la portata della presa può liberare il compagno. Al livello 1, dopo avere usato il tuo unico attacco non ti resta un’altra spinta.'], 96);
  rule('actions', 'Azioni nel turno', ['Azione', 'Azione bonus', 'Reazione', 'Turno'], 'Normalmente hai movimento e un’azione nel tuo turno; usi al massimo un’azione bonus solo se una capacità te la concede.', [],
    ['Azione, azione bonus e movimento sono risorse distinte. Non puoi trasformare liberamente un’azione in una seconda azione bonus.', 'Hai normalmente una reazione, che recuperi all’inizio del tuo turno. Il master gestisce le finestre di reazione prima di risolvere le conseguenze.', 'Dire che colpisci con pugno e testata non concede automaticamente due attacchi: dipende dalle capacità, come Arti marziali.'], 90);
  rule('concentration', 'Concentrazione', ['Concentrazione', 'Concentration'], 'Puoi mantenere un solo incantesimo a concentrazione alla volta. Iniziarne un altro termina il precedente.', [],
    ['Quando subisci danni devi superare un TS Costituzione: CD 10 oppure metà dei danni subiti, scegliendo il valore più alto. Fonti separate richiedono tiri separati.', 'Incapacitato o morto interrompono la concentrazione. Puoi interromperla volontariamente in qualsiasi momento senza azione.', 'Non richiede di spendere ogni turno un’azione, ma gli effetti terminano comunque alla scadenza.'], 102);
  rule('spell-components', 'Componenti degli incantesimi', ['Componenti', 'V, S, M'], 'V richiede parole; S gesti con almeno una mano libera; M l’oggetto specificato o un focus consentito.', [],
    ['Un focus o borsa dei componenti sostituisce solo materiali privi di prezzo indicato e non consumati. I componenti con costo o consumati devono essere disponibili.', 'La mano che fornisce M può fornire anche S per la stessa magia. Componenti e mani libere contano anche nelle reazioni.'], 102);
  rule('short-rest', 'Riposo breve', ['Riposo breve', 'Short Rest', 'short'], 'Almeno un’ora di riposo senza attività faticose; puoi spendere dadi vita per curarti.', [],
    ['Ogni dado cura il risultato più Costituzione, minimo 0. Puoi decidere uno alla volta quanti spenderne.', 'Le capacità con recupero breve tornano disponibili; gli slot ordinari normalmente no, salvo capacità come Magia del patto o Recupero Arcano.'], 87);
  rule('long-rest', 'Riposo lungo', ['Riposo lungo', 'Long Rest', 'long'], 'Almeno otto ore, con almeno sei ore di sonno per chi ne ha bisogno e non più di due ore di attività leggere.', [],
    ['Al termine recuperi tutti i PF e fino a metà dei dadi vita totali, minimo un dado. Recuperi le risorse che lo prevedono.', 'Puoi beneficiare di un solo riposo lungo ogni 24 ore e devi avere almeno 1 PF all’inizio. Le interruzioni e i casi delle specie si applicano secondo la fonte 2014.'], 87);
  rule('death-saves', 'Tiri salvezza contro morte', ['TS morte', 'Death Saves', 'death_saves'], 'A 0 PF, se non sei stabile, all’inizio del tuo turno tira 1d20: 10 o più è un successo, 9 o meno un fallimento.', [],
    ['Tre successi ti stabilizzano; tre fallimenti ti uccidono. Un 1 naturale vale due fallimenti; un 20 naturale ti restituisce 1 PF.', 'Danni a 0 PF causano un fallimento, oppure due se sono un critico; danni sufficienti possono uccidere sul colpo. Recuperare PF o diventare stabile azzera i conteggi.'], 97);
  rule('xp', 'Punti esperienza', ['XP', 'PE', 'xp', 'level', 'Livello'], 'Rappresentano i progressi del personaggio e le ricompense della campagna.', [],
    ['Le ricompense si assegnano una sola volta e il master applica gli importi della fonte. Salire di livello richiede aggiornare realmente capacità, risorse, scelte e PF.', 'Una promessa di pagamento non è ancora una ricompensa ricevuta.'], 56);
  rule('money', 'Monete d’oro', ['Oro', 'gold', 'Monete', 'mo'], 'Il valore economico disponibile al tuo personaggio è registrato nella sua scheda.',
    [['Conversione', '1 mo = 10 ma = 100 mr; 1 mp = 10 mo']], ['Visualizzare una scheda o un prezzo non compra, vende o consuma automaticamente nulla.'], 63);
  const skills = [
    ['acrobatics', 'Acrobazia', 'Destrezza', 'Equilibrio, capriole e movimenti agili. Può opporsi a una presa o una spinta, ma non sostituisce automaticamente ogni prova di Atletica.'],
    ['animal_handling', 'Addestrare Animali', 'Saggezza', 'Calmare o guidare un animale e comprenderne intenzioni o comportamento.'],
    ['arcana', 'Arcano', 'Intelligenza', 'Conoscenze di magia, tradizioni arcane, simboli, piani ed esseri legati alla magia.'],
    ['athletics', 'Atletica', 'Forza', 'Scalare, saltare, nuotare e compiere sforzi fisici; si usa anche per afferrare e spingere.'],
    ['deception', 'Inganno', 'Carisma', 'Mentire, celare la verità e mantenere una falsa impressione.'],
    ['history', 'Storia', 'Intelligenza', 'Ricordare eventi, popoli, regni, guerre e civiltà.'],
    ['insight', 'Intuizione', 'Saggezza', 'Interpretare intenzioni ed emozioni attraverso comportamento e indizi; non legge i pensieri.'],
    ['intimidation', 'Intimidire', 'Carisma', 'Influenzare qualcuno con minacce o atteggiamento intimidatorio, con le conseguenze della scena.'],
    ['investigation', 'Indagare', 'Intelligenza', 'Trarre deduzioni dagli indizi, esaminare oggetti e ricostruire come funziona qualcosa.'],
    ['medicine', 'Medicina', 'Saggezza', 'Diagnosticare malattie o stabilizzare una creatura morente: quest’ultimo uso normalmente richiede un’azione e CD 10.'],
    ['nature', 'Natura', 'Intelligenza', 'Conoscenze di terreno, piante, animali, clima e cicli naturali.'],
    ['perception', 'Percezione', 'Saggezza', 'Notare presenze e dettagli con vista, udito e altri sensi.'],
    ['performance', 'Intrattenere', 'Carisma', 'Coinvolgere un pubblico con musica, recitazione, danza o narrazione.'],
    ['persuasion', 'Persuasione', 'Carisma', 'Convincere con tatto, argomenti e buone maniere; non controlla la mente del bersaglio.'],
    ['religion', 'Religione', 'Intelligenza', 'Conoscenze di divinità, culti, riti e tradizioni religiose.'],
    ['sleight_of_hand', 'Rapidità di Mano', 'Destrezza', 'Movimenti precisi e discreti, come occultare piccoli oggetti o tentare un borseggio.'],
    ['stealth', 'Furtività', 'Destrezza', 'Nascondersi o passare inosservati quando la situazione lo permette.'],
    ['survival', 'Sopravvivenza', 'Saggezza', 'Seguire tracce, orientarsi, foraggiare e riconoscere pericoli naturali.']
  ];
  for (const [id, title, ability, summary] of skills) {
    rule(`skill-${id}`, title, [id], summary, [['Caratteristica abituale', ability]], ['Tira 1d20 e aggiungi il bonus mostrato nella tua scheda quando il master richiede la prova. Il contesto può richiedere un’altra caratteristica.'], 77);
  }
  window.DndRulesCatalog = {version: '2014', attribution: 'Sintesi originali in italiano dal SRD 5.1, © Wizards of the Coast LLC, CC BY 4.0. Vedi ATTRIBUZIONI.md. Eccezioni extra SRD indicate nella singola scheda.', entries};
})();
