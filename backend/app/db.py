from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base, Company


class DatabaseBusyError(RuntimeError):
    """The write lock could not be taken in time.

    Contention is a normal, retryable condition; the API turns this into a 503
    so it never surfaces as an internal error.
    """


class MigrationDataError(RuntimeError):
    """The selected database needs an explicit repair before it can be opened."""


# Upper bound for the in-process write lock. SQLite's own busy_timeout applies
# afterwards, once BEGIN IMMEDIATE is issued.
_WRITE_LOCK_TIMEOUT_SECONDS = 15.0

settings.data_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_path.as_posix()}",
    future=True,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configure_sqlite(connection, _record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# FastAPI may finalise a sync dependency on a different worker thread, so this
# must be a plain Lock (an RLock can only be released by its owner).
_write_lock = Lock()


def _enforce_required_company_id(connection: Connection, table_name: str) -> None:
    """Enforce the ORM's non-null company scope on SQLite tables altered in place.

    SQLite cannot add a NOT NULL column to a populated table without rebuilding
    it. Rebuilding clients/documents would also rewrite several foreign-key
    relationships, so legacy databases use equivalent insert/update guards.
    """
    for operation in ("INSERT", "UPDATE OF company_id"):
        suffix = "insert" if operation == "INSERT" else "update"
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS {table_name}_company_id_required_{suffix}
            BEFORE {operation} ON {table_name}
            WHEN NEW.company_id IS NULL
            BEGIN
                SELECT RAISE(ABORT, '{table_name}.company_id is required');
            END
            """
        )


def _enforce_receipt_company_scope(connection: Connection) -> None:
    """Prevent a receipt from being attached across company boundaries."""
    for operation in ("INSERT", "UPDATE OF company_id, invoice_id"):
        suffix = "insert" if operation == "INSERT" else "update"
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS documents_receipt_company_{suffix}
            BEFORE {operation} ON documents
            WHEN NEW.invoice_id IS NOT NULL
             AND NOT EXISTS (
                SELECT 1
                FROM documents AS invoice
                WHERE invoice.id = NEW.invoice_id
                  AND invoice.doc_type = 'invoice'
                  AND invoice.company_id = NEW.company_id
             )
            BEGIN
                SELECT RAISE(ABORT, 'receipt and invoice must belong to the same company');
            END
            """
        )


def _duplicate_document_numbers(connection: Connection) -> list[tuple]:
    return list(
        connection.exec_driver_sql(
            """
            SELECT company_id, doc_type, doc_number, COUNT(*), GROUP_CONCAT(id)
            FROM documents
            GROUP BY company_id, doc_type, doc_number
            HAVING COUNT(*) > 1
            ORDER BY company_id, doc_type, doc_number
            LIMIT 10
            """
        ).all()
    )


def _migrate_company_names(connection: Connection) -> None:
    """Replace the legacy required ``name`` column with explicit company names.

    The old UI described ``name`` as a trading name while SQLite required it.
    Rebuilding this small, unreferenced table is the only reliable way to drop
    that NOT NULL constraint on existing SQLite databases.
    """
    inspector = inspect(connection)
    if "company" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("company")}
    if "trading_name" in columns or "name" not in columns:
        return

    connection.exec_driver_sql("ALTER TABLE company RENAME TO company_legacy_names")
    Company.__table__.create(connection)
    connection.exec_driver_sql(
        """
        INSERT INTO company (
            id, legal_name, trading_name, abn, gst_registered,
            address_line1, address_line2, suburb, state, postcode,
            phone, email, bank_account_name, bank_name, bank_bsb,
            bank_account_number, bank_swift, payment_terms_days, updated_at
        )
        SELECT
            id,
            COALESCE(NULLIF(TRIM(legal_name), ''), NULLIF(TRIM(name), ''), 'My Company'),
            CASE
                WHEN NULLIF(TRIM(legal_name), '') IS NOT NULL
                 AND NULLIF(TRIM(name), '') IS NOT NULL
                 AND LOWER(TRIM(legal_name)) != LOWER(TRIM(name))
                THEN TRIM(name)
                ELSE NULL
            END,
            abn, gst_registered,
            address_line1, address_line2, suburb, state, postcode,
            phone, email, bank_account_name, bank_name, bank_bsb,
            bank_account_number, bank_swift, payment_terms_days, updated_at
        FROM company_legacy_names
        """
    )
    connection.exec_driver_sql("DROP TABLE company_legacy_names")


