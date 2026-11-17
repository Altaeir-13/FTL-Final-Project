"""Export a faithful raster PDF backup from the eight authored slide renders.

The PPTX remains the editable master. This fallback avoids the bundled native
PDF export's missing standard-font module and does not claim selectable text.
"""
import argparse
from pathlib import Path

from reportlab.pdfgen import canvas


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "docs" / "apresentacao" / "aquaclima-ftl.pdf")
    args = parser.parse_args()
    images = [root / "build" / "ftl-presentation" / f"slide-{i:02}.png" for i in range(1, 9)]
    if not all(path.is_file() for path in images):
        raise FileNotFoundError("Render all eight slides with generate_ftl_presentation.mjs first")
    output = args.output
    pdf = canvas.Canvas(str(output), pagesize=(960, 540), pageCompression=1)
    pdf.setTitle("AquaClima - Future Tech Leaders")
    pdf.setAuthor("Randerson Sousa de Sá Nunes")
    pdf.setSubject("Raster presentation backup; editable master supplied as PPTX")
    for image_path in images:
        pdf.drawImage(str(image_path), 0, 0, width=960, height=540)
        pdf.showPage()
    pdf.save()
    print(output)


if __name__ == "__main__":
    main()
