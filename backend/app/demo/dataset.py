"""Synthetic demo dataset. Every institution, person and reference number here is invented."""

REFERENCE_DATE = "2026-10-22"

USERS = [
    {"name": "A. Verma", "email": "scrutiny@verifyai.demo", "role": "SCRUTINY_OFFICER"},
    {"name": "S. Iyer", "email": "verification@verifyai.demo", "role": "VERIFICATION_OFFICER"},
    {"name": "N. Rao", "email": "admin@verifyai.demo", "role": "ADMIN"},
]
DEMO_PASSWORD = "demo1234"

INSTITUTIONS = {
    "ABC": {"aicte_id": "1-2345678901", "name": "ABC Institute of Technology", "state": "Maharashtra",
            "address": "Plot 14, Knowledge Park, Hingna Road, Nagpur, Maharashtra 440016", "established_year": 2008},
    "NEC": {"aicte_id": "1-3456789012", "name": "National Engineering College", "state": "Maharashtra",
            "address": "Survey No. 77, Baner Road, Pune, Maharashtra 411045", "established_year": 1998},
    "MBS": {"aicte_id": "1-4567890123", "name": "Metropolitan Business School", "state": "Maharashtra",
            "address": "12 Harbour View Lane, Andheri East, Mumbai, Maharashtra 400069", "established_year": 2011},
    "STU": {"aicte_id": "1-5678901234", "name": "Sunrise Technical University", "state": "Madhya Pradesh",
            "address": "Sector C, Super Corridor, Indore, Madhya Pradesh 452010", "established_year": 2015},
}

# Mock "AICTE system" records: approvals for 2025-26
APPROVED = {
    "ABC": ("EOA-2025-26-0081-ABC", [("B.Tech Computer Science and Engineering", 180),
                                     ("B.Tech Electronics and Communication Engineering", 120),
                                     ("B.Tech Mechanical Engineering", 60), ("MBA", 60)]),
    "NEC": ("EOA-2025-26-0042-NEC", [("B.Tech Computer Science and Engineering", 120),
                                     ("B.Tech Civil Engineering", 60)]),
    "MBS": ("EOA-2025-26-0107-MBS", [("MBA", 120)]),
    "STU": ("EOA-2025-26-0133-STU", [("B.Tech Computer Science and Engineering", 60)]),
}

PAYMENTS = [
    # (institution, txn_ref, amount, paid_on)
    ("ABC", "TXN-2026-778134", 150000, "2026-10-05"),
    ("NEC", "TXN-2026-771020", 150000, "2026-09-28"),
]

SOURCES = [
    {"key": "STATE_DTE", "name": "State Directorate of Technical Education — NOC Registry (mock)",
     "doc_types": ["NOC"], "method": "Reference-number lookup (API)", "mode": "ONLINE"},
    {"key": "NAB", "name": "National Accreditation Board — Certificate Registry (mock)",
     "doc_types": ["ACCREDITATION"], "method": "Certificate-number lookup", "mode": "ONLINE"},
    {"key": "NOTARY", "name": "District Notary e-Registry (mock)",
     "doc_types": ["AFFIDAVIT"], "method": "Registry cross-check", "mode": "OFFLINE"},
    {"key": "MUNICIPAL", "name": "Municipal Building Permission Portal (mock)",
     "doc_types": ["INFRA_CERT"], "method": "Certificate lookup (asynchronous)", "mode": "ASYNC"},
]

# What the mock issuing authorities hold on record
ISSUER_RECORDS = [
    ("STATE_DTE", "NOC-28492", {"institution_name": "A.B.C. Inst. of Technology", "issue_date": "2026-03-12",
                                "expiry_date": "2026-11-09", "status": "ACTIVE"}),
    ("STATE_DTE", "NOC-27310", {"institution_name": "National Engineering College", "issue_date": "2026-02-01",
                                "expiry_date": "2027-01-31", "status": "ACTIVE"}),
    ("NAB", "NAB-AC-4821", {"institution_name": "ABC Institute of Technology", "issue_date": "2023-07-01",
                            "expiry_date": "2026-06-30", "status": "ACTIVE"}),
    ("NAB", "NAB-AC-5120", {"institution_name": "ABC Institute of Technology", "issue_date": "2026-10-15",
                            "expiry_date": "2029-10-14", "status": "ACTIVE"}),
    ("NAB", "NAB-AC-3307", {"institution_name": "National Engineering College", "issue_date": "2025-07-01",
                            "expiry_date": "2028-06-30", "status": "ACTIVE"}),
    ("NOTARY", "AFF-2026-1192", {"institution_name": "ABC Institute of Technology", "issue_date": "2026-09-15"}),
    ("NOTARY", "AFF-2026-0877", {"institution_name": "National Engineering College", "issue_date": "2026-09-02"}),
    ("NOTARY", "AFF-2026-1310", {"institution_name": "Metropolitan Business School", "issue_date": "2026-09-20"}),
    # Official record shows 4,800 sq.m; the submitted certificate says 5,400 (see the modified-file scenario)
    ("MUNICIPAL", "BCC-NGP-5531", {"institution_name": "ABC Institute of Technology", "issue_date": "2026-03-05",
                                   "built_up_area": "4800"}),
    ("MUNICIPAL", "BCC-PUN-2210", {"institution_name": "National Engineering College", "issue_date": "2025-12-10",
                                   "built_up_area": "7200"}),
    ("MUNICIPAL", "BCC-MUM-1189", {"institution_name": "Metropolitan Business School", "issue_date": "2026-01-18",
                                   "built_up_area": "3100"}),
]

APPLICATIONS = [
    # code, institution, programmes (requested intake), built-up area, demo documents attached at reset?
    {"code": "EoA-2026-4821", "inst": "ABC", "built_up_area_sqm": 5400, "preload": False,
     "programmes": [("B.Tech Computer Science and Engineering", 240),
                    ("B.Tech Electronics and Communication Engineering", 120),
                    ("B.Tech Mechanical Engineering", 60), ("MBA", 60)],
     "submitted_at": "2026-10-20T09:15:00"},
    {"code": "EoA-2026-4820", "inst": "NEC", "built_up_area_sqm": 7200, "preload": True,
     "programmes": [("B.Tech Computer Science and Engineering", 120), ("B.Tech Civil Engineering", 60)],
     "submitted_at": "2026-10-18T11:40:00"},
    {"code": "EoA-2026-4819", "inst": "MBS", "built_up_area_sqm": 3100, "preload": True,
     "programmes": [("MBA", 120)], "submitted_at": "2026-10-17T15:05:00"},
    {"code": "EoA-2026-4818", "inst": "STU", "built_up_area_sqm": 2600, "preload": False,
     "programmes": [("B.Tech Computer Science and Engineering", 60)], "submitted_at": "2026-10-16T10:20:00"},
]
