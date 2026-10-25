"""Optional, offline OCR index of a scanned campaign PDF. Never served to players."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--count", type=int)
    args = parser.parse_args()
    import pymupdf
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    pdf_path = args.pdf.resolve()
    doc = pymupdf.open(pdf_path)
    if args.page < 1 or args.page > len(doc) or (args.count is not None and args.count < 1):
        parser.error("Intervallo di pagine non valido.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": str(pdf_path), "sha256": sha256(pdf_path.read_bytes()).hexdigest(),
        "pages": len(doc), "method": "RapidOCR ONNX, two columns, rendered 160 dpi",
        "notice": "OCR ausiliario: può contenere errori. Verificare numeri e mappe sul PDF originale.",
        "toc": doc.get_toc(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                   det_limit_side_len=1200, max_side_len=2600, use_cls=False)
    stop = min(len(doc), args.page - 1 + args.count) if args.count else len(doc)
    for index in range(args.page - 1, stop):
        target = output / f"page-{index+1:03d}.txt"
        if target.exists():
            print(f"SKIP {index+1}", flush=True)
            continue
        started = time.monotonic()
        page = doc[index]
        native = page.get_text().strip()
        if native:
            text = native
        else:
            pix = page.get_pixmap(dpi=160, colorspace=pymupdf.csRGB, alpha=False)
            pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            columns = []
            for left, right in ((0, pix.width // 2), (pix.width // 2, pix.width)):
                result, _ = ocr(pixels[:, left:right].copy())
                lines = [str(row[1]) for row in (result or [])]
                columns.append("\n".join(lines))
            text = "\n\n[COLONNA DESTRA]\n\n".join(columns)
        target.write_text(f"PAGINA PDF {index+1} / {len(doc)} — OCR DA VERIFICARE\n\n{text}\n", encoding="utf-8")
        print(f"PAGE {index+1}: {len(text)} chars, {time.monotonic()-started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
