"""Private DM tools for the active campaign pack. Never exposed as a web API."""
from __future__ import annotations

import argparse
import hashlib
import math
import mmap
from pathlib import Path
import re
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from engine import (CampaignError, StateStore, identifier, integer, list_field,
                    object_field, read_json, require, text_field)
from tools.dnd import emit, JsonParser


def relative_path(root: Path, value: str, label: str) -> Path:
    text_field(value, label, 1000)
    # Normalize both sides of the containment check. Windows temporary roots
    # may use an 8.3 alias while resolving a child expands its long path.
    root = Path(root).resolve()
    candidate = Path(value)
    require(not candidate.is_absolute(), f"{label}: serve un percorso relativo alla cartella del tavolo.")
    resolved = (root / candidate).resolve()
    require(resolved.is_relative_to(root), f"{label}: il percorso deve restare nella cartella del tavolo.")
    return resolved


def load_context(root: Path):
    store = StateStore(root)
    table = store.table()
    campaign_id = identifier(table["state"]["campaign_id"], "campaign_id")
    pack = root / "campaigns" / campaign_id
    return store, table, pack


def load_catalog(pack: Path, campaign_id: str) -> dict:
    catalog = object_field(read_json(pack / "locations-private.json"), "catalogo")
    require(catalog.get("campaign_id") == campaign_id, "Il catalogo non corrisponde alla campagna attiva.")
    entries = list_field(catalog.get("locations"), "catalogo.locations", 100)
    known = set()
    for entry in entries:
        object_field(entry, "catalogo.entry")
        integer(entry.get("refpage"), "catalogo.refpage", 1, 10000)
        text_field(entry.get("precondition"), "catalogo.precondition", 6000)
        location = object_field(entry.get("location"), "catalogo.location")
        require(set(location) == {"id", "name", "type", "x", "y", "description", "actions"},
                "Il luogo pubblico contiene campi mancanti o riservati.")
        place_id = identifier(location.get("id"), "catalogo.location.id")
        require(place_id not in known, "ID duplicato nel catalogo.")
        known.add(place_id)
        text_field(location.get("name"), "catalogo.location.name", 120)
        text_field(location.get("type"), "catalogo.location.type", 80)
        text_field(location.get("description"), "catalogo.location.description", 4000, empty=True)
        for axis, maximum in (("x", 1000), ("y", 680)):
            value = location.get(axis)
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum,
                    f"catalogo.location.{axis}: coordinata fuori mappa.")
        for action in list_field(location.get("actions"), "catalogo.location.actions", 12):
            text_field(action, "catalogo.location.action", 500)
        connections = list_field(entry.get("connect", []), "catalogo.connect", 100)
        for connection in connections:
            identifier(connection, "catalogo.connect.id")
        require(len(set(connections)) == len(connections) and place_id not in connections,
                "Collegamenti duplicati o riferiti al luogo stesso.")
    return catalog


def reveal_location(store: StateStore, table: dict, catalog: dict, place_id: str, revision: int) -> dict:
    identifier(place_id, "id")
    integer(revision, "expected_revision", 0, 10**12)
    state = table["state"]
    if revision != state["revision"]:
        raise CampaignError(f"Revisione non aggiornata: attesa {revision}, attuale {state['revision']}. Rileggi lo stato.",
                            "revision_conflict", 409)
    entry = next((row for row in catalog["locations"] if row["location"]["id"] == place_id), None)
    require(entry is not None, "Luogo non presente nel catalogo della campagna attiva.")
    public = {location["id"]: location for location in table["world"]["locations"]}
    if place_id in public:
        require(public[place_id] == entry["location"],
                "Questo ID esiste già con dati diversi. Non sovrascrivo le modifiche del master.")
        if place_id in state["discovered"]:
            # Check again under the engine lock, including for a no-op, so a
            # concurrent browser write cannot silently accept a stale revision.
            saved, _ = store.mutate(lambda current: None, revision)
            return {"ok": True, "campaign_id": saved["campaign_id"], "revision": saved["revision"],
                    "location_id": place_id, "already_revealed": True, "refpage": entry["refpage"]}
        saved, _ = store.commit({"discovered": state["discovered"] + [place_id]}, revision)
        connections = []
    else:
        connections = [connection for connection in entry.get("connect", []) if connection in public]
        saved, _ = store.add_location(entry["location"], revision, connect=connections, discover=True)
    return {"ok": True, "campaign_id": saved["campaign_id"], "revision": saved["revision"],
            "location_id": place_id, "already_revealed": False, "refpage": entry["refpage"],
            "connected_to": connections, "location_id_party": saved["location_id"],
            "notice": "Luogo rivelato; gruppo, tempo e scena non sono stati spostati."}


