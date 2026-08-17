from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import io

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.main import app

TODAY = date.today()
AUDIT = {"operator": "Tester", "reason": "Automated regression"}
VALID_ABN = "51824753556"


def reset_database() -> None:
    """Empty the workspace between tests.

    One SQLite file is shared for the whole session, so without this a client
    name or document number created by one test leaks into the next.
    """
    from app.db import SessionLocal
    from app.models import Client, Company, Document, DocumentCounter, DocumentEvent, DocumentLine

    with SessionLocal() as session:
        session.query(DocumentEvent).delete()
        session.query(DocumentLine).delete()
        # Receipts reference invoices with ON DELETE RESTRICT, so they go first.
        session.query(Document).filter(Document.doc_type == "receipt").delete()
        session.query(Document).filter(Document.doc_type == "invoice").delete()
        session.query(Client).delete()
        session.query(DocumentCounter).delete()
        session.query(Company).filter(Company.id != 1).delete()
        company = session.get(Company, 1)
        if company is not None:
            company.legal_name = "Fictional Legal Pty Ltd"
            company.trading_name = "Fictional Trading"
            company.abn = VALID_ABN
            company.gst_registered = True
            company.payment_terms_days = 14
        session.commit()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        # Each test starts from a clean, GST-registered business.
        reset_database()
        test_client.headers.update({"X-Company-ID": "1"})
        yield test_client


def make_client(client: TestClient, name: str = "Fictional Customer") -> int:
    response = client.post("/api/v1/clients", json={"display_name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_invoice(client: TestClient, client_id: int, *, unit_price="1000.00", quantity="1"):
    return client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": TODAY.isoformat(),
            "lines": [
                {"description": "Consulting", "quantity": quantity, "unit_price": unit_price}
            ],
            "operator": "Tester",
        },
    )


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


# --------------------------------------------------------------------------- company


def test_company_starts_as_a_single_editable_record(client):
    company = client.get("/api/v1/company").json()
    assert company["id"] == 1
    assert company["payment_terms_days"] == 14


def test_trading_name_is_optional_but_legal_name_is_required(client):
    updated = client.patch(
        "/api/v1/company",
        json={"legal_name": "Fictional Legal Pty Ltd", "trading_name": None},
    )
    assert updated.status_code == 200
    assert updated.json()["legal_name"] == "Fictional Legal Pty Ltd"
    assert updated.json()["trading_name"] is None

    assert client.patch("/api/v1/company", json={"legal_name": None}).status_code == 422
    assert client.patch("/api/v1/company", json={"legal_name": "   "}).status_code == 422


def test_gst_registration_requires_a_valid_abn(client):
    rejected = client.patch("/api/v1/company", json={"abn": "12345678901"})
    assert rejected.status_code == 422
    cleared = client.patch("/api/v1/company", json={"gst_registered": False, "abn": None})
    assert cleared.status_code == 200
    still_rejected = client.patch("/api/v1/company", json={"gst_registered": True})
    assert still_rejected.status_code == 422


