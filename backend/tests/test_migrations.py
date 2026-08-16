import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from app.db import (
    MigrationDataError,
    _migrate_company_names,
    _migrate_company_scope,
    _migrate_database,
)
from app.models import Client, Company, DocumentCounter


LEGACY_COMPANY_SQL = """
CREATE TABLE company (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(200),
    abn VARCHAR(20),
    gst_registered BOOLEAN NOT NULL,
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(200),
    suburb VARCHAR(100),
    state VARCHAR(20),
    postcode VARCHAR(10),
    phone VARCHAR(50),
    email VARCHAR(200),
    bank_account_name VARCHAR(200),
    bank_name VARCHAR(100),
    bank_bsb VARCHAR(10),
    bank_account_number VARCHAR(30),
    bank_swift VARCHAR(20),
    payment_terms_days INTEGER NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def test_legacy_company_names_are_migrated_without_losing_the_issuer(tmp_path):
    legacy_engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(LEGACY_COMPANY_SQL)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, name, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES (1, 'Example Trading', 'Example Legal Pty Ltd', 0, 14, CURRENT_TIMESTAMP)
            """
        )
        _migrate_company_names(connection)

        columns = {column["name"]: column for column in inspect(connection).get_columns("company")}
        row = connection.exec_driver_sql(
            "SELECT legal_name, trading_name FROM company WHERE id = 1"
        ).one()

    assert "name" not in columns
    assert columns["legal_name"]["nullable"] is False
    assert row == ("Example Legal Pty Ltd", "Example Trading")


def test_legacy_name_becomes_legal_name_when_no_legal_name_was_saved(tmp_path):
    legacy_engine = create_engine(f"sqlite:///{(tmp_path / 'legacy-fallback.db').as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(LEGACY_COMPANY_SQL)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, name, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES (1, 'Only Existing Name', NULL, 0, 14, CURRENT_TIMESTAMP)
            """
        )
        _migrate_company_names(connection)
        row = connection.exec_driver_sql(
            "SELECT legal_name, trading_name FROM company WHERE id = 1"
        ).one()

    assert row == ("Only Existing Name", None)


def test_single_company_clients_documents_and_counters_gain_company_scope(tmp_path):
    legacy_engine = create_engine(f"sqlite:///{(tmp_path / 'legacy-scope.db').as_posix()}")
    with legacy_engine.begin() as connection:
        Company.__table__.create(connection)
        DocumentCounter.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES (1, 'Legacy Pty Ltd', 0, 14, CURRENT_TIMESTAMP)
            """
        )
        connection.exec_driver_sql(
            "CREATE TABLE clients (id INTEGER PRIMARY KEY, display_name VARCHAR(200) NOT NULL)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                doc_type VARCHAR(10) NOT NULL,
                doc_number VARCHAR(40) NOT NULL,
                invoice_id INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE TABLE document_counters (year INTEGER PRIMARY KEY, last_serial INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO clients VALUES (10, 'Legacy Client')")
        connection.exec_driver_sql(
            "INSERT INTO documents VALUES (20, 'invoice', 'INV-2026-0007', NULL)"
        )
        connection.exec_driver_sql("INSERT INTO document_counters VALUES (2026, 7)")

        _migrate_company_scope(connection)
        _migrate_company_scope(connection)

        client_company = connection.exec_driver_sql(
            "SELECT company_id FROM clients WHERE id = 10"
        ).scalar_one()
        document_company = connection.exec_driver_sql(
            "SELECT company_id FROM documents WHERE id = 20"
        ).scalar_one()
        counter = connection.exec_driver_sql(
            """
            SELECT company_id, year, last_serial
            FROM company_document_counters
            WHERE company_id = 1 AND year = 2026
            """
        ).one()
        migrated_inspector = inspect(connection)
        migrated_tables = set(migrated_inspector.get_table_names())
        unique_columns = {
            tuple(constraint["column_names"])
            for constraint in migrated_inspector.get_unique_constraints("documents")
        }
        unique_columns.update(
            tuple(index["column_names"])
            for index in migrated_inspector.get_indexes("documents")
            if index.get("unique")
        )

    assert client_company == 1
    assert document_company == 1
    assert counter == (1, 2026, 7)
    assert "document_counters" not in migrated_tables
    assert ("company_id", "doc_type", "doc_number") in unique_columns

    with pytest.raises(IntegrityError, match="clients.company_id is required"):
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO clients (id, display_name, company_id) VALUES (11, 'Unscoped', NULL)"
            )

    with pytest.raises(IntegrityError, match="documents.company_id is required"):
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO documents (id, doc_type, doc_number, company_id)
                VALUES (21, 'invoice', 'INV-2026-0008', NULL)
                """
            )

    with pytest.raises(IntegrityError):
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO documents (id, doc_type, doc_number, company_id)
                VALUES (22, 'invoice', 'INV-2026-0007', 1)
                """
            )


