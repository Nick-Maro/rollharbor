"""Offline level-one character creation from SRD 5.1, with explicit starter choices.

Summaries and Italian labels are original adaptations. Rules source:
https://media.dndbeyond.com/compendium-images/srd/5.1/SRD_CC_v5.1.pdf
See ATTRIBUZIONI.md for the SRD's CC BY 4.0 attribution.
No campaign save is read or written here. StateStore owns transactions.
"""
from __future__ import annotations

import copy
import secrets


ABILITY_IDS = ("str", "dex", "con", "int", "wis", "cha")
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
SKILLS = {
    "acrobatics": ("Acrobazia", "dex"), "animal_handling": ("Addestrare Animali", "wis"),
    "arcana": ("Arcano", "int"), "athletics": ("Atletica", "str"),
    "deception": ("Inganno", "cha"), "history": ("Storia", "int"),
    "insight": ("Intuizione", "wis"), "intimidation": ("Intimidire", "cha"),
    "investigation": ("Indagare", "int"), "medicine": ("Medicina", "wis"),
    "nature": ("Natura", "int"), "perception": ("Percezione", "wis"),
    "performance": ("Intrattenere", "cha"), "persuasion": ("Persuasione", "cha"),
    "religion": ("Religione", "int"), "sleight_of_hand": ("Rapidità di Mano", "dex"),
    "stealth": ("Furtività", "dex"), "survival": ("Sopravvivenza", "wis"),
}


def _class(name, description, hit_die, primary, saves, choices, recommended, order, features):
    return {"name": name, "description": description, "hit_die": hit_die,
            "primary_abilities": primary.split(), "saving_throws": saves.split(),
            "skill_choices": choices.split() if choices != "all" else list(SKILLS),
            "skill_count": len(recommended.split()), "recommended_skills": recommended.split(),
            "recommended_abilities": dict(zip(order.split(), STANDARD_ARRAY)), "features": features}