def test_companies_are_selected_without_login_and_keep_data_isolated(client):
    second = client.post(
        "/api/v1/companies",
        json={"legal_name": "Second Legal Pty Ltd", "trading_name": "Second Books"},
    )
    assert second.status_code == 201
    second_id = second.json()["id"]
    assert [company["id"] for company in client.get("/api/v1/companies").json()] == [1, second_id]

    first_client = make_client(client, "Shared Customer Name")
    first_invoice = make_invoice(client, first_client).json()

    second_headers = {"X-Company-ID": str(second_id)}
    second_client_response = client.post(
        "/api/v1/clients",
        json={"display_name": "Shared Customer Name"},
        headers=second_headers,
    )
    assert second_client_response.status_code == 201
    second_invoice = client.post(
        "/api/v1/invoices",
        headers=second_headers,
        json={
            "client_id": second_client_response.json()["id"],
            "issue_date": TODAY.isoformat(),
            "lines": [{"description": "Second company work", "quantity": "1", "unit_price": "50"}],
            "operator": "Tester",
        },
    )
    assert second_invoice.status_code == 201
    assert second_invoice.json()["doc_number"].startswith(f"INV-C{second_id}-{TODAY.year}-0001")

    first_documents = client.get("/api/v1/documents").json()
    second_documents = client.get("/api/v1/documents", headers=second_headers).json()
    assert [document["id"] for document in first_documents] == [first_invoice["id"]]
    assert [document["id"] for document in second_documents] == [second_invoice.json()["id"]]
    assert (
        client.get(
            f"/api/v1/documents/{first_invoice['id']}", headers=second_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/documents/{first_invoice['id']}/pdf", headers=second_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/documents/{first_invoice['id']}/audit", headers=second_headers
        ).status_code
        == 404
    )

    update_payload = {
        "client_id": first_client,
        "issue_date": TODAY.isoformat(),
        "lines": [{"description": "Cross-company edit", "quantity": "1", "unit_price": "1"}],
        "operator": "Tester",
    }
    assert (
        client.put(
            f"/api/v1/invoices/{first_invoice['id']}",
            headers=second_headers,
            json=update_payload,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/invoices/{first_invoice['id']}/receipts",
            headers=second_headers,
            json={"operator": "Tester"},
        ).status_code
        == 404
    )
    assert (
        client.request(
            "DELETE",
            f"/api/v1/documents/{first_invoice['id']}",
            headers=second_headers,
            json=AUDIT,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/documents/{first_invoice['id']}/restore",
            headers=second_headers,
            json=AUDIT,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/clients/{first_client}",
            headers=second_headers,
            json={"display_name": "Cross-company edit"},
        ).status_code
        == 404
    )

    client.patch(
        "/api/v1/company",
        headers=second_headers,
        json={"trading_name": "Second Books Updated"},
    )
    assert client.get("/api/v1/company").json()["trading_name"] == "Fictional Trading"
    assert (
        client.get("/api/v1/company", headers=second_headers).json()["trading_name"]
        == "Second Books Updated"
    )


def test_company_legal_name_cannot_be_changed_to_an_existing_name(client):
    second = client.post(
        "/api/v1/companies",
        json={"legal_name": "Second Legal Pty Ltd"},
    )
    assert second.status_code == 201

    duplicate = client.patch(
        "/api/v1/company",
        json={"legal_name": "second legal pty ltd"},
    )
    assert duplicate.status_code == 409
    assert client.get("/api/v1/company").json()["legal_name"] == "Fictional Legal Pty Ltd"


def test_company_selection_header_is_required_for_company_data(client):
    previous = client.headers.pop("X-Company-ID")
    try:
        assert client.get("/api/v1/companies").status_code == 200
        response = client.get("/api/v1/clients")
        assert response.status_code == 422
        assert "X-Company-ID" in response.text
    finally:
        client.headers["X-Company-ID"] = previous


def test_list_endpoints_reject_a_company_that_does_not_exist(client):
    missing_company = {"X-Company-ID": "999999"}
    assert client.get("/api/v1/clients", headers=missing_company).status_code == 404
    assert client.get("/api/v1/documents", headers=missing_company).status_code == 404


# --------------------------------------------------------------------------- invoices


def test_invoice_operator_is_optional(client):
    client_id = make_client(client)
    response = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": TODAY.isoformat(),
            "lines": [{"description": "Consulting", "quantity": "1", "unit_price": "100"}],
        },
    )

    assert response.status_code == 201, response.text
    events = client.get(f"/api/v1/documents/{response.json()['id']}/audit").json()
    assert events[0]["operator"] == "Not specified"


def test_invoice_totals_gst_exclusive(client):
    invoice = make_invoice(client, make_client(client)).json()
    assert (invoice["subtotal"], invoice["gst_amount"], invoice["total"]) == (
        "1000.00",
        "100.00",
        "1100.00",
    )
    assert invoice["doc_number"].startswith(f"INV-{TODAY.year}-")
    assert invoice["status"] == "issued"
    assert invoice["amount_outstanding"] == "1100.00"


