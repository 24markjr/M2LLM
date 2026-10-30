"""The demonstration case: Project VAJRA, a defence procurement with planted irregularities.

Synthetic, every file says so; no real unit, supplier or person. Run once from the repository root
on Windows (the call is spoken by Windows' own synthesiser):

    backend/.venv/Scripts/python .agent/fixtures/make_vajra_fixtures.py

The story. An equipment depot orders 40 thermal imaging sights at INR 10,50,000 each
(INR 4,20,00,000), to be delivered by 15 March 2026; payment only after joint inspection, and only
for the units accepted. What the files show:

- `vajra_supply_order.pdf`: 40 units, INR 4,20,00,000, delivery by 15 March 2026, payment after
  joint inspection for accepted units only, liquidated damages for delay.
- `vajra_invoice_scan.png` (a scan, read by OCR): bills all 40 units, the full INR 4,20,00,000,
  and states delivery on 14 March 2026.
- `vajra_inspection_report.docx`: units received 28 March 2026; 36 accepted, 4 rejected.
- `vajra_payment_ledger.xlsx`: INR 4,20,00,000 released on 25 March 2026, before the inspection
  of 2 April 2026, against the invoice.
- `vajra_committee_minutes_hi.txt` (Hindi): payment approved for 36 units only, INR 3,78,00,000;
  delivery 28 March, 13 days late; no payment before inspection.
- `vajra_supplier_call.wav` (speech): the supplier says the units will reach the depot on
  28 March 2026.

Planted findings: paid for 40 but 36 accepted (INR 42,00,000 overpaid); paid before inspection;
the invoice's delivery date (14 March) contradicts the inspection, the minutes and the call
(28 March); delivery late against the order. The clean twin (`vajra2_*`): 20 units ordered,
delivered on time, all accepted, paid after inspection for exactly the amount - nothing to find.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent / "documents"
SYNTHETIC = "SYNTHETIC DEMONSTRATION DATA - no real unit, supplier or person."


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def supply_order() -> None:
    lines = [
        ("SUPPLY ORDER No. VJR/SO/2026/014", 15),
        ("Date: 10 January 2026", 11),
        ("Buyer: Procurement Cell, Equipment Depot Alpha", 11),
        ("Supplier: Trinetra Optronics Pvt Ltd", 11),
        ("", 11),
        ("1. Item: Thermal Imaging Sight, model TIS-450", 11),
        ("2. Quantity: 40 units", 11),
        ("3. Unit price: INR 10,50,000", 11),
        ("4. Total order value: INR 4,20,00,000", 11),
        ("5. Delivery: all 40 units to be delivered to the depot by 15 March 2026.", 11),
        ("6. Inspection: a joint inspection board will inspect every unit on receipt.", 11),
        ("7. Payment: only after the joint inspection report, and only for units accepted.", 11),
        ("8. Liquidated damages: 0.5% of the order value per week of delay.", 11),
        ("", 11),
        ("Approved by: Purchase Committee, Equipment Depot Alpha", 11),
        ("", 11),
        (SYNTHETIC, 8),
    ]
    pdf = canvas.Canvas(str(OUT / "vajra_supply_order.pdf"), pagesize=A4)
    y = 800
    for text, size in lines:
        pdf.setFont("Helvetica-Bold" if size > 12 else "Helvetica", size)
        pdf.drawString(60, y, text)
        y -= size + 10
    pdf.save()


def invoice_scan() -> None:
    lines = [
        "TAX INVOICE  TOI/2026/088",
        "Trinetra Optronics Pvt Ltd",
        "Bill to: Equipment Depot Alpha",
        "Invoice date: 20 March 2026",
        "Against supply order VJR/SO/2026/014",
        "Thermal Imaging Sight TIS-450 x 40",
        "Unit price: INR 10,50,000",
        "Amount payable: INR 4,20,00,000",
        "Goods delivered on 14 March 2026",
        "SYNTHETIC DEMONSTRATION DATA",
    ]
    image = Image.new("RGB", (1100, 820), "white")
    draw = ImageDraw.Draw(image)
    y = 40
    for i, line in enumerate(lines):
        size = 36 if i == 0 else 30
        draw.text((50, y), line, fill="black", font=font(size))
        y += size + 30
    # A scan: slightly rotated, softened, grey speckle.
    image = image.rotate(0.8, expand=True, fillcolor="white").filter(ImageFilter.GaussianBlur(0.5))
    rng = random.Random(11)
    speckle = ImageDraw.Draw(image)
    for _ in range(1500):
        x, y = rng.randrange(image.width), rng.randrange(image.height)
        speckle.point((x, y), fill=(rng.randrange(160, 220),) * 3)
    image.save(OUT / "vajra_invoice_scan.png")


def inspection_report() -> None:
    doc = Document()
    doc.add_heading("Joint Inspection Report JIR/VJR/2026/03", level=1)
    doc.add_paragraph("Supply order: VJR/SO/2026/014 (Thermal Imaging Sight TIS-450).")
    doc.add_paragraph("Date of report: 2 April 2026.")
    doc.add_paragraph("Units received at the depot: 40, on 28 March 2026.")
    doc.add_paragraph("Units accepted: 36.")
    doc.add_paragraph(
        "Units rejected: 4 (serial numbers TIS-0417, TIS-0422, TIS-0431, TIS-0438): "
        "detector failed the thermal sensitivity test."
    )
    doc.add_paragraph("The board recommends payment for the 36 accepted units only.")
    doc.add_paragraph("Board: Maj. A. Verma (presiding), Capt. S. Nair, Sub. R. Yadav.")
    doc.add_paragraph(SYNTHETIC)
    doc.save(str(OUT / "vajra_inspection_report.docx"))


def payment_ledger() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Payments FY2025-26"
    for row in [
        ("Voucher", "Date", "Payee", "Reference", "Amount (INR)", "Inspection report"),
        ("PV-2026-0311", "18 February 2026", "Sigma Stores", "SO/2026/009", 240000, "JIR/2026/01"),
        (
            "PV-2026-0356",
            "25 March 2026",
            "Trinetra Optronics Pvt Ltd",
            "Invoice TOI/2026/088",
            420000000,
            "pending",
        ),
        ("Note", SYNTHETIC, "", "", "", ""),
    ]:
        sheet.append(row)
    book.save(str(OUT / "vajra_payment_ledger.xlsx"))


def committee_minutes() -> None:
    text = "\n".join(
        [
            "परियोजना वज्र - क्रय समिति की बैठक का कार्यवृत्त",
            "दिनांक: 5 अप्रैल 2026",
            "स्थान: क्रय प्रकोष्ठ, उपकरण डिपो अल्फा",
            "",
            "1. संयुक्त निरीक्षण रिपोर्ट के अनुसार 40 में से केवल 36 थर्मल इमेजिंग साइट स्वीकार की गईं और 4 अस्वीकार की गईं।",
            "2. आपूर्तिकर्ता ने सभी इकाइयाँ 28 मार्च 2026 को वितरित कीं, जो निर्धारित तिथि 15 मार्च 2026 से 13 दिन देर है।",
            "3. समिति ने निर्णय लिया कि भुगतान केवल 36 स्वीकृत इकाइयों के लिए ₹3,78,00,000 किया जाएगा।",
            "4. आपूर्ति आदेश के अनुसार देरी के लिए परिनिर्धारित क्षतिपूर्ति लगाई जाएगी।",
            "5. निरीक्षण रिपोर्ट से पहले कोई भुगतान नहीं किया जाना चाहिए।",
            "",
            "SYNTHETIC DEMONSTRATION DATA",
        ]
    )
    (OUT / "vajra_committee_minutes_hi.txt").write_text(text + "\n", encoding="utf-8")


def supplier_call() -> None:
    speech = (
        "Hello, this is Ravi from Trinetra Optronics, calling about supply order fourteen. "
        "The thermal sights could not ship on time. All forty units will reach the depot on the "
        "twenty eighth of March twenty twenty six. Please do not mention the delay on the invoice."
    )
    path = OUT / "vajra_supplier_call.wav"
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{speech}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)  # noqa: S603, S607


def clean_twin() -> None:
    """Batch 2: everything agrees. The right answer is that there is nothing wrong."""
    (OUT / "vajra2_supply_order.txt").write_text(
        "\n".join(
            [
                "SUPPLY ORDER No. VJR/SO/2026/021",
                "Date: 2 February 2026",
                "Supplier: Trinetra Optronics Pvt Ltd",
                "Item: Thermal Imaging Sight TIS-450",
                "Quantity: 20 units at INR 10,50,000 each",
                "Total order value: INR 2,10,00,000",
                "Delivery: by 30 April 2026",
                "Payment: after joint inspection, for accepted units only",
                SYNTHETIC,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "vajra2_inspection_report.txt").write_text(
        "\n".join(
            [
                "Joint Inspection Report JIR/VJR/2026/05",
                "Supply order: VJR/SO/2026/021",
                "Date of report: 24 April 2026",
                "Units received: 20, on 22 April 2026",
                "Units accepted: 20. Units rejected: none.",
                "The board recommends payment of INR 2,10,00,000 for the 20 accepted units.",
                SYNTHETIC,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "vajra2_payment_ledger.csv").write_text(
        "Voucher,Date,Payee,Reference,Amount (INR),Inspection report\n"
        'PV-2026-0402,29 April 2026,Trinetra Optronics Pvt Ltd,SO/2026/021,"2,10,00,000",'
        "JIR/VJR/2026/05\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    supply_order()
    invoice_scan()
    inspection_report()
    payment_ledger()
    committee_minutes()
    supplier_call()
    clean_twin()
    print("written to", OUT)  # noqa: T201