CLASSES = {
    "barbarian": _class("Barbaro", "Combattente resistente, alimentato dall'ira.", 12,
        "str con", "str con", "animal_handling athletics intimidation nature perception survival",
        "athletics survival", "str con dex wis cha int", [
            "Ira: azione bonus, 2 usi per riposo lungo; per un minuto vantaggio alle prove e TS Forza, +2 danni agli attacchi in mischia con Forza e resistenza a contundente, perforante e tagliente; niente armatura pesante. Alla fine del vostro turno termina se dal vostro turno precedente non avete attaccato una creatura ostile né subito danni; termina anche se diventate incoscienti. Non permette incantesimi o concentrazione.",
            "Difesa senza armatura: CA 10 + Destrezza + Costituzione; permette lo scudo. Il bonus ai danni dell'ira si aggiunge quando attiva, non è già negli attacchi."]),
    "bard": _class("Bardo", "Magia, parole e musica per sostenere il gruppo.", 8,
        "cha dex", "dex cha", "all", "performance persuasion perception", "cha dex con wis int str", [
            "Ispirazione bardica: azione bonus a un'altra creatura entro 18 m che possa sentirvi; un d6 entro 10 minuti a una prova, TS o attacco, dopo il d20 ma prima dell'esito. Usi pari a Carisma, minimo 1, per riposo lungo.",
            "Incantesimi di Carisma: 2 trucchetti, 4 incantesimi conosciuti di 1° e 2 slot. Rituali solo fra gli incantesimi conosciuti. Competenza iniziale in tre strumenti: liuto, flauto e tamburo; nell'equipaggiamento è fornito il liuto."]),
    "cleric": _class("Chierico", "Guaritore e incantatore divino con armatura e scudo.", 8,
        "wis str", "wis cha", "history insight medicine persuasion religion",
        "medicine insight", "wis con str cha dex int", [
            "Dominio iniziale SRD: Vita. Competenza nelle armature pesanti. Discepolo della Vita: le cure tramite incantesimi di livello 1 o superiore recuperano 2 + livello dell'incantesimo PF aggiuntivi.",
            "Incantesimi di Saggezza: 3 trucchetti, 2 slot di 1°; preparate livello + modificatore Saggezza incantesimi (minimo 1), più Benedizione e Cura Ferite sempre preparati. Rituali per gli incantesimi preparati. Incanalare Divinità arriva al livello 2."]),
    "druid": _class("Druido", "Magia naturale, esplorazione e conoscenza degli animali.", 8,
        "wis con", "int wis", "arcana animal_handling insight medicine nature perception religion survival",
        "nature animal_handling", "wis con dex int cha str", [
            "Druidico: conoscete la lingua segreta dei druidi. Competenza negli strumenti da erborista. Non usate armature o scudi di metallo.",
            "Incantesimi di Saggezza: 2 trucchetti e 2 slot di 1°; preparate livello + Saggezza incantesimi (minimo 1), modificabili dopo un riposo lungo. Rituali se preparati. Forma Selvatica e circolo arrivano al livello 2."]),
    "fighter": _class("Guerriero", "Esperto d'armi, solido e immediato da giocare.", 10,
        "str con", "str con", "acrobatics animal_handling athletics history insight intimidation perception survival",
        "athletics perception", "str con dex wis cha int", [
            "Stile iniziale: Duellare, +2 danni con un'arma da mischia a una mano e nessun'altra arma; lo scudo è compatibile. Il bonus è già incluso nella spada lunga.",
            "Recuperare energie: azione bonus, recuperate 1d10 + 1 PF, una volta per riposo breve o lungo. Azione Impetuosa arriva al livello 2; archetipo al 3."]),
    "monk": _class("Monaco", "Agile combattente senz'armatura, con colpi e armi leggere.", 8,
        "dex wis", "str dex", "acrobatics athletics history insight religion stealth",
        "acrobatics stealth", "dex wis con str int cha", [
            "Difesa senza armatura: CA 10 + Destrezza + Saggezza senza armatura né scudo.",
            "Arti marziali: per colpi senz'armi e armi da monaco potete usare Destrezza e un d4; dopo un attacco con un'arma da monaco o senz'armi potete effettuare un colpo senz'armi come azione bonus. Richiede niente armatura né scudo e soltanto armi da monaco. Ki e movimento extra arrivano al livello 2. Competenza iniziale in flauto; lo strumento non è fornito dall'equipaggiamento di classe."]),
    "paladin": _class("Paladino", "Protettore in armatura, con cure e percezione del soprannaturale.", 10,
        "str cha", "wis cha", "athletics insight intimidation medicine persuasion religion",
        "athletics persuasion", "str cha con wis dex int", [
            "Imposizione delle mani: riserva di 5 PF per riposo lungo; azione e contatto per distribuire cure. Spendere 5 punti può curare una malattia o neutralizzare un veleno; non influenza non morti o costrutti.",
            "Percezione del divino: azione, fino al termine del turno successivo individuate celestiali, immondi e non morti entro 18 m senza copertura totale, e luoghi/oggetti consacrati o sconsacrati. Usi 1 + Carisma per riposo lungo. Incantesimi, stile e Punizione Divina arrivano al livello 2; giuramento al 3."]),
    "ranger": _class("Ranger", "Esploratore, arciere e conoscitore delle terre selvagge.", 10,
        "dex wis", "str dex", "animal_handling athletics insight investigation nature perception stealth survival",
        "perception stealth survival", "dex wis con str int cha", [
            "Nemico prescelto iniziale: bestie. Vantaggio a Sopravvivenza per seguirne le tracce e alle prove Intelligenza per ricordarne informazioni. Nessun bonus automatico ai danni.",
            "Esploratore nato: foreste. Raddoppiate competenza nelle prove Intelligenza/Saggezza competenti relative a questo terreno. Dopo un'ora di viaggio nel terreno: difficile non rallenta il gruppo, non vi perdete salvo magia, restate allerta, foraggiate il doppio e leggete meglio le tracce; da soli potete muovervi furtivi a passo normale. Incantesimi e stile arrivano al livello 2."]),
    "rogue": _class("Ladro", "Specialista in furtività, abilità e attacchi precisi.", 8,
        "dex int", "dex int", "acrobatics athletics deception insight intimidation investigation perception performance persuasion sleight_of_hand stealth",
        "stealth sleight_of_hand investigation perception", "dex int con cha wis str", [
            "Maestria: competenza raddoppiata nelle prime due abilità di classe selezionate; i bonus della scheda la includono.",
            "Attacco furtivo: +1d6 una volta per turno su un colpo con arma accurata o a distanza, con vantaggio; basta invece un nemico del bersaglio entro 1,5 m, non incapacitato, se non avete svantaggio. Non è sempre attivo e il dado si aggiunge quando applicabile. Gergo ladresco e competenza negli arnesi da scasso. Azione Scaltra arriva al livello 2."]),
    "sorcerer": _class("Stregone", "Magia innata e sangue draconico, con incantesimi di Carisma.", 6,
        "cha con", "con cha", "arcana deception insight intimidation persuasion religion",
        "arcana persuasion", "cha con dex wis int str", [
            "Origine iniziale SRD: discendenza draconica, drago rosso (fuoco). Parlate Draconico; raddoppiate la competenza quando applicabile alle prove Carisma per interagire con draghi. Non avete ancora resistenza al fuoco.",
            "Resilienza draconica: +1 PF per livello, già incluso; senza armatura CA 13 + Destrezza. 4 trucchetti, 2 incantesimi conosciuti di 1° e 2 slot. Punti stregoneria arrivano al livello 2, Metamagia al 3."]),
    "warlock": _class("Warlock", "Magia di un patto, pochi slot che tornano con riposi brevi.", 8,
        "cha con", "wis cha", "arcana deception history intimidation investigation nature religion",
        "arcana deception", "cha con dex int wis str", [
            "Patrono iniziale SRD: l'Immondo. Benedizione dell'Oscuro: quando riducete una creatura ostile a 0 PF ottenete PF temporanei pari a Carisma + livello (minimo 1); non si sommano ad altri PF temporanei.",
            "Magia del patto: 2 trucchetti, 2 incantesimi conosciuti e 1 slot di 1°, recuperato con riposo breve o lungo. La lista ampliata dell'Immondo aggiunge possibilità di scelta, non incantesimi conosciuti gratuiti. Suppliche Occulte arrivano al livello 2, dono del patto al 3."]),
    "wizard": _class("Mago", "Studioso della magia con grimorio e rituali.", 6,
        "int con", "int wis", "arcana history insight investigation medicine religion",
        "arcana investigation", "int con dex wis cha str", [
            "Grimorio: 6 incantesimi di 1°; preparate livello + Intelligenza (minimo 1), con 2 slot di 1°. 3 trucchetti. Potete lanciare come rituale un incantesimo rituale del grimorio anche se non preparato.",
            "Recupero Arcano: una volta al giorno dopo un riposo breve recuperate slot per un totale pari a metà livello da mago arrotondata in eccesso (1 slot di 1° ora). La tradizione arcana arriva al livello 2."]),
}