def test_invoice_totals_gst_inclusive(client):
    client_id = make_client(client)
    response = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": TODAY.isoformat(),
            "lines": [{"description": "Consulting", "quantity": "1", "unit_price": "1000.00"}],
            "gst_inclusive": True,
            "operator": "Tester",
        },
    )
    invoice = response.json()
    assert (invoice["subtotal"], invoice["gst_amount"], invoice["total"]) == (
        "909.09",
        "90.91",
        "1000.00",
    )


@pytest.mark.parametrize("gst_inclusive", [False, True])
def test_invoice_supports_taxable_and_gst_free_lines(client, gst_inclusive):
    client_id = make_client(client)
    taxable_price = "110.00" if gst_inclusive else "100.00"
    response = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": TODAY.isoformat(),
            "gst_inclusive": gst_inclusive,
            "lines": [
                {
                    "description": "Taxable service",
                    "quantity": "1",
                    "unit_price": taxable_price,
                    "gst_treatment": "taxable",
                },
                {
                    "description": "GST-free service",
                    "quantity": "1",
                    "unit_price": "50.00",
                    "gst_treatment": "gst_free",
                },
            ],
            "operator": "Tester",
        },
    )

    assert response.status_code == 201, response.text
    invoice = response.json()
    assert (invoice["subtotal"], invoice["gst_amount"], invoice["total"]) == (
        "150.00",
        "10.00",
        "160.00",
    )
    assert [line["gst_treatment"] for line in invoice["lines"]] == ["taxable", "gst_free"]

    text = pdf_text(client.get(f"/api/v1/documents/{invoice['id']}/pdf").content)
    assert "Taxable service [GST]" in text
    assert "GST-free service [GST-free]" in text


def test_invoice_without_gst_registration_charges_no_gst(client):
    client.patch("/api/v1/company", json={"gst_registered": False})
    invoice = make_invoice(client, make_client(client)).json()
    assert (invoice["subtotal"], invoice["gst_amount"], invoice["total"]) == (
        "1000.00",
        "0.00",
        "1000.00",
    )
    assert invoice["lines"][0]["gst_treatment"] == "gst_free"


def test_due_date_defaults_to_the_configured_payment_terms(client):
    client.patch("/api/v1/company", json={"payment_terms_days": 30})
    invoice = make_invoice(client, make_client(client)).json()
    assert invoice["due_date"] == (TODAY + timedelta(days=30)).isoformat()


@pytest.mark.parametrize(
    "bad_price", ["-1", "1e12", "1000.999", "1,000.00", "abc", "9999999999999.99"]
)
def test_malformed_money_is_rejected(client, bad_price):
    assert make_invoice(client, make_client(client), unit_price=bad_price).status_code == 422


def test_future_dated_invoice_is_rejected(client):
    client_id = make_client(client)
    response = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": (TODAY + timedelta(days=1)).isoformat(),
            "lines": [{"description": "X", "quantity": "1", "unit_price": "10.00"}],
            "operator": "Tester",
        },
    )
    assert response.status_code == 422


def test_zero_value_invoice_is_allowed(client):
    response = make_invoice(client, make_client(client), unit_price="0")

    assert response.status_code == 201, response.text
    invoice = response.json()
    assert (invoice["subtotal"], invoice["gst_amount"], invoice["total"]) == (
        "0.00",
        "0.00",
        "0.00",
    )


# --------------------------------------------------------------------------- receipts


def test_receipt_defaults_to_the_full_outstanding_amount(client):
    invoice = make_invoice(client, make_client(client)).json()
    receipt = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["total"] == "1100.00"
    assert receipt.json()["doc_number"] == invoice["doc_number"].replace("INV", "RCT") + "-1"

    refreshed = client.get(f"/api/v1/documents/{invoice['id']}").json()
    assert refreshed["status"] == "paid"
    assert refreshed["amount_outstanding"] == "0.00"


