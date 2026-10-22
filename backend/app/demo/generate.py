"""Generate the synthetic demo documents (PDFs, a scanned PDF and photos) plus ground truth.

Seeded test scenarios for EoA-2026-4821 (ABC Institute of Technology):
  1. accreditation.pdf expired 30 Jun 2026                         → EOA-EXP-001
  2. noc.pdf expires 09 Nov 2026 (18 days after reference date)     → EOA-EXP-002
  3. noc.pdf names "A.B.C. Inst. of Technology"                     → EOA-CON-001
  4. requested CSE intake 240 vs approved 180                       → EOA-INT-001
  5. fee receipt TXN reused by EoA-2026-4819                        → EOA-ANM-002
  6. NOC verifies against the state registry                        → VERIFIED
  7. notary registry offline for the affidavit                      → SOURCE_UNAVAILABLE
  8. infrastructure certificate edited 7 months after creation      → EOA-ANM-004
     (and the municipal record shows a different built-up area      → MISMATCH on refresh)
  9. no floor plan submitted                                        → EOA-INF-001
"""
import io
import json
import random
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .dataset import APPROVED, INSTITUTIONS

FOOTER = "SYNTHETIC DOCUMENT - GENERATED FOR THE SIH26261 DEMONSTRATION. NOT A REAL RECORD."
W, H = A4


class Doc:
    """Tiny layout helper on top of a reportlab canvas."""

    def __init__(self, issuer: str, title: str):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.issuer, self.title = issuer, title
        self._header()

    def _header(self):
        c = self.c
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(W / 2, H - 60, self.issuer)
        c.setLineWidth(0.6)
        c.line(60, H - 72, W - 60, H - 72)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(W / 2, H - 105, self.title)
        self.y = H - 145
        c.setFont("Helvetica", 7)
        c.drawCentredString(W / 2, 30, FOOTER)

    def field(self, label: str, value: str):
        self.c.setFont("Helvetica", 11)
        self.c.drawString(70, self.y, f"{label}: {value}")
        self.y -= 22

    def para(self, text: str, size: int = 11):
        self.c.setFont("Helvetica", size)
        words, line = text.split(), ""
        for w in words:
            trial = f"{line} {w}".strip()
            if self.c.stringWidth(trial, "Helvetica", size) > W - 140:
                self.c.drawString(70, self.y, line)
                self.y -= size + 6
                line = w
            else:
                line = trial
        if line:
            self.c.drawString(70, self.y, line)
            self.y -= size + 6
        self.y -= 8

    def table(self, header: tuple[str, str], rows: list[tuple[str, int]]):
        c = self.c
        c.setFont("Helvetica-Bold", 11)
        c.drawString(70, self.y, "S.No.")
        c.drawString(115, self.y, header[0])
        c.drawRightString(W - 80, self.y, header[1])
        self.y -= 6
        c.line(65, self.y, W - 65, self.y)
        self.y -= 18
        c.setFont("Helvetica", 11)
        for i, (prog, intake) in enumerate(rows, 1):
            c.drawString(70, self.y, f"{i}.")
            c.drawString(115, self.y, prog)
            c.drawRightString(W - 80, self.y, str(intake))
            self.y -= 22
        self.y -= 10

    def signature(self, name: str, role: str):
        self.y -= 20
        self.c.setFont("Helvetica", 11)
        self.c.drawString(W - 250, self.y, name)
        self.c.drawString(W - 250, self.y - 16, role)
        self.y -= 50

    def new_page(self):
        self.c.showPage()
        self._header()

    def save(self) -> bytes:
        self.c.save()
        return self.buf.getvalue()


def _set_meta(pdf: bytes, created: str, modified: str, producer: str = "VerifyAI synthetic generator",
              creator: str = "VerifyAI synthetic generator") -> bytes:
    doc = fitz.open(stream=pdf, filetype="pdf")
    doc.set_metadata({"creationDate": created, "modDate": modified, "producer": producer, "creator": creator,
                      "title": "Synthetic demo document"})
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def _pdfdate(iso: str) -> str:
    return "D:" + iso.replace("-", "") + "103000+05'30'"


