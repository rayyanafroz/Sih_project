"""End-to-end officer journey against the API, in order. Tests share state via STATE."""
import json
import re
from collections import Counter

API = "/api/v1"
STATE: dict = {}

EXPECTED_FINDINGS = Counter({
    ("EOA-EXP-001", "CRITICAL"): 1,   # accreditation expired
    ("EOA-EXP-002", "WARNING"): 1,    # NOC expires in 18 days
    ("EOA-CON-001", "WARNING"): 1,    # NOC institution name variation
    ("EOA-INT-001", "CRITICAL"): 1,   # CSE intake 240 vs approved 180
    ("EOA-ANM-002", "WARNING"): 1,    # fee receipt txn reused by EoA-2026-4819
    ("EOA-ANM-004", "WARNING"): 1,    # infra certificate modified after issue
    ("EOA-INF-001", "WARNING"): 1,    # floor plan missing
    ("EOA-VER-001", "WARNING"): 2,    # affidavit source unavailable, accreditation expired at source
    ("EOA-VER-001", "INFO"): 1,       # infra certificate verification pending
})


def _app(client, headers, code="EoA-2026-4821"):
    apps = client.get(f"{API}/applications", headers=headers).json()
    return next(a for a in apps if a["code"] == code)


def _open_findings(client, headers, app_id):
    return [f for f in client.get(f"{API}/applications/{app_id}/findings", headers=headers).json()
            if f["status"] != "AUTO_CLEARED"]


def _run(client, headers, app_id):
    r = client.post(f"{API}/applications/{app_id}/prescrutiny", headers=headers)
    assert r.status_code == 200, r.text
    run = client.get(f"{API}/applications/{app_id}/runs", headers=headers).json()[0]
    assert run["status"] == "COMPLETED", run
    return run


def test_login_and_rbac(client, scrutiny, verifier, admin):
    assert client.post(f"{API}/auth/login", json={"email": "scrutiny@verifyai.demo", "password": "x"}).status_code == 401
    assert client.get(f"{API}/dashboard").status_code == 401
    me = client.get(f"{API}/auth/me", headers=scrutiny).json()
    assert me["role"] == "SCRUTINY_OFFICER" and "prescrutiny:run" in me["permissions"]
    app = _app(client, scrutiny)
    STATE["app_id"] = app["id"]
    assert app["status"] == "DRAFT"
    # Only scrutiny officers upload / run; only admins edit rules
    files = {"files": ("noc.pdf", b"%PDF-1.4 test", "application/pdf")}
    assert client.post(f"{API}/applications/{app['id']}/documents", headers=verifier, files=files).status_code == 403
    assert client.post(f"{API}/applications/{app['id']}/prescrutiny", headers=admin).status_code == 403
    assert client.put(f"{API}/rules/EOA-EXP-002", headers=scrutiny,
                      json={"enabled": False, "change_note": "x" * 5}).status_code == 403


def test_upload_validation(client, scrutiny):
    app_id = STATE["app_id"]
    r = client.post(f"{API}/applications/{app_id}/documents", headers=scrutiny,
                    files={"files": ("virus.exe", b"MZ....", "application/octet-stream")})
    assert r.status_code == 400 and "not allowed" in r.json()["detail"]
    r = client.post(f"{API}/applications/{app_id}/documents", headers=scrutiny,
                    files={"files": ("fake.pdf", b"hello world", "application/pdf")})
    assert r.status_code == 400 and "does not match" in r.json()["detail"]


def test_upload_documents(client, scrutiny, demo_dir):
    app_id = STATE["app_id"]
    folder = demo_dir / "EoA-2026-4821"
    manifest = json.loads((folder / "manifest.json").read_text())
    STATE["manifest"] = manifest
    for item in manifest:
        # Upload without declared types for half the files to exercise auto-detection
        data = {"declared_types": item["declared_type"]} if item["declared_type"] in ("INFRA_PHOTOS", "NOC") else {}
        r = client.post(f"{API}/applications/{app_id}/documents", headers=scrutiny, data=data,
                        files={"files": (item["filename"], (folder / item["filename"]).read_bytes())})
        assert r.status_code == 200, r.text
        assert len(r.json()[0]["sha256"]) == 64
    docs = client.get(f"{API}/applications/{app_id}/documents", headers=scrutiny).json()
    assert len(docs) == len(manifest)
    assert _app(client, scrutiny)["status"] == "SUBMITTED"


