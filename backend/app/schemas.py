from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# Exact cents, with a generous business ceiling (just under one trillion AUD).
MONEY_MAX = Decimal("999999999999.99")
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _mark_utc(value: datetime) -> datetime:
    """Stamp UTC on the naive timestamps SQLite returns.

    SQLite has no timezone type, so ``server_default=func.now()`` stores a naive
    UTC instant. Serialising it without an offset makes every client parse it as
    local time, which shifts history onto the wrong day.
    """
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UtcDateTime = Annotated[datetime, AfterValidator(_mark_utc)]


def _blank_to_none(value):
    if isinstance(value, str):
        return value.strip() or None
    return value


def is_valid_abn(value: str | None) -> bool:
    if value is None or len(value) != 11 or not value.isdigit():
        return False
    digits = [int(digit) for digit in value]
    digits[0] -= 1
    return sum(d * w for d, w in zip(digits, ABN_WEIGHTS, strict=True)) % 89 == 0


def validate_abn(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(value.split())
    if not is_valid_abn(cleaned):
        raise ValueError("ABN must be 11 digits and pass the Australian checksum")
    return cleaned


def validate_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not _EMAIL_RE.fullmatch(cleaned):
        raise ValueError("Enter a valid email address, for example name@example.com")
    return cleaned


# --------------------------------------------------------------------------- company


class CompanyCreate(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    trading_name: str | None = Field(default=None, max_length=200)

    @field_validator("legal_name")
    @classmethod
    def clean_legal_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Legal name is required")
        return cleaned

    @field_validator("trading_name", mode="before")
    @classmethod
    def clean_trading_name(cls, value):
        return _blank_to_none(value)


class CompanyUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    trading_name: str | None = Field(default=None, max_length=200)
    abn: str | None = Field(default=None, max_length=20)
    gst_registered: bool | None = None
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    suburb: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=20)
    postcode: str | None = Field(default=None, max_length=10)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    bank_account_name: str | None = Field(default=None, max_length=200)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_bsb: str | None = Field(default=None, max_length=10)
    bank_account_number: str | None = Field(default=None, max_length=30)
    bank_swift: str | None = Field(default=None, max_length=20)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)

    @field_validator("trading_name", "abn", "email", "postcode", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        return _blank_to_none(value)

    @field_validator("legal_name", mode="before")
    @classmethod
    def clean_legal_name(cls, value):
        cleaned = _blank_to_none(value)
        if cleaned is None:
            raise ValueError("Legal name is required")
        return cleaned

    @field_validator("abn")
    @classmethod
    def check_abn(cls, value):
        return validate_abn(value)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return validate_email(value)

    @field_validator("postcode")
    @classmethod
    def check_postcode(cls, value):
        if value is None:
            return None
        cleaned = value.strip()
        if not (len(cleaned) == 4 and cleaned.isdigit()):
            raise ValueError("Postcode must be 4 digits")
        return cleaned


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_name: str
    trading_name: str | None
    abn: str | None
    gst_registered: bool
    address_line1: str | None
    address_line2: str | None
    suburb: str | None
    state: str | None
    postcode: str | None
    phone: str | None
    email: str | None
    bank_account_name: str | None
    bank_name: str | None
    bank_bsb: str | None
    bank_account_number: str | None
    bank_swift: str | None
    payment_terms_days: int
    updated_at: UtcDateTime


# --------------------------------------------------------------------------- clients


class ClientCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    abn: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Client name cannot be blank")
        return cleaned

    @field_validator("abn", "email", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        return _blank_to_none(value)

    @field_validator("abn")
    @classmethod
    def check_abn(cls, value):
        return validate_abn(value)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return validate_email(value)


class ClientUpdate(ClientCreate):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    display_name: str
    abn: str | None
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    is_active: bool
    created_at: UtcDateTime


# --------------------------------------------------------------------------- invoices


class InvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(
        default=Decimal("1"), gt=0, le=Decimal("999999.9999"), max_digits=12, decimal_places=4
    )
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, le=MONEY_MAX, max_digits=16, decimal_places=2
    )
    gst_treatment: Literal["taxable", "gst_free"] = "taxable"


class InvoiceCreate(BaseModel):
    client_id: int = Field(ge=1)
    issue_date: date
    due_date: date | None = None
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)
    gst_inclusive: bool = False
    notes: str | None = Field(default=None, max_length=1000)
    operator: str | None = Field(default=None, max_length=200)

    @field_validator("operator", mode="before")
    @classmethod
    def strip_optional_operator(cls, value):
        return _blank_to_none(value)

    @model_validator(mode="after")
    def check_dates(self):
        if self.issue_date > date.today():
            raise ValueError("Invoice date cannot be in the future")
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError("Due date cannot be before the invoice date")
        return self


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    gst_treatment: Literal["taxable", "gst_free"]


class ReceiptSummary(BaseModel):
    id: int
    doc_number: str
    status: str
    total: Decimal
    paid_date: date | None
    payment_method: str | None


class DocumentOut(BaseModel):
    id: int
    company_id: int
    doc_type: str
    doc_number: str
    issue_date: date
    due_date: date | None
    client_id: int | None
    invoice_id: int | None
    customer_name: str
    customer_abn: str | None
    customer_address: str | None
    customer_email: str | None
    customer_phone: str | None
    currency: str
    subtotal: Decimal
    gst_amount: Decimal
    total: Decimal
    gst_inclusive: bool
    status: str
    paid_date: date | None
    payment_method: str | None
    notes: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    lines: list[LineOut]
    # Invoice-only rollups.
    receipts: list[ReceiptSummary] = Field(default_factory=list)
    amount_received: Decimal | None = None
    amount_outstanding: Decimal | None = None
    can_edit: bool = False
    edit_block_reason: str | None = None


# --------------------------------------------------------------------------- receipts


class ReceiptCreate(BaseModel):
    amount: Decimal | None = Field(
        default=None, gt=0, le=MONEY_MAX, max_digits=16, decimal_places=2
    )
    paid_date: date | None = None
    payment_method: str = Field(default="Bank transfer", min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    operator: str = Field(min_length=1, max_length=200)

    @field_validator("operator", "payment_method")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def check_paid_date(self):
        if self.paid_date is not None and self.paid_date > date.today():
            raise ValueError("Payment date cannot be in the future")
        return self


# --------------------------------------------------------------------------- audit


class AuditAction(BaseModel):
    operator: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("operator")
    @classmethod
    def strip_operator(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Operator cannot be blank")
        return cleaned

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Reason must contain at least 3 non-space characters")
        return cleaned


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    action: str
    operator: str
    reason: str
    snapshot: dict | None
    occurred_at: UtcDateTime
