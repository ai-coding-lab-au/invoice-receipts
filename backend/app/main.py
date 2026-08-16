from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import os
from pathlib import Path
from typing import Annotated, Iterator
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from .config import settings
from .db import DatabaseBusyError, begin_immediate, db_session, dispose_engine, init_db
from .models import Client, Company, Document, DocumentCounter, DocumentEvent, DocumentLine
from .runtime_lock import RuntimeLockError, acquire_runtime_lock, runtime_lock_path
from .schemas import (
    AuditAction,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    DocumentOut,
    EventOut,
    InvoiceCreate,
    ReceiptCreate,
    is_valid_abn,
)
from .services.pdf_render import render_document_pdf

PathId = Annotated[int, ApiPath(ge=1, le=2**63 - 1)]
CompanyId = Annotated[int, Header(alias="X-Company-ID", ge=1, le=2**63 - 1)]
LIST_LIMIT = 500


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_db() -> Iterator[Session]:
    with db_session() as session:
        yield session


def get_company(session: Session, company_id: int) -> Company:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def set_list_metadata(response: Response, *, total: int, returned: int) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Result-Limit"] = str(LIST_LIMIT)
    response.headers["X-Result-Truncated"] = "true" if total > returned else "false"


# --------------------------------------------------------------------------- numbering


def next_serial(session: Session, company_id: int, year: int) -> int:
    """Allocate the next serial for one company/year inside the open transaction."""
    counter = session.get(DocumentCounter, (company_id, year))
    if counter is None:
        counter = DocumentCounter(company_id=company_id, year=year, last_serial=0)
        session.add(counter)
        session.flush()
    counter.last_serial += 1
    session.flush()
    return counter.last_serial


def invoice_number(session: Session, company_id: int, issue_date: date) -> str:
    serial = next_serial(session, company_id, issue_date.year)
    company_marker = "" if company_id == 1 else f"C{company_id}-"
    return f"INV-{company_marker}{issue_date.year}-{serial:04d}"


def receipt_number(session: Session, invoice: Document) -> str:
    """Keep the full invoice number core so receipts remain globally traceable."""
    invoice_core = (
        invoice.doc_number[4:] if invoice.doc_number.startswith("INV-") else invoice.doc_number
    )
    used = (
        session.query(Document)
        .filter(
            Document.doc_type == "receipt",
            Document.invoice_id == invoice.id,
            Document.company_id == invoice.company_id,
        )
        .count()
    )
    return f"RCT-{invoice_core}-{used + 1}"


# --------------------------------------------------------------------------- money


def compute_totals(
    lines: list[dict], *, gst_registered: bool, gst_inclusive: bool
) -> tuple[Decimal, Decimal, Decimal]:
    gross = sum((money(line["amount"]) for line in lines), Decimal("0"))
    if not gst_registered:
        return money(gross), Decimal("0.00"), money(gross)
    if gst_inclusive:
        subtotal = money(gross / Decimal("1.10"))
        return subtotal, money(gross - subtotal), money(gross)
    gst = money(gross * Decimal("0.10"))
    return money(gross), gst, money(gross + gst)


def active_receipts(session: Session, invoice: Document) -> list[Document]:
    return (
        session.query(Document)
        .filter(
            Document.doc_type == "receipt",
            Document.invoice_id == invoice.id,
            Document.company_id == invoice.company_id,
            Document.status != "void",
        )
        .order_by(Document.id)
        .all()
    )


def all_receipts(session: Session, invoice: Document) -> list[Document]:
    return (
        session.query(Document)
        .filter(
            Document.doc_type == "receipt",
            Document.invoice_id == invoice.id,
            Document.company_id == invoice.company_id,
        )
        .order_by(Document.id)
        .all()
    )


def received_total(session: Session, invoice: Document) -> Decimal:
    return money(
        sum((Decimal(r.total) for r in active_receipts(session, invoice)), Decimal("0"))
    )


def recompute_invoice_status(session: Session, invoice: Document) -> None:
    """The single source of truth for an invoice's payment status."""
    if invoice.status == "void":
        return
    received = received_total(session, invoice)
    if received <= 0:
        invoice.status = "issued"
    elif received < money(invoice.total):
        invoice.status = "partially_paid"
    else:
        invoice.status = "paid"