def _finish(pdf: bytes, issue_iso: str) -> bytes:
    return _set_meta(pdf, _pdfdate(issue_iso), _pdfdate(issue_iso))


def affidavit(inst: dict, ref: str, issue: str, issue_iso: str) -> bytes:
    d = Doc("OFFICE OF THE NOTARY PUBLIC, DISTRICT COURT", "AFFIDAVIT")
    d.field("Reference No.", ref)
    d.field("Name of Institution", inst["name"])
    d.field("AICTE Permanent ID", inst["aicte_id"])
    d.field("Date of Issue", issue)
    d.para(f"I, the undersigned deponent, being the authorised signatory of {inst['name']}, do hereby solemnly "
           f"affirm that the information furnished in the application for the academic year 2026-27 is true and "
           f"correct to the best of my knowledge, and that no material fact has been concealed.")
    d.para("I further affirm that the institution is not running any programme without approval and that all "
           "statutory norms applicable to the institution are being followed.")
    d.signature("Authorised Signatory", "Deponent")
    d.signature("Notary Public", "Registration No. NP/4471")
    return _finish(d.save(), issue_iso)


def scanned(pdf: bytes, seed: int = 7) -> bytes:
    """Turn a text PDF into an image-only 'scan' (slight blur, noise and tilt) so OCR is required."""
    rnd = random.Random(seed)
    src = fitz.open(stream=pdf, filetype="pdf")
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        img = img.rotate(0.35, resample=Image.BICUBIC, expand=False, fillcolor=255)
        px = img.load()
        for _ in range(img.width * img.height // 400):
            x, y = rnd.randrange(img.width), rnd.randrange(img.height)
            px[x, y] = rnd.choice((150, 190, 215))
        img = img.filter(ImageFilter.GaussianBlur(0.4))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=buf.getvalue())
    data = out.tobytes(garbage=3, deflate=True)
    src.close()
    out.close()
    return data


def undertaking(inst: dict, ref: str, issue: str, issue_iso: str) -> bytes:
    d = Doc(inst["name"].upper(), "UNDERTAKING")
    d.field("Reference No.", ref)
    d.field("Name of Institution", inst["name"])
    d.field("AICTE Permanent ID", inst["aicte_id"])
    d.field("Date of Issue", issue)
    d.para("We hereby undertake to comply with all norms, standards and conditions prescribed by the Council for "
           "the academic year 2026-27, and to rectify any deficiency pointed out during scrutiny within the time "
           "allowed.")
    d.signature("Principal / Director", inst["name"])
    return _finish(d.save(), issue_iso)


def noc(name_on_doc: str, inst: dict, ref: str, issue: str, valid: str, issue_iso: str) -> bytes:
    d = Doc("STATE DIRECTORATE OF TECHNICAL EDUCATION (DEMO STATE)", "NO OBJECTION CERTIFICATE")
    d.field("Reference No.", ref)
    d.field("Name of Institution", name_on_doc)
    d.field("Date of Issue", issue)
    d.field("Valid Until", valid)
    d.field("Issued by", "Joint Director, State Directorate of Technical Education")
    d.para(f"The State Government has no objection to the continuation of the approved programmes at the "
           f"institution named above, located at {inst['address']}, for the academic year 2026-27, subject to "
           f"the conditions laid down by the Council.")
    d.signature("Joint Director", "State Directorate of Technical Education")
    return _finish(d.save(), issue_iso)


def accreditation(inst: dict, ref: str, frm: str, until: str, issue_iso: str) -> bytes:
    d = Doc("NATIONAL ACCREDITATION BOARD (DEMO)", "CERTIFICATE OF ACCREDITATION")
    d.field("Certificate No.", ref)
    d.field("Name of Institution", inst["name"])
    d.field("Valid From", frm)
    d.field("Valid Until", until)
    d.para("This is to certify that the programmes listed in the annexure to this certificate have been "
           "accredited by the Board after evaluation by an expert committee.")
    d.signature("Member Secretary", "National Accreditation Board (Demo)")
    return _finish(d.save(), issue_iso)


