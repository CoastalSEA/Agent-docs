r"""OCR the first pages of linked PDFs that have no text layer, for lookup.py. Writes nothing to the library.

Created using: $\text {Created using: }\ claude-opus-5-5-\text{v}5.5-\text {date: }211126$

Usage: ocr_pdf.py --lib <library .enl> --ids 12,15 --out <folder> --tesseract <path to tesseract> [--pages 4]
                  [--root <project root>]
       ocr_pdf.py --version
Run it with the interpreter of the OCR environment named in machine.md (it needs pymupdf and pytesseract).
Inputs:  the library (read only) and the first linked PDF of each entry.
Outputs: <out>/ocr/ref<id>.txt per entry (the OCR text of the first pages), which lookup.py reads when the text
         layer is short. The PDFs are opened for reading only.
Exit:    0 on success; 2 for unusable input or missing packages.
Version: see VERSION.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import libmeta as lm  # noqa: E402

VERSION = "1.0"


def main(argv):
    ap = argparse.ArgumentParser(prog="ocr_pdf.py")
    ap.add_argument("--version", action="version", version=f"ocr_pdf.py {VERSION}")
    ap.add_argument("--root", default=".")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tesseract", required=True)
    ap.add_argument("--pages", type=int, default=4)
    a = ap.parse_args(argv)
    try:
        import io
        import pymupdf
        import pytesseract
        from PIL import Image
    except ImportError as e:
        print(f"Missing package ({e}): run this script with the OCR environment named in machine.md", file=sys.stderr)
        return 2
    pytesseract.pytesseract.tesseract_cmd = a.tesseract
    root = Path(a.root).resolve()
    lib = Path(a.lib) if Path(a.lib).is_absolute() else root / a.lib
    out = (Path(a.out) if Path(a.out).is_absolute() else root / a.out) / "ocr"
    el = lm.load_helper()
    _, data, _ = el.paths(lib)
    refs = {r["id"]: r for r in el.read_refs(lib)}
    out.mkdir(parents=True, exist_ok=True)
    for rid in (int(x) for x in a.ids.split(",") if x.strip()):
        ref = refs.get(rid)
        if not ref or not ref["files"]:
            print(rid, "no active entry with a linked PDF")
            continue
        d = pymupdf.open(data / "PDF" / ref["files"][0])
        try:
            parts = []
            for i in range(min(a.pages, len(d))):
                pix = d[i].get_pixmap(dpi=300)
                parts.append(pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), lang="eng"))
        finally:
            d.close()
        (out / f"ref{rid}.txt").write_text("\n".join(parts), encoding="utf-8")
        print(rid, "OCR text:", sum(len(p) for p in parts), "characters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