def test_partial_payments_accumulate_and_split_gst_exactly(client):
    invoice = make_invoice(client, make_client(client)).json()
    first = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"amount": "400.00", "operator": "Tester"},
    )
    assert first.status_code == 201, first.text
    mid = client.get(f"/api/v1/documents/{invoice['id']}").json()
    assert mid["status"] == "partially_paid"
    assert mid["amount_received"] == "400.00"
    assert mid["amount_outstanding"] == "700.00"

    second = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["total"] == "700.00"

    final = client.get(f"/api/v1/documents/{invoice['id']}").json()
    assert final["status"] == "paid"
    assert final["amount_received"] == "1100.00"
    # The parts must add back up to the invoice exactly, GST included.
    receipts = [client.get(f"/api/v1/documents/{r['id']}").json() for r in final["receipts"]]
    assert sum(Decimal(r["subtotal"]) for r in receipts) == Decimal(invoice["subtotal"])
    assert sum(Decimal(r["gst_amount"]) for r in receipts) == Decimal(invoice["gst_amount"])


def test_overpayment_is_refused(client):
    invoice = make_invoice(client, make_client(client)).json()
    too_much = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"amount": "1100.01", "operator": "Tester"},
    )
    assert too_much.status_code == 400
    client.post(f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"})
    again = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    )
    assert again.status_code == 409


def test_concurrent_receipts_never_exceed_the_invoice_total(client):
    invoice = make_invoice(client, make_client(client)).json()

    def pay(_):
        return client.post(
            f"/api/v1/invoices/{invoice['id']}/receipts",
            json={"amount": "700.00", "operator": "Tester"},
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(pay, range(4)))

    final = client.get(f"/api/v1/documents/{invoice['id']}").json()
    assert Decimal(final["amount_received"]) <= Decimal(final["total"])


def test_concurrent_invoices_receive_distinct_company_serials(client):
    client_id = make_client(client)

    def issue(sequence: int):
        response = client.post(
            "/api/v1/invoices",
            json={
                "client_id": client_id,
                "issue_date": TODAY.isoformat(),
                "lines": [
                    {
                        "description": f"Concurrent invoice {sequence}",
                        "quantity": "1",
                        "unit_price": "10.00",
                    }
                ],
                "operator": "Tester",
            },
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(issue, range(4)))

    assert [status for status, _payload in results] == [201, 201, 201, 201]
    numbers = {payload["doc_number"] for _status, payload in results}
    assert numbers == {f"INV-{TODAY.year}-{serial:04d}" for serial in range(1, 5)}


def test_receipt_cannot_predate_its_invoice(client):
    invoice = make_invoice(client, make_client(client)).json()
    response = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"paid_date": (TODAY - timedelta(days=1)).isoformat(), "operator": "Tester"},
    )
    assert response.status_code == 400


def test_future_dated_receipt_is_rejected(client):
    invoice = make_invoice(client, make_client(client)).json()
    response = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"paid_date": (TODAY + timedelta(days=1)).isoformat(), "operator": "Tester"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- editing


def test_invoice_is_locked_once_a_receipt_exists(client):
    client_id = make_client(client)
    invoice = make_invoice(client, client_id).json()
    payload = {
        "client_id": client_id,
        "issue_date": TODAY.isoformat(),
        "lines": [{"description": "Revised", "quantity": "1", "unit_price": "2000.00"}],
        "operator": "Tester",
    }
    editable = client.put(f"/api/v1/invoices/{invoice['id']}", json=payload)
    assert editable.status_code == 200, editable.text
    assert editable.json()["total"] == "2200.00"

    client.post(f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"})
    blocked = client.put(f"/api/v1/invoices/{invoice['id']}", json=payload)
    assert blocked.status_code == 409
    assert "receipt" in blocked.json()["detail"].lower()


# --------------------------------------------------------------------------- void / restore


def test_voiding_an_invoice_cascades_to_its_receipts(client):
    invoice = make_invoice(client, make_client(client)).json()
    receipt = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"amount": "500.00", "operator": "Tester"},
    ).json()

    voided = client.request("DELETE", f"/api/v1/documents/{invoice['id']}", json=AUDIT)
    assert voided.status_code == 204
    assert client.get(f"/api/v1/documents/{invoice['id']}").json()["status"] == "void"
    assert client.get(f"/api/v1/documents/{receipt['id']}").json()["status"] == "void"