def previous_eoa(inst: dict, ref: str, programmes: list[tuple[str, int]], issue: str, issue_iso: str) -> bytes:
    d = Doc("ALL INDIA COUNCIL FOR TECHNICAL EDUCATION (SYNTHETIC RECORD)", "EXTENSION OF APPROVAL")
    d.field("Approval Reference", ref)
    d.field("Name of Institution", inst["name"])
    d.field("AICTE Permanent ID", inst["aicte_id"])
    d.field("Academic Year", "2025-26")
    d.field("Date of Issue", issue)
    d.para("This letter of approval conveys the Extension of Approval to the institution named above for the "
           "academic year 2025-26 for the programmes and approved intake listed on the following page, subject "
           "to the conditions of the Approval Process Handbook.")
    d.signature("Member Secretary", "Approval Bureau")
    d.new_page()
    d.para("Annexure: programme-wise approved intake for the academic year 2025-26.")
    d.table(("Programme", "Approved Intake"), programmes)
    return _finish(d.save(), issue_iso)


def programme_details(inst: dict, programmes: list[tuple[str, int]], issue_iso: str) -> bytes:
    d = Doc(inst["name"].upper(), "PROGRAMME DETAILS")
    d.field("Name of Institution", inst["name"])
    d.field("AICTE Permanent ID", inst["aicte_id"])
    d.field("Academic Year", "2026-27")
    d.para("Programme details with the proposed intake for the academic year 2026-27 are given below.")
    d.table(("Programme", "Proposed Intake"), programmes)
    d.signature("Principal / Director", inst["name"])
    return _finish(d.save(), issue_iso)


def fee_receipt(inst_name: str, txn: str, amount: str, paid: str, issue_iso: str) -> bytes:
    d = Doc("COUNCIL PAYMENT GATEWAY (SYNTHETIC)", "PAYMENT RECEIPT")
    d.field("Transaction Reference", txn)
    d.field("Name of Institution", inst_name)
    d.field("Date of Payment", paid)
    d.field("Amount Paid", f"Rs. {amount}")
    d.field("Purpose", "Processing fee, academic year 2026-27")
    d.para("This is a computer-generated receipt and does not require a signature.")
    return _finish(d.save(), issue_iso)


def infra_cert(inst: dict, ref: str, area: str, issue: str, issue_iso: str, modified_iso: str | None = None) -> bytes:
    d = Doc("MUNICIPAL BUILDING PERMISSION AUTHORITY (DEMO)", "BUILDING COMPLETION AND STRUCTURAL STABILITY")
    d.field("Certificate No.", ref)
    d.field("Name of Institution", inst["name"])
    d.field("Built-up Area", f"{area} sq.m")
    d.field("Date of Issue", issue)
    d.para(f"Certified that the academic buildings at {inst['address']} have been completed as per the sanctioned "
           f"plan and are structurally stable for the intended educational use.")
    d.signature("Executive Engineer", "Building Permission Authority")
    pdf = d.save()
    if modified_iso:
        return _set_meta(pdf, _pdfdate(issue_iso), _pdfdate(modified_iso), producer="QuickEdit PDF Editor 4.2",
                         creator="QuickEdit PDF Editor")
    return _finish(pdf, issue_iso)


def floor_plan(inst: dict, issue_iso: str) -> bytes:
    d = Doc(inst["name"].upper(), "FLOOR PLAN - ACADEMIC BLOCK")
    d.field("Name of Institution", inst["name"])
    d.para("Ground floor layout plan of the academic block showing classrooms, laboratories and the library.")
    c = d.c
    c.rect(90, 250, W - 180, 300)
    for i, label in enumerate(["Classroom 1", "Classroom 2", "Computer Lab", "Library"]):
        x = 90 + i * (W - 180) / 4
        c.rect(x, 250, (W - 180) / 4, 300)
        c.setFont("Helvetica", 9)
        c.drawCentredString(x + (W - 180) / 8, 400, label)
    return _finish(d.save(), issue_iso)