def test_partial_company_name_migration_preserves_existing_foreign_keys(tmp_path):
    partial_engine = create_engine(f"sqlite:///{(tmp_path / 'partial-company.db').as_posix()}")
    with partial_engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.exec_driver_sql(LEGACY_COMPANY_SQL)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, name, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES (1, 'Legacy Trading', 'Legacy Pty Ltd', 0, 14, CURRENT_TIMESTAMP)
            """
        )
        Client.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO clients (id, company_id, display_name, is_active)
            VALUES (10, 1, 'Existing Client', 1)
            """
        )

    with partial_engine.connect() as connection:
        _migrate_database(connection)
        _migrate_database(connection)
        foreign_keys = inspect(connection).get_foreign_keys("clients")
        client_company = connection.exec_driver_sql(
            "SELECT company_id FROM clients WHERE id = 10"
        ).scalar_one()
        company_names = connection.exec_driver_sql(
            "SELECT legal_name, trading_name FROM company WHERE id = 1"
        ).one()

    assert client_company == 1
    assert company_names == ("Legacy Pty Ltd", "Legacy Trading")
    assert any(
        foreign_key["constrained_columns"] == ["company_id"]
        and foreign_key["referred_table"] == "company"
        for foreign_key in foreign_keys
    )


def test_partial_receipt_scope_is_repaired_from_its_invoice_and_guarded(tmp_path):
    partial_engine = create_engine(f"sqlite:///{(tmp_path / 'partial-receipt.db').as_posix()}")
    with partial_engine.begin() as connection:
        Company.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES
                (1, 'First Pty Ltd', 0, 14, CURRENT_TIMESTAMP),
                (2, 'Second Pty Ltd', 0, 14, CURRENT_TIMESTAMP)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                company_id INTEGER REFERENCES company(id),
                doc_type VARCHAR(10) NOT NULL,
                doc_number VARCHAR(40) NOT NULL,
                invoice_id INTEGER REFERENCES documents(id)
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO documents VALUES (20, 2, 'invoice', 'INV-C2-2026-0001', NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO documents VALUES (21, 1, 'receipt', 'RCT-C2-2026-0001-1', 20)"
        )
        _migrate_company_scope(connection)
        _migrate_company_scope(connection)
        receipt_company = connection.exec_driver_sql(
            "SELECT company_id FROM documents WHERE id = 21"
        ).scalar_one()

    assert receipt_company == 2
    with pytest.raises(IntegrityError, match="receipt and invoice must belong"):
        with partial_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO documents (id, company_id, doc_type, doc_number, invoice_id)
                VALUES (22, 1, 'receipt', 'RCT-WRONG-1', 20)
                """
            )


def test_duplicate_document_numbers_report_a_repair_error_without_renaming(tmp_path):
    damaged_engine = create_engine(f"sqlite:///{(tmp_path / 'duplicates.db').as_posix()}")
    with damaged_engine.begin() as connection:
        Company.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO company (
                id, legal_name, gst_registered, payment_terms_days, updated_at
            ) VALUES (1, 'Damaged Pty Ltd', 0, 14, CURRENT_TIMESTAMP)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                company_id INTEGER REFERENCES company(id),
                doc_type VARCHAR(10) NOT NULL,
                doc_number VARCHAR(40) NOT NULL,
                invoice_id INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO documents VALUES
                (30, 1, 'invoice', 'INV-2026-0001', NULL),
                (31, 1, 'invoice', 'INV-2026-0001', NULL)
            """
        )

    with pytest.raises(MigrationDataError, match="duplicate document numbers"):
        with damaged_engine.begin() as connection:
            _migrate_company_scope(connection)

    with damaged_engine.connect() as connection:
        numbers = connection.exec_driver_sql(
            "SELECT id, doc_number FROM documents ORDER BY id"
        ).all()
    assert numbers == [(30, "INV-2026-0001"), (31, "INV-2026-0001")]