def edit_block_reason(session: Session, invoice: Document) -> str | None:
    if invoice.status == "void":
        return "Restore the invoice before editing it"
    if all_receipts(session, invoice):
        return "Void every receipt on this invoice before editing it"
    return None


# --------------------------------------------------------------------------- audit


def snapshot(document: Document) -> dict:
    return {
        "doc_type": document.doc_type,
        "doc_number": document.doc_number,
        "status": document.status,
        "issue_date": document.issue_date.isoformat(),
        "due_date": document.due_date.isoformat() if document.due_date else None,
        "invoice_id": document.invoice_id,
        "client_id": document.client_id,
        "customer": {
            "name": document.customer_name,
            "abn": document.customer_abn,
            "address": document.customer_address,
            "email": document.customer_email,
            "phone": document.customer_phone,
        },
        "subtotal": str(money(document.subtotal)),
        "gst_amount": str(money(document.gst_amount)),
        "total": str(money(document.total)),
        "gst_inclusive": document.gst_inclusive,
        "paid_date": document.paid_date.isoformat() if document.paid_date else None,
        "payment_method": document.payment_method,
        "notes": document.notes,
        "lines": [
            {
                "order_no": line.order_no,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(money(line.unit_price)),
                "amount": str(money(line.amount)),
            }
            for line in document.lines
        ],
        "pdf_sha256": (
            hashlib.sha256(bytes(document.pdf_content)).hexdigest()
            if document.pdf_content
            else None
        ),
    }


def record_event(
    session: Session,
    document: Document,
    action: str,
    *,
    operator: str,
    reason: str,
    before: dict | None = None,
) -> None:
    session.flush()
    session.add(
        DocumentEvent(
            document_id=document.id,
            action=action,
            operator=operator,
            reason=reason,
            snapshot={"before": before, "after": snapshot(document)},
        )
    )


# --------------------------------------------------------------------------- PDF


def company_payload(company: Company) -> dict:
    return {
        "legal_name": company.legal_name,
        "trading_name": company.trading_name,
        "abn": company.abn,
        "address_line1": company.address_line1,
        "address_line2": company.address_line2,
        "suburb": company.suburb,
        "state": company.state,
        "postcode": company.postcode,
        "phone": company.phone,
        "email": company.email,
        "bank_account_name": company.bank_account_name,
        "bank_name": company.bank_name,
        "bank_bsb": company.bank_bsb,
        "bank_account_number": company.bank_account_number,
        "bank_swift": company.bank_swift,
    }


def ensure_tax_details(company: Company) -> None:
    if company.gst_registered and not is_valid_abn(company.abn):
        raise HTTPException(
            409,
            "Set a valid 11-digit ABN in Settings before issuing GST documents",
        )


def persist_pdf(
    document: Document, company: Company, *, source_document_number: str | None = None
) -> None:
    """Render and attach the PDF inside the caller's transaction.

    The bytes are stored on the row, so an issued document can always be
    reproduced exactly and later changes to Settings cannot rewrite history.
    """
    ensure_tax_details(company)
    try:
        content = render_document_pdf(
            doc_type=document.doc_type,
            doc_number=document.doc_number,
            issue_date=document.issue_date,
            expiration_date=document.due_date,
            company=company_payload(company),
            customer={
                "name": document.customer_name,
                "abn": document.customer_abn,
                "address": document.customer_address,
                "email": document.customer_email,
                "phone": document.customer_phone,
            },
            lines=[
                {
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "amount": line.amount,
                }
                for line in document.lines
            ],
            subtotal=document.subtotal,
            gst_amount=document.gst_amount,
            total=document.total,
            currency=document.currency,
            paid_date=document.paid_date,
            payment_method=document.payment_method,
            notes=document.notes,
            is_gst_registered=company.gst_registered,
            source_document_number=source_document_number,
        )
    except ValueError as exc:
        # User-controlled text the bundled fonts cannot draw must be a client
        # error, never a 500, and nothing may be persisted.
        if "font coverage is missing character" in str(exc):
            raise HTTPException(
                422, f"The document contains a character that cannot be rendered: {exc}"
            ) from exc
        raise
    document.pdf_content = content