SPECIES = {
    "human": {"name": "Umano", "description": "Versatile: +1 a tutte le caratteristiche.",
        "bonuses": dict.fromkeys(ABILITY_IDS, 1), "speed": 9,
        "features": ["Umano SRD standard: +1 a tutte le caratteristiche; taglia Media, nessun talento iniziale."], "languages": ["Comune", "Elfico"]},
    "high_elf": {"name": "Elfo alto", "description": "+2 Destrezza, +1 Intelligenza; percezione e un trucchetto da mago.",
        "bonuses": {"dex": 2, "int": 1}, "speed": 9,
        "features": ["Taglia Media; scurovisione 18 m; competenza in Percezione.", "Retaggio fatato: vantaggio ai TS per evitare affascinato, immunità al sonno magico. Trance: 4 ore di meditazione sostituiscono il sonno; i tempi dei riposi si concordano col master.", "Addestramento con spada lunga, spada corta, arco lungo e arco corto. Trucchetto razziale iniziale: Messaggio, usa Intelligenza."],
        "languages": ["Comune", "Elfico", "Nanico"]},
    "hill_dwarf": {"name": "Nano delle colline", "description": "+2 Costituzione, +1 Saggezza; +1 PF per livello.",
        "bonuses": {"con": 2, "wis": 1}, "speed": 7.5,
        "features": ["Taglia Media; scurovisione 18 m. Resistenza ai danni da veleno e vantaggio ai TS contro veleno.", "Robustezza nanica: +1 PF per livello, già incluso. La velocità non diminuisce per l'armatura pesante.", "Competenza in ascia da battaglia, ascia, martello leggero e martello da guerra; utensili da muratore. Nelle prove Storia sull'origine di opere in pietra siete competenti e raddoppiate il bonus di competenza."],
        "languages": ["Comune", "Nanico"]},
    "lightfoot_halfling": {"name": "Halfling piedelesto", "description": "+2 Destrezza, +1 Carisma; fortunato e furtivo.",
        "bonuses": {"dex": 2, "cha": 1}, "speed": 7.5,
        "features": ["Taglia Piccola: svantaggio agli attacchi con armi pesanti. Fortunato: su un 1 naturale a un attacco, prova o TS potete ritirare il d20 e dovete usare il nuovo risultato.", "Coraggioso: vantaggio ai TS per evitare spaventato. Agilità: attraversate lo spazio di creature più grandi. Furtività naturale: potete nascondervi anche dietro una creatura di almeno una taglia più grande."],
        "languages": ["Comune", "Halfling"]},
    "rock_gnome": {"name": "Gnomo delle rocce", "description": "+2 Intelligenza, +1 Costituzione; resistente alla magia.",
        "bonuses": {"int": 2, "con": 1}, "speed": 7.5,
        "features": ["Taglia Piccola: svantaggio agli attacchi con armi pesanti; scurovisione 18 m. Astuzia gnomesca: vantaggio ai TS Intelligenza, Saggezza e Carisma contro magia.", "Conoscenze dell'artefice: raddoppiate competenza alle prove Storia su oggetti magici, alchemici e tecnologici. Competenza negli arnesi da inventore; con un'ora e 10 mo di materiali costruite un congegno minuscolo per 24 ore (giocattolo, accendino o carillon), massimo tre attivi."],
        "languages": ["Comune", "Gnomesco"]},
}