def test_voiding_a_receipt_reopens_the_invoice(client):
    invoice = make_invoice(client, make_client(client)).json()
    receipt = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    ).json()
    assert client.get(f"/api/v1/documents/{invoice['id']}").json()["status"] == "paid"

    client.request("DELETE", f"/api/v1/documents/{receipt['id']}", json=AUDIT)
    reopened = client.get(f"/api/v1/documents/{invoice['id']}").json()
    assert reopened["status"] == "issued"
    assert reopened["amount_outstanding"] == "1100.00"


def test_void_requires_a_nonblank_operator_and_reason(client):
    invoice = make_invoice(client, make_client(client)).json()
    response = client.request(
        "DELETE", f"/api/v1/documents/{invoice['id']}", json={"operator": "  ", "reason": " x "}
    )
    assert response.status_code == 422


def test_restore_is_blocked_when_it_would_overpay(client):
    invoice = make_invoice(client, make_client(client)).json()
    first = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts",
        json={"amount": "600.00", "operator": "Tester"},
    ).json()
    client.request("DELETE", f"/api/v1/documents/{first['id']}", json=AUDIT)
    # Take the full amount with a fresh receipt, then try to bring the old one back.
    client.post(f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"})
    blocked = client.post(f"/api/v1/documents/{first['id']}/restore", json=AUDIT)
    assert blocked.status_code == 409
    assert "overpay" in blocked.json()["detail"].lower()


def test_receipt_cannot_be_restored_before_its_invoice(client):
    invoice = make_invoice(client, make_client(client)).json()
    receipt = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    ).json()
    client.request("DELETE", f"/api/v1/documents/{invoice['id']}", json=AUDIT)
    blocked = client.post(f"/api/v1/documents/{receipt['id']}/restore", json=AUDIT)
    assert blocked.status_code == 409


# --------------------------------------------------------------------------- PDFs


def test_pdf_uses_legal_name_when_there_is_no_trading_name(client):
    response = client.patch(
        "/api/v1/company",
        json={"legal_name": "Only Legal Name Pty Ltd", "trading_name": None},
    )
    assert response.status_code == 200

    invoice = make_invoice(client, make_client(client)).json()
    text = pdf_text(client.get(f"/api/v1/documents/{invoice['id']}/pdf").content)
    assert "Only Legal Name Pty Ltd" in text
    assert "Legal name: Only Legal Name Pty Ltd" not in text


def test_pdf_download_uses_a_real_attachment_filename(client):
    client_id = make_client(client)
    invoice = make_invoice(client, client_id).json()

    response = client.get(
        f"/api/v1/documents/{invoice['id']}/pdf/download",
        params={"company_id": 1},
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{invoice["doc_number"]}.pdf"'
    )


def test_company_name_is_repeated_on_every_pdf_continuation_page(client):
    client_id = make_client(client)
    response = client.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "issue_date": TODAY.isoformat(),
            "lines": [
                {
                    "description": f"Consulting line {index:03d}",
                    "quantity": "1",
                    "unit_price": "1.00",
                }
                for index in range(80)
            ],
            "operator": "Tester",
        },
    )
    assert response.status_code == 201, response.text

    content = client.get(f"/api/v1/documents/{response.json()['id']}/pdf").content
    pages = PdfReader(io.BytesIO(content)).pages
    assert len(pages) > 1
    assert all("Fictional Trading" in (page.extract_text() or "") for page in pages)


def test_pdfs_are_immutable_snapshots(client):
    invoice = make_invoice(client, make_client(client)).json()
    original = client.get(f"/api/v1/documents/{invoice['id']}/pdf").content
    assert original.startswith(b"%PDF")
    text = pdf_text(original)
    assert "TAX INVOICE" in text
    assert "Fictional Trading" in text
    assert "Legal name: Fictional Legal Pty Ltd" in text

    # Renaming the business must not rewrite an issued document.
    client.patch("/api/v1/company", json={"trading_name": "RENAMED TRADING NAME"})
    assert client.get(f"/api/v1/documents/{invoice['id']}/pdf").content == original