def _migrate_company_scope(connection: Connection) -> None:
    """Attach legacy clients/documents/numbering to the original company."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    if "clients" in tables:
        client_columns = {column["name"] for column in inspector.get_columns("clients")}
        if "company_id" not in client_columns:
            connection.exec_driver_sql(
                "ALTER TABLE clients ADD COLUMN company_id INTEGER REFERENCES company(id)"
            )
        connection.exec_driver_sql(
            "UPDATE clients SET company_id = COALESCE((SELECT MIN(id) FROM company), 1) "
            "WHERE company_id IS NULL"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_clients_company_id ON clients (company_id)"
        )
        _enforce_required_company_id(connection, "clients")

    if "documents" in tables:
        document_columns = {column["name"] for column in inspector.get_columns("documents")}
        if "company_id" not in document_columns:
            connection.exec_driver_sql(
                "ALTER TABLE documents ADD COLUMN company_id INTEGER REFERENCES company(id)"
            )
        # Establish invoice ownership first, then make every receipt inherit its
        # parent invoice's company. This also repairs an interrupted earlier
        # migration that assigned the receipt to the wrong company.
        connection.exec_driver_sql(
            """
            UPDATE documents
            SET company_id = COALESCE((SELECT MIN(id) FROM company), 1)
            WHERE company_id IS NULL
              AND (doc_type != 'receipt' OR invoice_id IS NULL)
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE documents
            SET company_id = (
                SELECT invoice.company_id
                FROM documents AS invoice
                WHERE invoice.id = documents.invoice_id
                  AND invoice.doc_type = 'invoice'
            )
            WHERE doc_type = 'receipt'
              AND invoice_id IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM documents AS invoice
                WHERE invoice.id = documents.invoice_id
                  AND invoice.doc_type = 'invoice'
                  AND invoice.company_id IS NOT NULL
              )
              AND company_id IS NOT (
                SELECT invoice.company_id
                FROM documents AS invoice
                WHERE invoice.id = documents.invoice_id
              )
            """
        )
        orphan_receipts = connection.exec_driver_sql(
            """
            SELECT id, invoice_id
            FROM documents AS receipt
            WHERE receipt.doc_type = 'receipt'
              AND receipt.invoice_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM documents AS invoice
                WHERE invoice.id = receipt.invoice_id
                  AND invoice.doc_type = 'invoice'
              )
            ORDER BY id
            LIMIT 10
            """
        ).all()
        if orphan_receipts:
            details = ", ".join(
                f"receipt {receipt_id} -> invoice {invoice_id}"
                for receipt_id, invoice_id in orphan_receipts
            )
            raise MigrationDataError(
                "The database contains receipts without a valid invoice: "
                f"{details}. Restore a known-good backup or request a data repair."
            )
        connection.exec_driver_sql(
            "UPDATE documents SET company_id = COALESCE((SELECT MIN(id) FROM company), 1) "
            "WHERE company_id IS NULL"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_documents_company_id ON documents (company_id)"
        )
        unique_columns = {
            tuple(constraint["column_names"])
            for constraint in inspect(connection).get_unique_constraints("documents")
        }
        unique_columns.update(
            tuple(index["column_names"])
            for index in inspect(connection).get_indexes("documents")
            if index.get("unique")
        )
        duplicate_numbers = _duplicate_document_numbers(connection)
        if duplicate_numbers:
            details = "; ".join(
                f"company {company_id}, {doc_type} {doc_number}, rows {row_ids}"
                for company_id, doc_type, doc_number, _count, row_ids in duplicate_numbers
            )
            raise MigrationDataError(
                "The database contains duplicate document numbers: "
                f"{details}. No document numbers were changed; restore a known-good backup "
                "or request a data repair."
            )
        if ("company_id", "doc_type", "doc_number") not in unique_columns:
            conflicting_index = next(
                (
                    index
                    for index in inspect(connection).get_indexes("documents")
                    if index["name"] == "uq_company_document_type_number"
                ),
                None,
            )
            if conflicting_index is not None:
                raise MigrationDataError(
                    "The document-number index has an unexpected definition. "
                    "Restore a known-good backup or request a data repair."
                )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_company_document_type_number "
                "ON documents (company_id, doc_type, doc_number)"
            )
        _enforce_required_company_id(connection, "documents")
        _enforce_receipt_company_scope(connection)

    if "document_counters" in tables:
        connection.exec_driver_sql(
            """
            INSERT OR IGNORE INTO company_document_counters (company_id, year, last_serial)
            SELECT COALESCE((SELECT MIN(id) FROM company), 1), year, last_serial
            FROM document_counters
            """
        )
        connection.exec_driver_sql("DROP TABLE document_counters")


def _migrate_database(connection: Connection) -> None:
    """Run schema changes atomically while preserving partial-schema foreign keys."""
    connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    connection.commit()
    try:
        # An explicit BEGIN makes SQLite DDL transactional even when the Python
        # driver is using its legacy transaction-control mode.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        _migrate_company_names(connection)
        Base.metadata.create_all(connection)
        _migrate_company_scope(connection)
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            details = "; ".join(
                f"table {table}, row {row_id}, parent {parent}"
                for table, row_id, parent, _foreign_key_id in violations[:10]
            )
            raise MigrationDataError(
                "The database contains broken relationships: "
                f"{details}. Restore a known-good backup or request a data repair."
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.commit()


def init_db() -> None:
    with engine.connect() as connection:
        _migrate_database(connection)
    with SessionLocal() as session:
        if session.get(Company, 1) is None:
            session.add(Company(id=1))
            session.commit()


def dispose_engine() -> None:
    engine.dispose()


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        held = session.info.pop("write_lock_held", False)
        try:
            session.rollback()
            session.close()
        finally:
            if held:
                _write_lock.release()


def begin_immediate(session: Session) -> None:
    """Take the write lock and open a real write transaction.

    Every mutating endpoint calls this before reading the state it guards on,
    so a check and the write that depends on it cannot be interleaved.
    """
    if session.in_transaction():
        return
    if not session.info.get("write_lock_held"):
        if not _write_lock.acquire(timeout=_WRITE_LOCK_TIMEOUT_SECONDS):
            raise DatabaseBusyError("Another change is still in progress")
        session.info["write_lock_held"] = True
    try:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except Exception as exc:
        session.info.pop("write_lock_held", None)
        _write_lock.release()
        if isinstance(exc, OperationalError) and "locked" in str(exc).lower():
            raise DatabaseBusyError("The database is locked by another writer") from exc
        raise
