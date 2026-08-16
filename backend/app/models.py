from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


MONEY = Numeric(16, 2)


class Base(DeclarativeBase):
    pass


class Company(Base):
    """A business issuing its own isolated clients, documents and numbering."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False, default="My Company")
    trading_name: Mapped[str | None] = mapped_column(String(200))
    abn: Mapped[str | None] = mapped_column(String(20))
    gst_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    suburb: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(20))
    postcode: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    bank_account_name: Mapped[str | None] = mapped_column(String(200))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_bsb: Mapped[str | None] = mapped_column(String(10))
    bank_account_number: Mapped[str | None] = mapped_column(String(30))
    bank_swift: Mapped[str | None] = mapped_column(String(20))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    abn: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    company: Mapped[Company] = relationship()


class DocumentCounter(Base):
    """An independent invoice serial for each company and calendar year."""

    __tablename__ = "company_document_counters"

    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_serial: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Document(Base):
    """An invoice, or a receipt recording a payment against one."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "doc_type", "doc_number", name="uq_company_document_type_number"
        ),
        Index("ix_documents_invoice", "invoice_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # invoice|receipt
    doc_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date | None] = mapped_column(Date)

    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    # A receipt points at the invoice it pays. Null on an invoice.
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT")
    )

    # Customer details are snapshotted at issue time: editing a client record
    # must never rewrite a document that has already been sent.
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_abn: Mapped[str | None] = mapped_column(String(20))
    customer_address: Mapped[str | None] = mapped_column(String(500))
    customer_email: Mapped[str | None] = mapped_column(String(200))
    customer_phone: Mapped[str | None] = mapped_column(String(50))

    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    gst_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    gst_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # invoice: issued | partially_paid | paid | void ; receipt: issued | void
    status: Mapped[str] = mapped_column(String(20), default="issued", nullable=False, index=True)
    paid_date: Mapped[date | None] = mapped_column(Date)
    payment_method: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(1000))

    # The issued PDF, committed in the same transaction as the row it belongs
    # to. Deferred so lists and detail reads never pull the blob.
    pdf_content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped[Company] = relationship()
    client: Mapped[Client | None] = relationship()
    lines: Mapped[list["DocumentLine"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentLine.order_no"
    )
    events: Mapped[list["DocumentEvent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentEvent.id"
    )


class DocumentLine(Base):
    __tablename__ = "document_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    document: Mapped[Document] = relationship(back_populates="lines")


class DocumentEvent(Base):
    __tablename__ = "document_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="events")
