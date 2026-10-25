"""Read selected pages of a local source PDF for the DM; optional PDF libraries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Leggi una pagina del PDF del master senza esporla nella plancia.")
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--campaign", help="Pack locale, per esempio phandelver. Usa source.json e l'indice OCR privato.")
    parser.add_argument("--page", type=int, default=1, help="Numero della pagina PDF, da 1.")
    parser.add_argument("--count", type=int, default=1, help="Numero di pagine da leggere, massimo 8.")
    parser.add_argument("--render", type=Path, help="Cartella privata in cui rendere anche le pagine PNG, a 150 dpi.")
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.count <= 8:
        parser.error("Pagina positiva e da 1 a 8 pagine per lettura.")
    root = Path(__file__).resolve().parents[1]
    cache = None
    if args.campaign:
        if args.pdf is not None or not args.campaign.replace("-", "").replace("_", "").isalnum():
            parser.error("Usa un percorso PDF oppure --campaign con un ID locale.")
        manifest_path = root / "campaigns" / args.campaign / "source.json"
        if not manifest_path.is_file():
            parser.error("Pack senza source.json.")
        source = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        args.pdf = (root / source["path"]).resolve()
        cache = (root / source["ocr_path"]).resolve() if source.get("ocr_path") else None
        if not args.pdf.is_relative_to(root) or (cache and not cache.is_relative_to(root)):
            parser.error("Il manifesto della fonte deve indicare file della cartella del tavolo.")
    if args.pdf is None or not args.pdf.is_file():
        parser.error("PDF non trovato.")
    # The prepared cache is usable without optional PDF/OCR dependencies at play
    # time. Its manifest identifies the original; it is an aid, not a new edition.
    if cache is not None and not args.render:
        manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8-sig"))
        if manifest.get("sha256") != source.get("sha256"):
            parser.error("L'indice OCR non corrisponde alla fonte del pack.")
        if args.page > manifest["pages"]:
            parser.error(f"Il PDF ha {manifest['pages']} pagine.")
        end = min(args.page - 1 + args.count, manifest["pages"])
        files = [cache / f"page-{i+1:03d}.txt" for i in range(args.page - 1, end)]
        if all(path.is_file() for path in files):
            print("Indice OCR privato: controllare numeri, nomi e cartografia sul PDF originale.\n")
            for path in files:
                print(path.read_text(encoding="utf-8-sig"))
            return 0
    try:
        import pymupdf
        with pymupdf.open(args.pdf) as pdf:
            if args.page > len(pdf):
                parser.error(f"Il PDF ha {len(pdf)} pagine.")
            for index in range(args.page - 1, min(args.page - 1 + args.count, len(pdf))):
                print(f"\n--- Pagina PDF {index + 1} / {len(pdf)} ---\n")
                page = pdf[index]
                native = page.get_text().strip()
                if native:
                    print(native)
                elif cache and (cache / f"page-{index+1:03d}.txt").is_file():
                    print((cache / f"page-{index+1:03d}.txt").read_text(encoding="utf-8-sig"))
                else:
                    print("Pagina scansionata, senza testo estraibile. Consultare il PDF o usare --render CARTELLA.")
                if args.render:
                    args.render.mkdir(parents=True, exist_ok=True)
                    target = args.render / f"page-{index+1:03d}.png"
                    page.get_pixmap(dpi=150).save(target)
                    print(f"Immagine da leggere con view_image: {target.resolve()}")
    except ImportError:
        try:
            from pypdf import PdfReader
            pdf = PdfReader(args.pdf)
            if args.page > len(pdf.pages):
                parser.error(f"Il PDF ha {len(pdf.pages)} pagine.")
            for index in range(args.page - 1, min(args.page - 1 + args.count, len(pdf.pages))):
                print(f"\n--- Pagina PDF {index + 1} / {len(pdf.pages)} ---\n")
                print(pdf.pages[index].extract_text() or "Pagina scansionata: consultare il PDF originale.")
            if args.render:
                print("Per rendere pagine in PNG occorre PyMuPDF.", file=sys.stderr)
                return 2
        except ImportError:
            print("Lettura PDF opzionale: usa un lettore PDF o consulta la fonte online indicata in master/CURRENT.md. Il tavolo di gioco funziona senza librerie PDF.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