def test_receipt_pdf_references_its_invoice(client):
    invoice = make_invoice(client, make_client(client)).json()
    receipt = client.post(
        f"/api/v1/invoices/{invoice['id']}/receipts", json={"operator": "Tester"}
    ).json()
    text = pdf_text(client.get(f"/api/v1/documents/{receipt['id']}/pdf").content)
    assert "RECEIPT" in text
    assert invoice["doc_number"] in text
    # The source is an invoice here, not the parent system's payment request.
    # Info-table labels are rendered uppercase.
    assert "INVOICE #" in text
    assert "PAYMENT REQUEST" not in text.upper()


def test_void_documents_cannot_be_downloaded(client):
    invoice = make_invoice(client, make_client(client)).json()
    client.request("DELETE", f"/api/v1/documents/{invoice['id']}", json=AUDIT)
    assert client.get(f"/api/v1/documents/{invoice['id']}/pdf").status_code == 409


def test_unrenderable_characters_are_a_client_error(client):
    client_id = client.post(
        "/api/v1/clients", json={"display_name": "Emoji \U0001f600 Customer"}
    ).json()["id"]
    response = make_invoice(client, client_id)
    assert response.status_code != 500
    assert response.status_code == 422


# --------------------------------------------------------------------------- audit


def test_audit_trail_records_before_and_after_with_a_pdf_hash(client):
    invoice = make_invoice(client, make_client(client)).json()
    client.request("DELETE", f"/api/v1/documents/{invoice['id']}", json=AUDIT)
    events = client.get(f"/api/v1/documents/{invoice['id']}/audit").json()
    assert [event["action"] for event in events] == ["created", "voided"]
    assert events[0]["snapshot"]["after"]["pdf_sha256"]
    assert events[1]["snapshot"]["before"]["status"] == "issued"
    assert events[1]["snapshot"]["after"]["status"] == "void"
    assert events[1]["operator"] == "Tester"


def test_timestamps_carry_an_explicit_utc_offset(client):
    invoice = make_invoice(client, make_client(client)).json()
    events = client.get(f"/api/v1/documents/{invoice['id']}/audit").json()
    for value in (invoice["created_at"], invoice["updated_at"], events[0]["occurred_at"]):
        assert value.endswith("Z") or "+00:00" in value


def test_client_edits_do_not_rewrite_issued_documents(client):
    client_id = make_client(client, "Original Name")
    invoice = make_invoice(client, client_id).json()
    client.patch(f"/api/v1/clients/{client_id}", json={"display_name": "Renamed Customer"})
    assert client.get(f"/api/v1/documents/{invoice['id']}").json()["customer_name"] == "Original Name"


# --------------------------------------------------------------------------- API surface


def test_unknown_api_route_is_json_not_the_spa(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


def test_foreign_host_header_is_rejected(client):
    assert client.get("/health", headers={"Host": "evil.example.com"}).status_code == 400


def test_cross_site_browser_mutations_are_rejected(client):
    bad_origin = client.post(
        "/api/v1/companies",
        headers={"Origin": "https://evil.example"},
        json={"legal_name": "Blocked Origin Pty Ltd"},
    )
    assert bad_origin.status_code == 403

    bad_fetch_site = client.post(
        "/api/v1/companies",
        headers={
            "Origin": "http://testserver",
            "Sec-Fetch-Site": "cross-site",
        },
        json={"legal_name": "Blocked Fetch Site Pty Ltd"},
    )
    assert bad_fetch_site.status_code == 403

    same_origin = client.post(
        "/api/v1/companies",
        headers={"Origin": "http://testserver"},
        json={"legal_name": "Allowed Same Origin Pty Ltd"},
    )
    assert same_origin.status_code == 201
    names = {company["legal_name"] for company in client.get("/api/v1/companies").json()}
    assert names == {"Fictional Legal Pty Ltd", "Allowed Same Origin Pty Ltd"}


def test_list_metadata_is_exposed(client):
    make_invoice(client, make_client(client))
    response = client.get("/api/v1/documents", params={"doc_type": "invoice"})
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Result-Truncated"] == "false"


def test_duplicate_client_names_are_refused(client):
    make_client(client, "Same Name")
    assert client.post("/api/v1/clients", json={"display_name": "same name"}).status_code == 409