# Original background packages use the SRD's custom-background proficiency rule.
# Their modest equipment and narrative contacts are declared table additions.
BACKGROUNDS = {
    "studente": {"name": "Studente", "skills": ["history", "arcana"], "languages": ["Nanico", "Draconico"],
        "description": "Background personalizzato: Storia, Arcano e due lingue; un precedente insegnante come contatto narrativo."},
    "viandante": {"name": "Viandante", "skills": ["survival", "animal_handling"], "languages": ["Elfico", "Gigante"],
        "description": "Background personalizzato: Sopravvivenza, Addestrare Animali e due lingue; un compagno di viaggio come contatto."},
    "guardia": {"name": "Guardia", "skills": ["athletics", "intimidation"], "languages": ["Orchesco", "Nanico"],
        "description": "Background personalizzato: Atletica, Intimidire e due lingue; un ex collega come contatto narrativo."},
    "accolito": {"name": "Accolito", "skills": ["insight", "religion"], "languages": ["Celestiale", "Infernale"],
        "description": "Background personalizzato: Intuizione, Religione e due lingue; un mentore religioso come contatto. Non è il pacchetto completo dell'Accolito ufficiale."},
}

BUILD_FIELDS = {"class_id", "species_id", "name", "abilities", "skills", "background_id", "description"}


def catalog() -> dict:
    return {"edition": "SRD 5.1 (regole del 2014)", "standard_array": STANDARD_ARRAY[:],
            "classes": [{"id": key, **copy.deepcopy(value)} for key, value in CLASSES.items()],
            "species": [{"id": key, **copy.deepcopy(value)} for key, value in SPECIES.items()],
            "skills": [{"id": key, "name": value[0], "ability": value[1]} for key, value in SKILLS.items()],
            "backgrounds": [{"id": key, **copy.deepcopy(value)} for key, value in BACKGROUNDS.items()],
            "notes": "Le classi sono tutte ripetibili. Equipaggiamento, lingue, incantesimi e altre scelte iniziali hanno un assetto pronto, visibile in scheda e modificabile col master prima di iniziare. Cinque specie SRD complete disponibili nel creatore. I background e il loro kit sono adattamenti originali del tavolo."}