def test_prescrutiny_finds_exactly_the_seeded_issues(client, scrutiny):
    app_id = STATE["app_id"]
    run = _run(client, scrutiny, app_id)
    assert run["summary"]["rules_evaluated"] == 24
    assert run["summary"]["rules_passed"] == 16
    found = Counter((f["rule_id"], f["severity"]) for f in _open_findings(client, scrutiny, app_id))
    assert found == EXPECTED_FINDINGS, f"unexpected: {found - EXPECTED_FINDINGS}, missing: {EXPECTED_FINDINGS - found}"
    detail = client.get(f"{API}/applications/{app_id}", headers=scrutiny).json()
    assert detail["status"] == "NEEDS_REVIEW"
    assert detail["findings"]["critical"] == 2


def test_classification_and_extraction_accuracy(client, scrutiny):
    docs = {d["filename"]: d for d in client.get(f"{API}/applications/{STATE['app_id']}/documents",
                                                headers=scrutiny).json()}
    correct_types = sum(1 for m in STATE["manifest"] if docs[m["filename"]]["effective_type"] == m["expected_type"])
    assert correct_types == len(STATE["manifest"])
    total = hits = 0
    for m in STATE["manifest"]:
        fields = {f["field"]: f["normalized_value"] for f in
                  client.get(f"{API}/documents/{docs[m['filename']]['id']}", headers=scrutiny).json()["fields"]}
        for k, v in m["expected_fields"].items():
            total += 1
            hits += fields.get(k) == v
    accuracy = hits / total
    print(f"\nExtraction accuracy on demo set: {hits}/{total} = {accuracy:.0%}")
    assert accuracy >= 0.95
    scan = docs["affidavit_scanned.pdf"]
    assert scan["text_method"] == "ocr" and scan["ocr_confidence"] > 70


def test_finding_has_evidence_and_renders(client, scrutiny):
    fs = _open_findings(client, scrutiny, STATE["app_id"])
    intake = next(f for f in fs if f["rule_id"] == "EOA-INT-001")
    assert intake["expected_value"] == "≤ 180" and intake["actual_value"] == "240"
    kinds = [e["kind"] for e in intake["evidence"]]
    assert kinds.count("document") == 2 and "record" in kinds and "application_form" in kinds
    ev = next(e for e in intake["evidence"] if e["kind"] == "document" and "previous_eoa" in e["filename"])
    assert ev["page"] == 2 and len(ev["bbox"]) == 4
    token = scrutiny["Authorization"].split()[1]
    boxes = ",".join(str(v) for v in ev["bbox"])
    r = client.get(f"{API}/documents/{ev['document_id']}/pages/{ev['page']}/image?boxes={boxes}&token={token}")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    STATE["intake_finding"] = intake["id"]


def test_anomaly_wording_is_never_conclusive(client, scrutiny):
    for f in _open_findings(client, scrutiny, STATE["app_id"]):
        text = (f["title"] + " " + f["description"]).lower()
        assert not re.search(r"\b(forged|forgery|fake|fraud)\b", text), f["title"]
        if f["finding_type"] == "ANOMALY":
            assert f["title"].startswith("Potential anomaly") and "not proof" in f["description"]
        # Record comparisons are framed as needing verification, not as conclusions
        if re.search(r"\b(differs|different institution|no matching)\b", f["title"].lower()) \
                and f["finding_type"] in ("REGULATORY", "VERIFICATION", "CONSISTENCY", "INFRASTRUCTURE"):
            assert f["title"].endswith("verification required"), f["title"]