# --------------------------------------------------------------------------- serialisation


def serialize(document: Document, session: Session | None = None) -> dict:
    data = {
        "id": document.id,
        "company_id": document.company_id,
        "doc_type": document.doc_type,
        "doc_number": document.doc_number,
        "issue_date": document.issue_date,
        "due_date": document.due_date,
        "client_id": document.client_id,
        "invoice_id": document.invoice_id,
        "customer_name": document.customer_name,
        "customer_abn": document.customer_abn,
        "customer_address": document.customer_address,
        "customer_email": document.customer_email,
        "customer_phone": document.customer_phone,
        "currency": document.currency,
        "subtotal": document.subtotal,
        "gst_amount": document.gst_amount,
        "total": document.total,
        "gst_inclusive": document.gst_inclusive,
        "status": document.status,
        "paid_date": document.paid_date,
        "payment_method": document.payment_method,
        "notes": document.notes,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "lines": document.lines,
        "receipts": [],
        "amount_received": None,
        "amount_outstanding": None,
        "can_edit": False,
        "edit_block_reason": None,
    }
    if session is not None and document.doc_type == "invoice":
        received = received_total(session, document)
        blocked = edit_block_reason(session, document)
        data.update(
            receipts=[
                {
                    "id": r.id,
                    "doc_number": r.doc_number,
                    "status": r.status,
                    "total": r.total,
                    "paid_date": r.paid_date,
                    "payment_method": r.payment_method,
                }
                for r in all_receipts(session, document)
            ],
            amount_received=received,
            amount_outstanding=money(max(Decimal(document.total) - received, Decimal("0"))),
            can_edit=blocked is None,
            edit_block_reason=blocked,
        )
    return data


# --------------------------------------------------------------------------- app


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        lock = acquire_runtime_lock(
            runtime_lock_path(settings.data_dir), owner=f"PID {os.getpid()}"
        )
    except RuntimeLockError as exc:
        raise RuntimeError(f"Invoice & Receipts is already running ({exc})") from exc
    try:
        init_db()
        yield
    finally:
        lock.release()
        dispose_engine()


app = FastAPI(title="Invoice & Receipts", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "::1", "testserver"],
)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _effective_port(scheme: str, port: int | None) -> int | None:
    if port is not None:
        return port
    return {"http": 80, "https": 443}.get(scheme)