def _ensure(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, name, maximum, empty=False):
    _ensure(isinstance(value, str), f"{name}: serve un testo.")
    _ensure(len(value) <= maximum and (empty or value.strip()), f"{name}: lunghezza non valida.")
    _ensure(not any((ord(c) < 32 and c not in "\r\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value), f"{name}: caratteri non validi.")
    return value.strip()


def build_character(payload: dict, character_id: str | None = None) -> dict:
    """Validate all player choices, then derive a level-one sheet deterministically."""
    _ensure(isinstance(payload, dict) and set(payload) <= BUILD_FIELDS, "Campi del personaggio sconosciuti.")
    class_id, species_id = payload.get("class_id"), payload.get("species_id")
    _ensure(isinstance(class_id, str) and class_id in CLASSES, "Scegliete una delle dodici classi.")
    _ensure(isinstance(species_id, str) and species_id in SPECIES, "Specie non disponibile nel creatore.")
    cls, species = CLASSES[class_id], SPECIES[species_id]
    name = _text(payload.get("name"), "Nome", 80)
    description = _text(payload.get("description", ""), "Descrizione", 2000, True)
    base = payload.get("abilities", cls["recommended_abilities"])
    _ensure(isinstance(base, dict) and set(base) == set(ABILITY_IDS), "Servono le sei caratteristiche.")
    _ensure(all(type(value) is int for value in base.values()) and sorted(base.values()) == sorted(STANDARD_ARRAY),
            "Assegnate una volta ciascuno 15, 14, 13, 12, 10, 8 prima dei bonus della specie.")
    chosen_skills = payload.get("skills", cls["recommended_skills"])
    _ensure(isinstance(chosen_skills, list) and all(isinstance(s, str) for s in chosen_skills), "Abilità non valide.")
    _ensure(len(chosen_skills) == cls["skill_count"] and len(set(chosen_skills)) == len(chosen_skills)
            and set(chosen_skills) <= set(cls["skill_choices"]), f"Scegliete {cls['skill_count']} abilità distinte dalla lista di classe.")
    background_id = payload.get("background_id", "studente")
    _ensure(isinstance(background_id, str) and background_id in BACKGROUNDS, "Background non disponibile.")
    background = BACKGROUNDS[background_id]
    abilities = {key: base[key] + species["bonuses"].get(key, 0) for key in ABILITY_IDS}
    modifiers = {key: (value - 10) // 2 for key, value in abilities.items()}
    feats = copy.deepcopy(species["features"] + cls["features"])
    trained = list(chosen_skills)
    if species_id == "high_elf":
        elf_skill = "perception" if "perception" not in trained else next(s for s in SKILLS if s not in trained)
        trained.append(elf_skill)
        if elf_skill != "perception":
            feats.append(f"La Percezione duplicata tra classe e specie è sostituita da {SKILLS[elf_skill][0]}; potete scegliere un'altra abilità col master.")
    background_skills = []
    for skill in background["skills"]:
        selected = skill if skill not in trained else next(s for s in SKILLS if s not in trained)
        if selected != skill:
            feats.append(f"Background: la competenza duplicata in {SKILLS[skill][0]} è sostituita da {SKILLS[selected][0]} secondo la regola SRD sulle competenze duplicate; potete concordare un'altra abilità col master.")
        trained.append(selected)
        background_skills.append(selected)
    skills = {key: modifiers[ability] + (2 if key in trained else 0) for key, (_, ability) in SKILLS.items()}
    if class_id == "rogue":
        for key in chosen_skills[:2]:
            skills[key] += 2
        feats.append("Maestrie iniziali: " + ", ".join(SKILLS[key][0] for key in chosen_skills[:2]) + ".")
    hp = cls["hit_die"] + modifiers["con"] + int(species_id == "hill_dwarf") + int(class_id == "sorcerer")
    inventory, attacks, resources = [], [], []
    def item(label, qty=1):
        inventory.append({"name": label, "qty": qty})
    def attack(label, die, ability="str", bonus_damage=0):
        value = modifiers[ability]
        attacks.append({"name": label, "bonus": value + 2, "damage": f"{die}{value + bonus_damage:+d}"})
    def resource(key, label, maximum, reset="long"):
        resources.append({"id": key, "name": label, "max": maximum, "current": maximum, "reset": reset})
    def ranged_crossbow():
        item("Balestra leggera"); item("Quadrello", 20)
        attack("Balestra leggera · 24/96 m, ricarica, due mani", "1d8", "dex")
    def dagger(count=1):
        item("Pugnale", count)
        attack("Pugnale · accurata, lancio 6/18 m", "1d4", "dex" if modifiers["dex"] >= modifiers["str"] else "str")
    def finesse_sword(label="Spada corta", die="1d6"):
        item(label)
        attack(label + " · accurata", die, "dex" if modifiers["dex"] >= modifiers["str"] else "str")
    def pack(label):
        # List consumables rather than a vague pack that would hide rations/torches.
        if label == "esploratore":
            for label2, qty in (("Zaino",1),("Giaciglio",1),("Gavetta",1),("Acciarino",1),("Torcia",10),("Razione giornaliera",10),("Otre pieno",1),("Corda di canapa da 15 metri",1)):
                item(label2, qty)
        elif label == "studioso":
            for label2, qty in (("Zaino",1),("Libro di studio",1),("Inchiostro (boccetta)",1),("Pennino",1),("Pergamena (foglio)",10),("Sacchetto di sabbia",1),("Coltellino",1)):
                item(label2, qty)
        else:
            for label2, qty in (("Zaino",1),("Giaciglio",1),("Costume di scena",2),("Candela",5),("Razione giornaliera",5),("Otre pieno",1),("Trucchi per il volto",1)):
                item(label2, qty)
    dex, strength = modifiers["dex"], modifiers["str"]
    armor_kind, armor_base = "none", 10
    shields = False
    if class_id == "barbarian":
        ac = 10 + dex + modifiers["con"]
        small = species_id in ("lightfoot_halfling", "rock_gnome")
        item("Ascia da battaglia" if small else "Ascia bipenne")
        attack("Ascia da battaglia · due mani" if small else "Ascia bipenne · pesante, due mani", "1d10" if small else "1d12")
        item("Ascia", 2); attack("Ascia · leggera, lancio 6/18 m", "1d6")
        item("Giavellotto", 4); attack("Giavellotto · lancio 9/36 m", "1d6")
        resource("rage", "Ira", 2); pack("esploratore")
    elif class_id in ("fighter", "paladin", "cleric"):
        armor_kind, armor_base, shields = "heavy", 16, True
        ac = 18; item("Cotta di maglia"); item("Scudo")
        if class_id == "cleric":
            item("Mazza"); attack("Mazza", "1d6"); ranged_crossbow(); item("Simbolo sacro")
        else:
            item("Spada lunga"); attack("Spada lunga · una mano", "1d8", bonus_damage=2 if class_id == "fighter" else 0)
            if class_id == "fighter":
                item("Ascia", 2); attack("Ascia · lancio 6/18 m", "1d6")
                resource("second_wind", "Recuperare energie · 1d10+1 PF", 1, "short")
            else:
                item("Giavellotto", 5); attack("Giavellotto · lancio 9/36 m", "1d6"); item("Simbolo sacro")
                resource("lay_on_hands", "Imposizione delle mani · PF", 5)
                resource("divine_sense", "Percezione del divino", max(0, 1 + modifiers["cha"]))
        pack("esploratore")
    elif class_id == "monk":
        ac = 10 + dex + modifiers["wis"]
        finesse_sword(); item("Dardo", 10); attack("Dardo · lancio 6/18 m", "1d4", "dex" if dex >= strength else "str")
        attack("Colpo senz'armi · arti marziali", "1d4", "dex" if dex >= strength else "str")
        pack("esploratore")
    elif class_id == "sorcerer":
        ac = 13 + dex
        ranged_crossbow(); dagger(2); item("Focus arcano"); pack("esploratore")
    elif class_id == "wizard":
        ac = 10 + dex
        dagger(); item("Focus arcano"); item("Grimorio"); pack("studioso")
        resource("arcane_recovery", "Recupero Arcano · 1 slot di 1°", 1)
    else:
        armor_kind, armor_base = "light", 11
        ac = 11 + dex; item("Armatura di cuoio")
        if class_id == "bard":
            finesse_sword("Stocco", "1d8"); dagger(); item("Liuto"); pack("intrattenitore")
            resource("bardic_inspiration", "Ispirazione bardica · d6", max(1, modifiers["cha"]))
        elif class_id == "rogue":
            finesse_sword("Stocco", "1d8"); item("Arco corto"); item("Freccia",20); item("Faretra")
            attack("Arco corto · 24/96 m, due mani", "1d6", "dex")
            dagger(2); item("Arnesi da scasso"); pack("esploratore")
        elif class_id == "ranger":
            finesse_sword(); item("Spada corta")
            attack("Seconda spada corta · azione bonus, senza bonus positivo ai danni", "1d6", "dex" if dex >= strength else "str", -max(dex, strength, 0))
            item("Arco lungo"); item("Freccia",20); item("Faretra")
            attack("Arco lungo · 45/180 m, pesante, due mani", "1d8", "dex"); pack("esploratore")
        elif class_id == "druid":
            shields = True; ac += 2; item("Scudo di legno"); finesse_sword("Scimitarra")
            item("Focus druidico"); pack("esploratore")
        else:
            ranged_crossbow(); dagger(2); item("Bastone ferrato"); attack("Bastone ferrato · una mano", "1d6")
            item("Focus arcano"); pack("studioso")
    speed = species["speed"]
    if armor_kind == "heavy" and abilities["str"] < 13 and species_id != "hill_dwarf":
        speed -= 3
        feats.append("Forza inferiore a 13 con cotta di maglia: velocità ridotta di 3 m, già incluso. La cotta impone svantaggio a Furtività.")
    elif armor_kind == "heavy":
        feats.append("La cotta di maglia impone svantaggio alle prove di Furtività.")
    resource("hit_die", f"Dado vita d{cls['hit_die']}", 1)
    spell_info = _spells(class_id, modifiers, attack, resource)
    if species_id == "high_elf":
        spell_info["cantrips"].append("Messaggio · elfo alto, Intelligenza")
        if spell_info["ability"] is None:
            spell_info.update(ability="int", dc=10 + modifiers["int"], attack_bonus=2 + modifiers["int"])
            spell_info["notes"] = "Il solo trucchetto razziale è Messaggio e usa Intelligenza; non richiede attacchi né tiri salvezza e non consuma slot. Nessun incantesimo di classe al livello 1."
    for label in ("Abito comune", "Diario del passato", "Borsa da cintura"):
        item(label)
    feats.append(background["description"] + " Kit originale del tavolo: abito, diario, borsa e 15 mo. Il contatto è un legame narrativo; non garantisce aiuti automatici.")
    tools = {"bard": ["Liuto", "Flauto", "Tamburo"], "druid": ["Strumenti da erborista"],
             "rogue": ["Arnesi da scasso"], "monk": ["Flauto"]}.get(class_id, [])[:]
    if species_id == "hill_dwarf": tools.append("Utensili da muratore")
    if species_id == "rock_gnome": tools.append("Arnesi da inventore")
    languages = species["languages"][:]
    extra_languages = ["Druidico"] if class_id == "druid" else ["Draconico"] if class_id == "sorcerer" else []
    # Duplicate language selections are replaced by a different permitted language.
    for language in extra_languages + background["languages"]:
        if language in languages:
            language = next(x for x in ("Elfico", "Nanico", "Draconico", "Gigante", "Gnomesco", "Halfling", "Orchesco", "Goblin") if x not in languages)
        languages.append(language)
    armor_prof, weapon_prof = _proficiencies(class_id, species_id)
    return {"id": character_id or "pc_" + secrets.token_hex(8), "name": name,
        "class_id": class_id, "species_id": species_id, "class": cls["name"], "species": species["name"],
        "level": 1, "xp": 0, "hp": hp, "max_hp": hp, "ac": ac, "speed": speed, "proficiency": 2,
        "abilities": abilities, "skills": skills, "attacks": attacks, "resources": resources,
        "inventory": inventory, "gold": 15, "description": description,
        "saving_throws": {key: modifiers[key] + (2 if key in cls["saving_throws"] else 0) for key in ABILITY_IDS},
        "saving_throw_proficiencies": cls["saving_throws"][:], "features": feats,
        "spells": spell_info, "proficiencies": {"armor": armor_prof, "weapons": weapon_prof,
            "tools": tools, "languages": languages},
        "background": background["name"], "background_skills": background_skills,
        "equipment_state": {"armor": armor_kind, "armor_base_ac": armor_base, "shield": shields},
        "creation": {"class_id": class_id, "species_id": species_id, "base_abilities": dict(base),
            "skills": chosen_skills[:], "background_id": background_id, "description": description}}


def _proficiencies(class_id, species_id):
    if class_id in ("fighter", "paladin"):
        armor = ["Armature leggere, medie e pesanti", "Scudi"]
    elif class_id in ("barbarian", "ranger", "druid", "cleric"):
        armor = ["Armature leggere e medie", "Scudi"]
        if class_id == "cleric": armor.append("Armature pesanti · dominio della Vita")
        if class_id == "druid": armor.append("Nessuna armatura o scudo di metallo")
    elif class_id in ("bard", "rogue", "warlock"):
        armor = ["Armature leggere"]
    else: armor = []
    if class_id in ("fighter", "paladin", "ranger", "barbarian"):
        weapons = ["Armi semplici e da guerra"]
    elif class_id in ("bard", "rogue"):
        weapons = ["Armi semplici", "Balestra a mano", "Spada lunga", "Stocco", "Spada corta"]
    elif class_id in ("sorcerer", "wizard"):
        weapons = ["Pugnale", "Dardo", "Fionda", "Bastone ferrato", "Balestra leggera"]
    elif class_id == "druid":
        weapons = ["Randello", "Pugnale", "Dardo", "Giavellotto", "Mazza", "Bastone ferrato", "Scimitarra", "Falcetto", "Fionda", "Lancia"]
    else:
        weapons = ["Armi semplici"]
        if class_id == "monk": weapons.append("Spada corta")
    if species_id == "high_elf": weapons.append("Spada lunga, spada corta, arco lungo e arco corto · elfo")
    if species_id == "hill_dwarf": weapons.append("Ascia da battaglia, ascia, martello leggero e martello da guerra · nano")
    return armor, weapons


def _spells(class_id, mods, attack, resource):
    ability = {"bard": "cha", "cleric": "wis", "druid": "wis", "sorcerer": "cha", "warlock": "cha", "wizard": "int"}.get(class_id)
    result = {"ability": ability, "dc": None, "attack_bonus": None, "cantrips": [], "known": [], "prepared": [], "notes": "Nessun incantesimo di classe al livello 1."}
    if not ability: return result
    bonus = mods[ability]
    result.update(dc=10 + bonus, attack_bonus=2 + bonus)
    cantrips = {
        "bard": ["Beffa Crudele · TS Saggezza, 1d4 psichici e svantaggio al prossimo attacco entro il suo prossimo turno", "Mano Magica"],
        "cleric": ["Fiamma Sacra · TS Destrezza, 1d8 radiosi; ignora copertura per questo TS", "Guida · concentrazione, +1d4 a una prova di caratteristica", "Taumaturgia"],
        "druid": ["Guida · concentrazione, +1d4 a una prova di caratteristica", "Produrre Fiamma · 1d8 fuoco"],
        "sorcerer": ["Dardo di Fuoco · 1d10 fuoco", "Raggio di Gelo · 1d8 freddo, velocità -3 m fino all'inizio del vostro prossimo turno", "Mano Magica", "Illusione Minore"],
        "warlock": ["Deflagrazione Occulta · 1d10 forza", "Mano Magica"],
        "wizard": ["Dardo di Fuoco · 1d10 fuoco", "Mano Magica", "Illusione Minore"],
    }
    known = {
        "bard": ["Parola Guaritrice", "Sonno", "Luminescenza", "Onda Tonante"],
        "cleric": ["Parola Guaritrice", "Individuazione del Magico", "Scudo della Fede", "Dardo Tracciante", "Santuario", "Protezione dal Bene e dal Male", "Comando"],
        "druid": ["Intralciare", "Parola Guaritrice", "Bacche Benefiche", "Individuazione del Magico", "Amicizia con gli Animali", "Onda Tonante", "Passo Veloce"],
        "sorcerer": ["Dardo Incantato", "Scudo"],
        "warlock": ["Armatura di Agathys", "Mani Brucianti"],
        "wizard": ["Dardo Incantato", "Scudo", "Sonno", "Armatura Magica", "Individuazione del Magico", "Trova Famiglio"],
    }
    result["cantrips"] = cantrips[class_id][:]
    if class_id in ("cleric", "druid"):
        result["prepared"] = known[class_id][:max(1, 1 + bonus)]
        if class_id == "cleric": result["prepared"] += ["Benedizione · dominio", "Cura Ferite · dominio"]
        result["notes"] = "Conoscete la lista SRD della classe; qui sono indicati soltanto gli incantesimi inizialmente preparati. Cambiabili dopo un riposo lungo. I trucchetti non consumano slot. Concentratevi su un solo incantesimo alla volta."
    elif class_id == "wizard":
        result["known"] = known[class_id][:]
        result["prepared"] = known[class_id][:max(1, 1 + bonus)]
        result["notes"] = "Conosciuti = grimorio. Preparati = pronti per gli slot. I rituali nel grimorio non devono essere preparati. Trova Famiglio richiede 10 mo di reagenti consumati, da procurare: nessun famiglio è già evocato. Armatura Magica e Scudo non sono già attivi nella CA."
    else:
        result["known"] = known[class_id][:]
        result["notes"] = "Assetto iniziale legale, modificabile col master prima della partita. I trucchetti non consumano slot. Gli incantesimi con concentrazione sono limitati a uno alla volta."
    if class_id == "warlock":
        resource("pact_slot_1", "Magia del patto · slot di 1°", 1, "short")
    else:
        resource("spell_slot_1", "Incantesimi · slot di 1°", 2)
    if class_id in ("sorcerer", "wizard"):
        attack("Dardo di Fuoco · attacco incantesimo, 36 m", "1d10", ability, -mods[ability])
        if class_id == "sorcerer": attack("Raggio di Gelo · attacco incantesimo, 18 m", "1d8", ability, -mods[ability])
    if class_id == "warlock": attack("Deflagrazione Occulta · attacco incantesimo, 36 m", "1d10", ability, -mods[ability])
    if class_id == "druid": attack("Produrre Fiamma · attacco incantesimo, 9 m", "1d8", ability, -mods[ability])
    return result