def test_verification_statuses_and_refresh(client, scrutiny, verifier):
    app_id = STATE["app_id"]
    rows = client.get(f"{API}/applications/{app_id}/verifications", headers=scrutiny).json()
    status = {r["document"]["filename"]: r["latest"]["status"] for r in rows if r["latest"]}
    assert status == {"noc.pdf": "VERIFIED", "accreditation.pdf": "EXPIRED",
                      "affidavit_scanned.pdf": "SOURCE_UNAVAILABLE", "infrastructure_certificate.pdf": "PENDING"}
    assert all(r["latest"]["is_mock"] for r in rows if r["latest"])
    pending = next(r["latest"] for r in rows if r["latest"] and r["latest"]["status"] == "PENDING")
    assert client.post(f"{API}/verifications/{pending['id']}/refresh", headers=scrutiny).status_code == 403
    r = client.post(f"{API}/verifications/{pending['id']}/refresh", headers=verifier)
    assert r.status_code == 200 and r.json()["status"] == "MISMATCH"
    assert any(not c["match"] and c["field"] == "built_up_area" for c in r.json()["comparison"])
    # Rules re-applied automatically: the pending INFO finding became a CRITICAL mismatch
    ver = [f for f in _open_findings(client, scrutiny, app_id) if f["rule_id"] == "EOA-VER-001"]
    assert any(f["severity"] == "CRITICAL" and "differs from submitted" in f["title"]
               and f["title"].endswith("verification required") for f in ver)
    # Manual confirmation for the unavailable notary registry
    aff = next(r["document"] for r in rows if r["document"]["filename"] == "affidavit_scanned.pdf")
    r = client.post(f"{API}/documents/{aff['id']}/verify/manual", headers=verifier,
                    json={"status": "VERIFIED", "note": "Confirmed with notary office by phone"})
    assert r.status_code == 200
    ver = [f for f in _open_findings(client, scrutiny, app_id) if f["rule_id"] == "EOA-VER-001"]
    assert not any("Affidavit" in f["title"] for f in ver)


def test_officer_actions(client, scrutiny):
    fid = STATE["intake_finding"]
    r = client.post(f"{API}/findings/{fid}/actions", headers=scrutiny, json={"action": "mark_reviewed", "note": ""})
    assert r.status_code == 400
    r = client.post(f"{API}/findings/{fid}/actions", headers=scrutiny,
                    json={"action": "request_clarification", "note": "Please submit the increase-in-intake approval."})
    assert r.status_code == 200 and r.json()["status"] == "CLARIFICATION_REQUESTED"
    assert r.json()["actions"][0]["note"].startswith("Please submit")
    assert _app(client, scrutiny)["status"] == "CLARIFICATION_REQUESTED"


def test_rectification_auto_clears(client, scrutiny, demo_dir):
    app_id = STATE["app_id"]
    folder = demo_dir / "EoA-2026-4821-rectification"
    r = client.post(f"{API}/applications/{app_id}/documents", headers=scrutiny,
                    files={"files": ("floor_plan.pdf", (folder / "floor_plan.pdf").read_bytes())})
    assert r.status_code == 200
    docs = client.get(f"{API}/applications/{app_id}/documents", headers=scrutiny).json()
    acc = next(d for d in docs if d["filename"] == "accreditation.pdf")
    r = client.post(f"{API}/documents/{acc['id']}/replace", headers=scrutiny,
                    files={"file": ("accreditation_renewed.pdf", (folder / "accreditation_renewed.pdf").read_bytes())})
    assert r.status_code == 200 and r.json()["replaces_document_id"] == acc["id"]
    assert client.get(f"{API}/applications/{app_id}", headers=scrutiny).json()["needs_rerun"] is True
    _run(client, scrutiny, app_id)
    fs = client.get(f"{API}/applications/{app_id}/findings", headers=scrutiny).json()
    by_rule = {}
    for f in fs:
        by_rule.setdefault(f["rule_id"], []).append(f["status"])
    assert by_rule["EOA-INF-001"] == ["AUTO_CLEARED"]
    assert by_rule["EOA-EXP-001"] == ["AUTO_CLEARED"]
    # Officer's clarification on the intake finding survives the re-run
    intake = next(f for f in fs if f["id"] == STATE["intake_finding"])
    assert intake["status"] == "CLARIFICATION_REQUESTED"
    rows = client.get(f"{API}/applications/{app_id}/verifications", headers=scrutiny).json()
    renewed = next(r for r in rows if r["document"]["filename"] == "accreditation_renewed.pdf")
    assert renewed["latest"]["status"] == "VERIFIED"