def photo(caption: str, seed: int) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", (1200, 800), (196, 214, 229))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 560, 1200, 800], fill=(140, 160, 120))
    x = 120
    for _ in range(3):
        w, h = rnd.randint(220, 320), rnd.randint(260, 400)
        dr.rectangle([x, 560 - h, x + w, 560], fill=(205, 190, 165), outline=(120, 100, 80), width=3)
        for wx in range(x + 20, x + w - 30, 45):
            for wy in range(560 - h + 25, 540, 55):
                dr.rectangle([wx, wy, wx + 25, wy + 30], fill=(90, 110, 130))
        x += w + 60
    dr.rectangle([0, 740, 1200, 800], fill=(30, 30, 30))
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:
        font = ImageFont.load_default()
    dr.text((24, 755), caption, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def build(out_dir: Path) -> dict:
    """Write every demo application's documents + manifest.json (ground truth). Returns the manifests."""
    abc, nec, mbs = INSTITUTIONS["ABC"], INSTITUTIONS["NEC"], INSTITUTIONS["MBS"]
    sets: dict[str, list[tuple[str, bytes, str, dict]]] = {}

    abc_prog = [("B.Tech Computer Science and Engineering", 240),
                ("B.Tech Electronics and Communication Engineering", 120),
                ("B.Tech Mechanical Engineering", 60), ("MBA", 60)]
    sets["EoA-2026-4821"] = [
        ("affidavit_scanned.pdf", scanned(affidavit(abc, "AFF-2026-1192", "15 September 2026", "2026-09-15")),
         "AFFIDAVIT", {"reference_number": "AFF20261192", "issue_date": "2026-09-15",
                       "aicte_id": "12345678901"}),
        ("undertaking.pdf", undertaking(abc, "UND-2026-0417", "16 September 2026", "2026-09-16"), "UNDERTAKING",
         {"reference_number": "UND20260417", "issue_date": "2026-09-16"}),
        ("noc.pdf", noc("A.B.C. Inst. of Technology", abc, "NOC-28492", "12 March 2026", "09 November 2026",
                        "2026-03-12"), "NOC",
         {"reference_number": "NOC28492", "issue_date": "2026-03-12", "expiry_date": "2026-11-09"}),
        ("accreditation.pdf", accreditation(abc, "NAB-AC-4821", "01 July 2023", "30 June 2026", "2023-07-01"),
         "ACCREDITATION", {"reference_number": "NABAC4821", "valid_from": "2023-07-01", "expiry_date": "2026-06-30"}),
        ("previous_eoa.pdf", previous_eoa(abc, APPROVED["ABC"][0], APPROVED["ABC"][1], "18 November 2025",
                                          "2025-11-18"), "PREVIOUS_EOA",
         {"reference_number": "EOA2025260081ABC", "issue_date": "2025-11-18",
          "intake:btech computer science and engineering": "180"}),
        ("programme_details.pdf", programme_details(abc, abc_prog, "2026-10-01"), "PROGRAMME_DETAILS",
         {"intake:btech computer science and engineering": "240", "intake:mba": "60"}),
        ("fee_receipt.pdf", fee_receipt(abc["name"], "TXN-2026-778134", "1,50,000", "05 October 2026", "2026-10-05"),
         "FEE_RECEIPT", {"reference_number": "TXN2026778134", "amount": "150000", "issue_date": "2026-10-05"}),
        ("infrastructure_certificate.pdf",
         infra_cert(abc, "BCC-NGP-5531", "5,400", "05 March 2026", "2026-03-05", modified_iso="2026-10-02"),
         "INFRA_CERT", {"reference_number": "BCCNGP5531", "built_up_area": "5400", "issue_date": "2026-03-05"}),
        ("campus_photo_1.jpg", photo("Main academic block - ABC Institute of Technology", 1), "INFRA_PHOTOS", {}),
        ("lab_photo_2.jpg", photo("Computer laboratory block - ABC Institute of Technology", 2), "INFRA_PHOTOS", {}),
    ]
    # Documents for the rectification part of the demo (upload / replace later)
    sets["EoA-2026-4821-rectification"] = [
        ("floor_plan.pdf", floor_plan(abc, "2026-10-21"), "FLOOR_PLAN", {}),
        ("accreditation_renewed.pdf", accreditation(abc, "NAB-AC-5120", "15 October 2026", "14 October 2029",
                                                    "2026-10-15"), "ACCREDITATION",
         {"reference_number": "NABAC5120", "expiry_date": "2029-10-14"}),
    ]
    sets["EoA-2026-4820"] = [
        ("affidavit.pdf", affidavit(nec, "AFF-2026-0877", "02 September 2026", "2026-09-02"), "AFFIDAVIT", {}),
        ("undertaking.pdf", undertaking(nec, "UND-2026-0391", "02 September 2026", "2026-09-02"), "UNDERTAKING", {}),
        ("noc.pdf", noc(nec["name"], nec, "NOC-27310", "01 February 2026", "31 January 2027", "2026-02-01"), "NOC", {}),
        ("accreditation.pdf", accreditation(nec, "NAB-AC-3307", "01 July 2025", "30 June 2028", "2025-07-01"),
         "ACCREDITATION", {}),
        ("previous_eoa.pdf", previous_eoa(nec, APPROVED["NEC"][0], APPROVED["NEC"][1], "11 November 2025",
                                          "2025-11-11"), "PREVIOUS_EOA", {}),
        ("programme_details.pdf", programme_details(nec, APPROVED["NEC"][1], "2026-09-05"), "PROGRAMME_DETAILS", {}),
        ("fee_receipt.pdf", fee_receipt(nec["name"], "TXN-2026-771020", "1,50,000", "28 September 2026", "2026-09-28"),
         "FEE_RECEIPT", {}),
        ("infrastructure_certificate.pdf", infra_cert(nec, "BCC-PUN-2210", "7,200", "10 December 2025", "2025-12-10"),
         "INFRA_CERT", {}),
        ("floor_plan.pdf", floor_plan(nec, "2026-09-05"), "FLOOR_PLAN", {}),
        ("campus_photo.jpg", photo("Main building - National Engineering College", 3), "INFRA_PHOTOS", {}),
        ("workshop_photo.jpg", photo("Workshop - National Engineering College", 4), "INFRA_PHOTOS", {}),
    ]
    sets["EoA-2026-4819"] = [
        ("affidavit.pdf", affidavit(mbs, "AFF-2026-1310", "20 September 2026", "2026-09-20"), "AFFIDAVIT", {}),
        ("undertaking.pdf", undertaking(mbs, "UND-2026-0502", "20 September 2026", "2026-09-20"), "UNDERTAKING", {}),
        ("previous_eoa.pdf", previous_eoa(mbs, APPROVED["MBS"][0], APPROVED["MBS"][1], "20 November 2025",
                                          "2025-11-20"), "PREVIOUS_EOA", {}),
        ("programme_details.pdf", programme_details(mbs, [("MBA", 120)], "2026-09-22"), "PROGRAMME_DETAILS", {}),
        # Reuses ABC's transaction reference — cross-application duplicate scenario
        ("fee_receipt.pdf", fee_receipt(mbs["name"], "TXN-2026-778134", "1,50,000", "06 October 2026", "2026-10-06"),
         "FEE_RECEIPT", {}),
        ("infrastructure_certificate.pdf", infra_cert(mbs, "BCC-MUM-1189", "3,100", "18 January 2026", "2026-01-18"),
         "INFRA_CERT", {}),
        ("floor_plan.pdf", floor_plan(mbs, "2026-09-22"), "FLOOR_PLAN", {}),
        ("campus_photo.jpg", photo("Campus - Metropolitan Business School", 5), "INFRA_PHOTOS", {}),
        ("classroom_photo.jpg", photo("Classroom - Metropolitan Business School", 6), "INFRA_PHOTOS", {}),
    ]

    manifests = {}
    for code, files in sets.items():
        folder = out_dir / code
        folder.mkdir(parents=True, exist_ok=True)
        manifest = []
        for name, data, dtype, truth in files:
            (folder / name).write_bytes(data)
            manifest.append({"filename": name, "declared_type": dtype, "expected_type": dtype,
                             "expected_fields": truth})
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
        manifests[code] = manifest
    return manifests