def _same_origin(request: Request, origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme == request.url.scheme
            and parsed.hostname == request.url.hostname
            and _effective_port(parsed.scheme, parsed.port)
            == _effective_port(request.url.scheme, request.url.port)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


def _is_cross_site_mutation(request: Request) -> bool:
    if request.method not in _MUTATING_METHODS:
        return False
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return True
    origin = request.headers.get("origin")
    return origin is not None and not _same_origin(request, origin)


@app.exception_handler(DatabaseBusyError)
async def database_busy_handler(_request, exc: DatabaseBusyError):
    return JSONResponse(
        status_code=503,
        content={"detail": f"The database is busy ({exc}); please retry in a moment."},
        headers={"Retry-After": "1"},
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if _is_cross_site_mutation(request):
        response = JSONResponse(
            status_code=403,
            content={"detail": "Cross-site changes are not allowed"},
        )
    else:
        response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
        "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- companies


@app.get("/api/v1/companies", response_model=list[CompanyOut])
def list_companies(session: Session = Depends(get_db)):
    return session.query(Company).order_by(Company.legal_name, Company.id).all()


@app.post("/api/v1/companies", response_model=CompanyOut, status_code=201)
def create_company(payload: CompanyCreate, session: Session = Depends(get_db)):
    begin_immediate(session)
    duplicate = (
        session.query(Company)
        .filter(Company.legal_name.ilike(payload.legal_name))
        .first()
    )
    if duplicate:
        raise HTTPException(409, "A company with this legal name already exists")
    company = Company(**payload.model_dump())
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


# --------------------------------------------------------------------------- selected company


@app.get("/api/v1/company", response_model=CompanyOut)
def read_company(company_id: CompanyId, session: Session = Depends(get_db)):
    return get_company(session, company_id)


@app.patch("/api/v1/company", response_model=CompanyOut)
def update_company(
    payload: CompanyUpdate, company_id: CompanyId, session: Session = Depends(get_db)
):
    begin_immediate(session)
    company = get_company(session, company_id)
    updates = payload.model_dump(exclude_unset=True)
    prospective_legal_name = updates.get("legal_name", company.legal_name)
    duplicate = (
        session.query(Company)
        .filter(
            Company.id != company.id,
            Company.legal_name.ilike(prospective_legal_name),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(409, "A company with this legal name already exists")
    prospective_abn = updates.get("abn", company.abn)
    prospective_gst = updates.get("gst_registered", company.gst_registered)
    if prospective_gst and not is_valid_abn(prospective_abn):
        raise HTTPException(422, "A GST-registered business requires a valid 11-digit ABN")
    for field, value in updates.items():
        setattr(company, field, value)
    session.commit()
    session.refresh(company)
    return company


# --------------------------------------------------------------------------- clients


@app.get("/api/v1/clients", response_model=list[ClientOut])
def list_clients(
    response: Response,
    company_id: CompanyId,
    q: str | None = None,
    active_only: bool = True,
    session: Session = Depends(get_db),
):
    get_company(session, company_id)
    query = session.query(Client).filter(Client.company_id == company_id)
    if q:
        query = query.filter(Client.display_name.ilike(f"%{q}%"))
    if active_only:
        query = query.filter(Client.is_active.is_(True))
    total = query.count()
    rows = query.order_by(Client.display_name).limit(LIST_LIMIT).all()
    set_list_metadata(response, total=total, returned=len(rows))
    return rows


@app.post("/api/v1/clients", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate, company_id: CompanyId, session: Session = Depends(get_db)
):
    begin_immediate(session)
    get_company(session, company_id)
    if (
        session.query(Client)
        .filter(
            Client.company_id == company_id,
            Client.display_name.ilike(payload.display_name),
        )
        .first()
    ):
        raise HTTPException(409, "A client with this name already exists")
    client = Client(company_id=company_id, **payload.model_dump())
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


@app.get("/api/v1/clients/{client_id}", response_model=ClientOut)
def read_client(
    client_id: PathId, company_id: CompanyId, session: Session = Depends(get_db)
):
    client = (
        session.query(Client)
        .filter(Client.id == client_id, Client.company_id == company_id)
        .first()
    )
    if client is None:
        raise HTTPException(404, "Client not found")
    return client


@app.patch("/api/v1/clients/{client_id}", response_model=ClientOut)
def update_client(
    client_id: PathId,
    payload: ClientUpdate,
    company_id: CompanyId,
    session: Session = Depends(get_db),
):
    begin_immediate(session)
    client = (
        session.query(Client)
        .filter(Client.id == client_id, Client.company_id == company_id)
        .first()
    )
    if client is None:
        raise HTTPException(404, "Client not found")
    updates = payload.model_dump(exclude_unset=True)
    if "display_name" in updates:
        clash = (
            session.query(Client)
            .filter(
                Client.company_id == company_id,
                Client.display_name.ilike(updates["display_name"]),
                Client.id != client_id,
            )
            .first()
        )
        if clash:
            raise HTTPException(409, "A client with this name already exists")
    for field, value in updates.items():
        setattr(client, field, value)
    session.commit()
    session.refresh(client)
    return client


# --------------------------------------------------------------------------- invoices


@app.get("/api/v1/documents", response_model=list[DocumentOut])
def list_documents(
    response: Response,
    company_id: CompanyId,
    doc_type: str = Query(default="invoice", pattern=r"^(invoice|receipt)$"),
    status: str | None = Query(default=None, pattern=r"^(issued|partially_paid|paid|void)$"),
    q: str | None = None,
    session: Session = Depends(get_db),
):
    get_company(session, company_id)
    query = session.query(Document).filter(
        Document.company_id == company_id,
        Document.doc_type == doc_type,
    )
    if status:
        query = query.filter(Document.status == status)
    if q:
        query = query.filter(
            Document.doc_number.ilike(f"%{q}%") | Document.customer_name.ilike(f"%{q}%")
        )
    total = query.count()
    rows = query.order_by(Document.issue_date.desc(), Document.id.desc()).limit(LIST_LIMIT).all()
    set_list_metadata(response, total=total, returned=len(rows))
    return [serialize(row, session) for row in rows]


@app.post("/api/v1/invoices", response_model=DocumentOut, status_code=201)
def create_invoice(
    payload: InvoiceCreate, company_id: CompanyId, session: Session = Depends(get_db)
):
    begin_immediate(session)
    company = get_company(session, company_id)
    client = (
        session.query(Client)
        .filter(Client.id == payload.client_id, Client.company_id == company_id)
        .first()
    )
    if client is None or not client.is_active:
        raise HTTPException(400, "Select an active client")

    lines = [
        {
            "description": line.description.strip(),
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": money(line.quantity * line.unit_price),
        }
        for line in payload.lines
    ]
    subtotal, gst, total = compute_totals(
        lines, gst_registered=company.gst_registered, gst_inclusive=payload.gst_inclusive
    )

    due = payload.due_date or payload.issue_date + timedelta(days=company.payment_terms_days)
    invoice = Document(
        company_id=company_id,
        doc_type="invoice",
        doc_number=invoice_number(session, company_id, payload.issue_date),
        issue_date=payload.issue_date,
        due_date=due,
        client_id=client.id,
        customer_name=client.display_name,
        customer_abn=client.abn,
        customer_address=client.address,
        customer_email=client.email,
        customer_phone=client.phone,
        subtotal=subtotal,
        gst_amount=gst,
        total=total,
        gst_inclusive=payload.gst_inclusive and company.gst_registered,
        status="issued",
        notes=payload.notes,
    )
    for order, line in enumerate(lines):
        invoice.lines.append(DocumentLine(order_no=order, **line))
    session.add(invoice)
    try:
        session.flush()
        persist_pdf(invoice, company)
        record_event(
            session,
            invoice,
            "created",
            operator=payload.operator or "Not specified",
            reason="Invoice issued",
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Document number already exists") from exc
    session.refresh(invoice)
    return serialize(invoice, session)


@app.get("/api/v1/documents/{document_id}", response_model=DocumentOut)
def read_document(
    document_id: PathId, company_id: CompanyId, session: Session = Depends(get_db)
):
    document = (
        session.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    return serialize(document, session)


@app.put("/api/v1/invoices/{invoice_id}", response_model=DocumentOut)
def update_invoice(
    invoice_id: PathId,
    payload: InvoiceCreate,
    company_id: CompanyId,
    session: Session = Depends(get_db),
):
    begin_immediate(session)
    invoice = (
        session.query(Document)
        .filter(Document.id == invoice_id, Document.company_id == company_id)
        .first()
    )
    if invoice is None or invoice.doc_type != "invoice":
        raise HTTPException(404, "Invoice not found")
    blocked = edit_block_reason(session, invoice)
    if blocked:
        raise HTTPException(409, blocked)

    company = get_company(session, company_id)
    client = (
        session.query(Client)
        .filter(Client.id == payload.client_id, Client.company_id == company_id)
        .first()
    )
    if client is None or not client.is_active:
        raise HTTPException(400, "Select an active client")

    before = snapshot(invoice)
    lines = [
        {
            "description": line.description.strip(),
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount": money(line.quantity * line.unit_price),
        }
        for line in payload.lines
    ]
    subtotal, gst, total = compute_totals(
        lines, gst_registered=company.gst_registered, gst_inclusive=payload.gst_inclusive
    )

    invoice.issue_date = payload.issue_date
    invoice.due_date = payload.due_date or payload.issue_date + timedelta(
        days=company.payment_terms_days
    )
    invoice.client_id = client.id
    invoice.customer_name = client.display_name
    invoice.customer_abn = client.abn
    invoice.customer_address = client.address
    invoice.customer_email = client.email
    invoice.customer_phone = client.phone
    invoice.subtotal = subtotal
    invoice.gst_amount = gst
    invoice.total = total
    invoice.gst_inclusive = payload.gst_inclusive and company.gst_registered
    invoice.notes = payload.notes
    invoice.lines.clear()
    session.flush()
    for order, line in enumerate(lines):
        invoice.lines.append(DocumentLine(order_no=order, **line))
    session.flush()
    persist_pdf(invoice, company)
    record_event(
        session,
        invoice,
        "updated",
        operator=payload.operator or "Not specified",
        reason="Invoice edited",
        before=before,
    )
    session.commit()
    session.refresh(invoice)
    return serialize(invoice, session)


# --------------------------------------------------------------------------- receipts


@app.post("/api/v1/invoices/{invoice_id}/receipts", response_model=DocumentOut, status_code=201)
def create_receipt(
    invoice_id: PathId,
    payload: ReceiptCreate,
    company_id: CompanyId,
    session: Session = Depends(get_db),
):
    """Record a payment against an invoice. Defaults to the full outstanding amount."""
    begin_immediate(session)
    invoice = (
        session.query(Document)
        .filter(Document.id == invoice_id, Document.company_id == company_id)
        .first()
    )
    if invoice is None or invoice.doc_type != "invoice":
        raise HTTPException(404, "Invoice not found")
    if invoice.status == "void":
        raise HTTPException(409, "Cannot receipt a void invoice")

    company = get_company(session, company_id)
    received = received_total(session, invoice)
    outstanding = money(max(Decimal(invoice.total) - received, Decimal("0")))
    if outstanding <= 0:
        raise HTTPException(409, "This invoice is already paid in full")

    amount = outstanding if payload.amount is None else money(payload.amount)
    if amount > outstanding:
        raise HTTPException(
            400, f"Receipt amount exceeds the outstanding balance of {outstanding}"
        )

    paid_date = payload.paid_date or date.today()
    if paid_date < invoice.issue_date:
        raise HTTPException(400, "Payment date cannot be before the invoice date")

    # Split the payment's GST in the same proportion the invoice carries, with
    # the final receipt absorbing the rounding remainder so the parts always
    # add back up to the invoice exactly.
    if amount == outstanding:
        net = money(
            Decimal(invoice.subtotal)
            - sum((Decimal(r.subtotal) for r in active_receipts(session, invoice)), Decimal("0"))
        )
        gst = money(amount - net)
    elif Decimal(invoice.total) > 0:
        net = money(Decimal(invoice.subtotal) * amount / Decimal(invoice.total))
        gst = money(amount - net)
    else:  # pragma: no cover - a zero-total invoice cannot be created
        net = gst = Decimal("0.00")

    receipt = Document(
        company_id=company_id,
        doc_type="receipt",
        doc_number=receipt_number(session, invoice),
        issue_date=paid_date,
        client_id=invoice.client_id,
        invoice_id=invoice.id,
        customer_name=invoice.customer_name,
        customer_abn=invoice.customer_abn,
        customer_address=invoice.customer_address,
        customer_email=invoice.customer_email,
        customer_phone=invoice.customer_phone,
        subtotal=net,
        gst_amount=gst,
        total=amount,
        gst_inclusive=invoice.gst_inclusive,
        status="issued",
        paid_date=paid_date,
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    receipt.lines.append(
        DocumentLine(
            order_no=0,
            description=f"Payment received for {invoice.doc_number}",
            quantity=Decimal("1"),
            unit_price=net,
            amount=net,
        )
    )
    session.add(receipt)
    try:
        session.flush()
        persist_pdf(receipt, company, source_document_number=invoice.doc_number)
        record_event(
            session,
            receipt,
            "created",
            operator=payload.operator,
            reason=f"Payment recorded against {invoice.doc_number}",
        )
        recompute_invoice_status(session, invoice)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Receipt number conflict; retry the operation") from exc
    session.refresh(receipt)
    return serialize(receipt, session)


# --------------------------------------------------------------------------- void / restore


@app.delete("/api/v1/documents/{document_id}", status_code=204)
def void_document(
    document_id: PathId,
    payload: AuditAction,
    company_id: CompanyId,
    session: Session = Depends(get_db),
):
    begin_immediate(session)
    document = (
        session.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    if document.status == "void":
        raise HTTPException(409, "The document is already void")

    if document.doc_type == "invoice":
        # An invoice cannot be void while money is still recorded against it,
        # so its receipts are voided in the same transaction.
        for receipt in active_receipts(session, document):
            before = snapshot(receipt)
            receipt.status = "void"
            record_event(
                session,
                receipt,
                "voided",
                operator=payload.operator,
                reason=f"Cascaded from invoice: {payload.reason}",
                before=before,
            )
    before = snapshot(document)
    document.status = "void"
    record_event(
        session, document, "voided", operator=payload.operator, reason=payload.reason, before=before
    )
    if document.doc_type == "receipt" and document.invoice_id:
        invoice = (
            session.query(Document)
            .filter(
                Document.id == document.invoice_id,
                Document.company_id == company_id,
            )
            .first()
        )
        if invoice is not None:
            session.flush()
            recompute_invoice_status(session, invoice)
    session.commit()


@app.post("/api/v1/documents/{document_id}/restore", response_model=DocumentOut)
def restore_document(
    document_id: PathId,
    payload: AuditAction,
    company_id: CompanyId,
    session: Session = Depends(get_db),
):
    begin_immediate(session)
    document = (
        session.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    if document.status != "void":
        raise HTTPException(409, "Only a void document can be restored")

    if document.doc_type == "receipt":
        invoice = (
            session.query(Document)
            .filter(
                Document.id == document.invoice_id,
                Document.company_id == company_id,
            )
            .first()
        )
        if invoice is None or invoice.status == "void":
            raise HTTPException(409, "Restore the invoice first")
        received = received_total(session, invoice)
        if money(received + Decimal(document.total)) > money(invoice.total):
            raise HTTPException(409, "Restoring this receipt would overpay the invoice")

    before = snapshot(document)
    document.status = "issued"
    record_event(
        session,
        document,
        "restored",
        operator=payload.operator,
        reason=payload.reason,
        before=before,
    )
    session.flush()
    if document.doc_type == "invoice":
        recompute_invoice_status(session, document)
    else:
        invoice = (
            session.query(Document)
            .filter(
                Document.id == document.invoice_id,
                Document.company_id == company_id,
            )
            .first()
        )
        if invoice is not None:
            recompute_invoice_status(session, invoice)
    session.commit()
    session.refresh(document)
    return serialize(document, session)


# --------------------------------------------------------------------------- PDF & audit


@app.get("/api/v1/documents/{document_id}/pdf")
def document_pdf(
    document_id: PathId,
    company_id: CompanyId,
    inline: bool = True,
    session: Session = Depends(get_db),
):
    document = (
        session.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    if document.status == "void":
        raise HTTPException(409, "Void documents cannot be rendered or downloaded")
    if not document.pdf_content:
        raise HTTPException(409, "The stored PDF is missing")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=bytes(document.pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{document.doc_number}.pdf"'
        },
    )


@app.get("/api/v1/documents/{document_id}/audit", response_model=list[EventOut])
def document_audit(
    document_id: PathId, company_id: CompanyId, session: Session = Depends(get_db)
):
    document = (
        session.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    return (
        session.query(DocumentEvent)
        .filter(DocumentEvent.document_id == document.id)
        .order_by(DocumentEvent.id)
        .all()
    )


# --------------------------------------------------------------------------- bundled UI

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSET_DIR = STATIC_DIR / "assets"
if ASSET_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def bundled_frontend(full_path: str):
    # Registered last so an unknown /api path 404s as JSON instead of being
    # answered with the SPA shell.
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(404, "API route not found")
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse(
            "<h1>Interface is not built</h1><p>Run build.ps1 (Windows) or build.sh.</p>",
            status_code=503,
        )
    candidate = (STATIC_DIR / full_path).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        raise HTTPException(404, "File not found") from None
    return FileResponse(candidate if candidate.is_file() else index)