def test_admin_configures_rules(client, scrutiny, admin):
    app_id = STATE["app_id"]
    r = client.put(f"{API}/rules/EOA-EXP-002", headers=admin, json={"params": {"window_days": "abc"},
                                                                     "change_note": "bad value"})
    assert r.status_code == 400
    r = client.put(f"{API}/rules/EOA-EXP-002", headers=admin, json={"params": {"window_days": 10},
                                                                     "change_note": "Shorter warning window"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["history"][0]["version"] == 2
    _run(client, scrutiny, app_id)
    comp = client.get(f"{API}/applications/{app_id}/compliance", headers=scrutiny).json()["results"]
    exp2 = next(c for c in comp if c["rule_id"] == "EOA-EXP-002")
    assert exp2["rule_version"] == 2 and exp2["outcome"] == "PASS"  # 18 days > 10-day window
    # Disable a rule
    r = client.put(f"{API}/rules/EOA-ANM-004", headers=admin, json={"enabled": False, "change_note": "Pilot off"})
    assert r.status_code == 200
    _run(client, scrutiny, app_id)
    comp = client.get(f"{API}/applications/{app_id}/compliance", headers=scrutiny).json()["results"]
    assert next(c for c in comp if c["rule_id"] == "EOA-ANM-004")["outcome"] == "DISABLED"
    # Admin adds a new required-document rule without touching code
    r = client.post(f"{API}/rules", headers=admin, json={
        "rule_id": "EOA-DOC-010", "name": "Faculty list submitted", "group": "DOCUMENT", "check": "required_document",
        "params": {"doc_type": "FACULTY_LIST"}, "severity": "WARNING", "applies_to": ["EOA"],
        "change_note": "New circular"})
    assert r.status_code == 200, r.text
    _run(client, scrutiny, app_id)
    assert any(f["rule_id"] == "EOA-DOC-010" for f in _open_findings(client, scrutiny, app_id))
    # Reference date is configurable
    r = client.put(f"{API}/settings", headers=admin, json={"reference_date": "2026-11-15", "change_note": "test"})
    assert r.status_code == 200 and r.json()["reference_date"] == "2026-11-15"
    client.put(f"{API}/settings", headers=admin, json={"reference_date": "2026-10-22", "change_note": "restore"})


def test_outcome_requires_human_acknowledgement(client, scrutiny, verifier):
    app_id = STATE["app_id"]
    body = {"outcome": "RECOMMEND_APPROVAL", "note": "Recommending despite findings"}
    assert client.post(f"{API}/applications/{app_id}/outcome", headers=verifier, json=body).status_code == 403
    r = client.post(f"{API}/applications/{app_id}/outcome", headers=scrutiny, json=body)
    assert r.status_code == 400 and "critical" in r.json()["detail"]
    r = client.post(f"{API}/applications/{app_id}/outcome", headers=scrutiny,
                    json={"outcome": "ISSUE_DEFICIENCY_LETTER", "note": "Intake increase approval and NOC name "
                                                                       "clarification required."})
    assert r.status_code == 200 and r.json()["status"] == "DECIDED"
    assert client.post(f"{API}/applications/{app_id}/prescrutiny", headers=scrutiny).status_code == 409


def test_audit_trail_records_the_journey(client, scrutiny, admin):
    actions = {e["action"] for e in client.get(f"{API}/applications/{STATE['app_id']}/audit", headers=scrutiny).json()}
    for a in ("application.created", "document.uploaded", "document.processed", "records.checked",
              "verification.requested", "verification.refreshed", "verification.manual_recorded", "rules.evaluated",
              "finding.created", "finding.request_clarification", "finding.auto_cleared", "document.replaced",
              "prescrutiny.completed", "outcome.recorded"):
        assert a in actions, a
    glob = {e["action"] for e in client.get(f"{API}/audit", headers=admin).json()}
    assert {"auth.login", "rule.updated", "rule.created", "settings.updated"} <= glob
    assert client.get(f"{API}/audit", headers=scrutiny).status_code == 403


def test_dashboard_and_report(client, scrutiny):
    d = client.get(f"{API}/dashboard", headers=scrutiny).json()
    assert d["metrics"]["applications"] == 4 and d["alerts"]
    r = client.get(f"{API}/applications/{STATE['app_id']}/report", headers=scrutiny).json()
    assert r["findings"] and r["compliance"]["results"] and "Advisory only" in r["disclaimer"]


def test_create_application(client, scrutiny):
    inst = client.get(f"{API}/institutions", headers=scrutiny).json()[0]
    r = client.post(f"{API}/applications", headers=scrutiny, json={
        "institution_id": inst["id"], "category": "EOA", "academic_year": "2026-27",
        "programmes": [{"programme": "MBA", "intake": 60}], "built_up_area_sqm": 1000})
    assert r.status_code == 200 and r.json()["code"].startswith("EoA-2026-") and r.json()["status"] == "DRAFT"