def source_info(root: Path, pack: Path) -> dict:
    manifest = object_field(read_json(pack / "source.json"), "source")
    page_count = integer(manifest.get("page_count"), "source.page_count", 1, 10000)
    source_path = relative_path(root, manifest.get("path"), "source.path")
    digest = manifest.get("sha256")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            "source.sha256: impronta SHA-256 non valida.")
    ocr_path = relative_path(root, manifest.get("ocr_path"), "source.ocr_path")
    available = [n for n in range(1, page_count + 1) if (ocr_path / f"page-{n:03d}.txt").is_file()]
    result = {"source": manifest, "pdf_exists": source_path.is_file(), "expected_page_count": page_count,
              "ocr": {"available": len(available), "expected": page_count,
                      "complete": len(available) == page_count,
                      "missing": [n for n in range(1, page_count + 1) if n not in available]}}
    return result


def verify_source(root: Path, pack: Path) -> dict:
    result = source_info(root, pack)
    manifest = result["source"]
    pdf = relative_path(root, manifest["path"], "source.path")
    problems = []
    if not pdf.is_file():
        problems.append("PDF originale non trovato.")
    else:
        digest = hashlib.sha256()
        with pdf.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual_hash = digest.hexdigest()
        result["actual_sha256"] = actual_hash
        result["sha256_matches"] = actual_hash == manifest["sha256"]
        if not result["sha256_matches"]:
            problems.append("L'impronta del PDF non coincide con quella della fonte preparata.")
        # The supplied source has 64 uncompressed page objects. For this fixed,
        # hash-verified PDF a stdlib count is exact; it is not a general parser
        # for arbitrary PDFs with compressed object streams.
        count = None
        if pdf.stat().st_size:
            with pdf.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                if mapped[:5] != b"%PDF-":
                    problems.append("La fonte non comincia con una firma PDF valida.")
                count = sum(1 for _ in re.finditer(rb"/Type\s*/Page\b", mapped))
        result["actual_page_count"] = count
        result["page_count_method"] = "Oggetti /Type /Page non compressi nel PDF fornito"
        if count != manifest["page_count"]:
            problems.append("Il numero delle pagine non coincide con il manifesto, oppure il PDF usa oggetti compressi non supportati da questo controllo.")
    ocr = relative_path(root, manifest["ocr_path"], "source.ocr_path")
    if not result["ocr"]["complete"]:
        problems.append("Indice OCR incompleto; consultare le pagine mancanti nel PDF originale.")
    ocr_manifest = ocr / "manifest.json"
    if not ocr_manifest.is_file():
        problems.append("Manifesto OCR non trovato.")
    else:
        indexed = object_field(read_json(ocr_manifest), "ocr.manifest")
        if indexed.get("sha256") != manifest["sha256"] or indexed.get("pages") != manifest["page_count"]:
            problems.append("L'indice OCR si riferisce a una fonte o a un numero di pagine diverso.")
    invalid_headers = []
    for n in range(1, manifest["page_count"] + 1):
        page = ocr / f"page-{n:03d}.txt"
        if page.is_file():
            with page.open(encoding="utf-8-sig") as stream:
                header = stream.readline()
            if not header.startswith(f"PAGINA PDF {n} / {manifest['page_count']}"):
                invalid_headers.append(n)
    result["ocr"]["invalid_headers"] = invalid_headers
    if invalid_headers:
        problems.append("Alcune pagine OCR non hanno l'intestazione corrispondente.")
    result.update(ok=not problems, problems=problems,
                  notice="L'OCR resta ausiliario: numeri, mappe e regole richiedono riscontro sull'immagine originale.")
    return result


def build_parser():
    parser = JsonParser(description="Strumenti locali riservati al DM: fonte e rivelazione dei luoghi.")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonParser)
    commands.add_parser("info", help="Manifesto della fonte e disponibilità dell'OCR, senza dipendenze PDF.")
    commands.add_parser("verify", help="Verifica SHA-256, pagine e indice OCR della fonte preparata.")
    commands.add_parser("locations", aliases=["list"], help="Catalogo privato del DM: include condizioni e pagine, non inviarlo ai giocatori.")
    reveal = commands.add_parser("reveal", help="Rivela un singolo luogo noto nella fiction, senza spostare il gruppo.")
    reveal.add_argument("location_id")
    reveal.add_argument("--expected-revision", type=int, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        store, table, pack = load_context(root)
        campaign_id = table["state"]["campaign_id"]
        if args.command in ("info", "verify"):
            result = (source_info if args.command == "info" else verify_source)(root, pack)
            result.update(campaign_id=campaign_id, revision=table["state"]["revision"])
        else:
            catalog = load_catalog(pack, campaign_id)
            if args.command in ("locations", "list"):
                result = {"private": True, "campaign_id": campaign_id, "revision": table["state"]["revision"],
                          "notice": catalog.get("notice"), "locations": catalog["locations"]}
            else:
                result = reveal_location(store, table, catalog, args.location_id, args.expected_revision)
        emit(result)
        return 1 if result.get("ok") is False else 0
    except (CampaignError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        emit({"error": str(exc), "code": getattr(exc, "code", "storage_error")}, error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
