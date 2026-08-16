"""Render outgoing documents (TAX INVOICE / RECEIPT) to PDF.

Pure reportlab; no fonts loaded from the network, no external HTTP. The visual
style matches the user's existing Word template:
  * top-left: company name (deep blue, bold) + address/phone block
  * top-right: large document-type wordmark (deep blue)
  * blue header bar "BILL TO" on the left, document number / dates on the right
  * line items table with blue header row
  * subtotal row + big blue TOTAL band
  * bottom: bank or payment details table
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .pdf_fonts import (
    FONT_BASE,
    FONT_BOLD,
    FONT_OBLIQUE,
    draw_unicode_string,
    string_width,
)


# Restrained professional palette: navy for authority, cool greys for structure,
# and a warm hairline accent that adds polish without looking decorative.
BRAND_BLUE = HexColor("#173B57")
HEADER_BG = HexColor("#173B57")
TEXT_DARK = HexColor("#24313C")
TEXT_MUTED = HexColor("#667784")
ROW_DIVIDER = HexColor("#D7E0E7")
LIGHT_GREY = HexColor("#F7F9FB")
TABLE_HEADER_BG = HexColor("#EAF0F4")
ACCENT = HexColor("#B88A4A")


DOC_TITLE = {
    "invoice": "INVOICE",
    "receipt": "RECEIPT",
}


def _document_title(doc_type: str, is_gst_registered: bool) -> str:
    if doc_type == "invoice" and is_gst_registered:
        return "TAX INVOICE"
    return DOC_TITLE.get(doc_type, doc_type.upper())


def _fmt_money(v: Decimal | float | int, currency: str = "AUD") -> str:
    del currency
    n = Decimal(str(v)).quantize(Decimal("0.01"))
    return f"${n:,.2f}"


def _fmt_date(d: date | str | None) -> str:
    if d is None:
        return ""
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def _draw_text(c, x, y, text, *, font=FONT_BASE, size=10, color=TEXT_DARK):
    c.setFillColor(color)
    draw_unicode_string(c, x, y, text, font=font, size=size)


def _draw_right(c, x, y, text, *, font=FONT_BASE, size=10, color=TEXT_DARK):
    c.setFillColor(color)
    draw_unicode_string(c, x, y, text, font=font, size=size, align="right")


def _draw_center(c, x, y, text, *, font=FONT_BASE, size=10, color=TEXT_DARK):
    c.setFillColor(color)
    draw_unicode_string(c, x, y, text, font=font, size=size, align="center")


def _draw_bar(c, x, y, w, h, fill: Color):
    c.setFillColor(fill)
    c.rect(x, y, w, h, stroke=0, fill=1)


def _draw_box_with_header(
    c,
    x,
    y,
    w,
    header_h,
    label: str,
    body_h: float,
):
    """Header bar + bordered body box. Returns the inner top y for the body."""
    _draw_bar(c, x, y - header_h, w, header_h, HEADER_BG)
    _draw_text(c, x + 6, y - header_h + 4, label.upper(), font=FONT_BOLD, size=10, color=white)
    c.setStrokeColor(ROW_DIVIDER)
    c.setLineWidth(0.65)
    c.setFillColor(LIGHT_GREY)
    c.rect(x, y - header_h - body_h, w, body_h, stroke=1, fill=1)
    return y - header_h - 6  # baseline for first body line


def render_document_pdf(
    *,
    doc_type: str,
    doc_number: str,
    issue_date: date,
    expiration_date: date | None,
    company: dict,
    customer: dict,
    lines: list[dict],
    subtotal: Decimal,
    gst_amount: Decimal,
    total: Decimal,
    currency: str = "AUD",
    paid_date: date | None = None,
    payment_method: str | None = None,
    notes: str | None = None,
    is_gst_registered: bool = False,
    source_document_number: str | None = None,
) -> bytes:
    """Render one document to PDF and return the bytes.

    `company` keys: legal_name, trading_name, address_line1, address_line2,
                    suburb, state, postcode, phone, email, abn,
                    bank_account_name, bank_name, bank_bsb,
                    bank_account_number, bank_swift.
    `customer` keys: name, address (multi-line str), email, phone.
    `lines`: list of {description, quantity, unit_price, amount, gst_treatment}.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    margin = 19 * mm
    content_w = page_w - 2 * margin

    # ----- Top-left: company name + address -----
    y = page_h - margin
    display_name = company.get("trading_name") or company.get("legal_name", "")
    _draw_text(c, margin, y - 14, display_name, font=FONT_BOLD, size=17, color=BRAND_BLUE)

    # A fine warm rule creates a deliberate visual anchor below the masthead.
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.2)
    c.line(margin, y - 23, margin + 48 * mm, y - 23)

    y_addr = y - 14 - 23
    addr_lines = _company_address_lines(company)
    for line in addr_lines:
        _draw_text(c, margin, y_addr, line, size=8.7, color=TEXT_MUTED)
        y_addr -= 11

    # ----- Top-right: document title wordmark -----
    # Size down for longer titles so a wide one doesn't
    # overrun toward the left column / company name.
    title_text = _document_title(doc_type, is_gst_registered)
    title_size = 24 if len(title_text) <= 8 else 16
    _draw_right(c, page_w - margin, y - 14, title_text, font=FONT_BOLD, size=title_size, color=BRAND_BLUE)

    # ----- BILL TO / document-info bands -----
    band_top = min(y_addr - 6, y - 70)
    band_top_y = band_top  # top edge of the header bar
    half_gap = 14
    left_w = (content_w - half_gap) * 0.55
    right_w = content_w - left_w - half_gap

    header_h = 16

    # Left: BILL TO header + body. Wrap each line to the box width FIRST so the
    # box can grow to fit a long name/address instead of clipping it.
    bill_max_w = left_w - 12  # 6pt padding each side
    bill_lines = _customer_bill_to_lines(customer)
    wrapped_bill: list[str] = []
    for line in bill_lines:
        wrapped_bill.extend(_wrap_line(c, line, FONT_BASE, 10, bill_max_w))
    # Grow the box to fit the wrapped content (min 70 keeps the original look).
    body_h_left = max(70, 10 + 12 * len(wrapped_bill))
    body_top_left = _draw_box_with_header(
        c,
        margin,
        band_top_y,
        left_w,
        header_h,
        "BILL TO",
        body_h_left,
    )
    ly = body_top_left - 6
    for wrapped in wrapped_bill:
        _draw_text(c, margin + 6, ly, wrapped, size=9.4)
        ly -= 12

    # Right: document info (number/date/expiration). Build dynamically.
    right_x = margin + left_w + half_gap
    info_rows = _doc_info_rows(
        doc_type,
        doc_number,
        issue_date,
        expiration_date,
        paid_date,
        source_document_number,
    )
    body_h_right = max(70, 4 + 14 * len(info_rows))
    _draw_bar(c, right_x, band_top_y - header_h, right_w, header_h, HEADER_BG)
    # Header row is a 2-col band where each label sits above its value (label in white).
    # Simpler: draw rows of (label, value).
    c.setStrokeColor(ROW_DIVIDER)
    c.setLineWidth(0.65)
    c.setFillColor(LIGHT_GREY)
    c.rect(right_x, band_top_y - header_h - body_h_right, right_w, body_h_right, stroke=1, fill=1)
    ry = band_top_y - header_h - 4
    label_x = right_x + 6
    value_x = right_x + right_w - 6
    # Hide the white "header bar text" — we want the rows inside instead.
    # First "row" is technically the bar; put first label/value in white on the bar.
    if info_rows:
        first_label, first_value = info_rows[0]
        _draw_text(c, label_x, band_top_y - header_h + 4, first_label.upper(), font=FONT_BOLD, size=10, color=white)
        _draw_right(c, value_x, band_top_y - header_h + 4, first_value, font=FONT_BOLD, size=10, color=white)
        rest = info_rows[1:]
    else:
        rest = []
    ry = band_top_y - header_h - 14
    for label, value in rest:
        _draw_text(c, label_x, ry, label.upper(), font=FONT_BOLD, size=9.5)
        _draw_right(c, value_x, ry, value, size=9.5)
        ry -= 14

    # ----- Line items table -----
    table_top = min(body_top_left - body_h_left, ry) - 20
    table_x = margin
    table_w = content_w

    col_widths = [
        table_w * 0.54,  # description
        table_w * 0.10,  # qty
        table_w * 0.16,  # unit price
        table_w * 0.20,  # amount
    ]
    col_x = [table_x]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)
    col_right = [col_x[i] + col_widths[i] for i in range(4)]

    # Header
    row_h = 18
    _draw_bar(c, table_x, table_top - row_h, table_w, row_h, TABLE_HEADER_BG)
    c.setStrokeColor(BRAND_BLUE)
    c.setLineWidth(0.8)
    c.line(table_x, table_top, table_x + table_w, table_top)
    c.line(table_x, table_top - row_h, table_x + table_w, table_top - row_h)
    _draw_text(c, col_x[0] + 6, table_top - row_h + 5, "DESCRIPTION", font=FONT_BOLD, size=9, color=BRAND_BLUE)
    _draw_center(c, (col_x[1] + col_right[1]) / 2, table_top - row_h + 5, "QTY", font=FONT_BOLD, size=9, color=BRAND_BLUE)
    _draw_right(c, col_right[2] - 6, table_top - row_h + 5, "UNIT PRICE", font=FONT_BOLD, size=9, color=BRAND_BLUE)
    _draw_right(c, col_right[3] - 6, table_top - row_h + 5, "AMOUNT", font=FONT_BOLD, size=9, color=BRAND_BLUE)

    page_number = 1
    content_bottom = margin + 18

    def draw_page_footer() -> None:
        if not is_gst_registered:
            _draw_text(c, margin, margin - 2, "No GST has been charged. This is not a tax invoice.", font=FONT_OBLIQUE, size=8, color=HexColor("#808080"))
        _draw_right(c, page_w - margin, margin - 2, f"Page {page_number}", size=8, color=TEXT_MUTED)

    def start_continuation_page(*, with_table_header: bool) -> float:
        """Draw a compact repeated masthead and return the next content y."""
        top = page_h - margin
        _draw_text(c, margin, top - 10, display_name, font=FONT_BOLD, size=13, color=BRAND_BLUE)
        _draw_right(c, page_w - margin, top - 10, title_text, font=FONT_BOLD, size=13, color=BRAND_BLUE)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1)
        c.line(margin, top - 21, page_w - margin, top - 21)
        _draw_text(c, margin, top - 35, f"{doc_number} - CONTINUED", size=8.5, color=TEXT_MUTED)
        continuation_top = top - 50
        if not with_table_header:
            return continuation_top

        _draw_bar(c, table_x, continuation_top - row_h, table_w, row_h, TABLE_HEADER_BG)
        c.setStrokeColor(BRAND_BLUE)
        c.setLineWidth(0.8)
        c.line(table_x, continuation_top, table_x + table_w, continuation_top)
        c.line(table_x, continuation_top - row_h, table_x + table_w, continuation_top - row_h)
        _draw_text(c, col_x[0] + 6, continuation_top - row_h + 5, "DESCRIPTION", font=FONT_BOLD, size=9, color=BRAND_BLUE)
        _draw_center(
            c,
            (col_x[1] + col_right[1]) / 2,
            continuation_top - row_h + 5,
            "QTY",
            font=FONT_BOLD,
            size=9,
            color=BRAND_BLUE,
        )
        _draw_right(c, col_right[2] - 6, continuation_top - row_h + 5, "UNIT PRICE", font=FONT_BOLD, size=9, color=BRAND_BLUE)
        _draw_right(c, col_right[3] - 6, continuation_top - row_h + 5, "AMOUNT", font=FONT_BOLD, size=9, color=BRAND_BLUE)
        return continuation_top - row_h

    # Rows — pad to at least 4 rows so the table doesn't look empty for single-line invoices
    body_lines = list(lines) + [None] * max(0, 4 - len(lines))
    row_y = table_top - row_h
    c.setStrokeColor(ROW_DIVIDER)
    for li in body_lines:
        description = str(li.get("description", "")) if li is not None else ""
        if li is not None and is_gst_registered and doc_type == "invoice":
            tax_label = "GST" if li.get("gst_treatment", "taxable") == "taxable" else "GST-free"
            description = f"{description} [{tax_label}]"
        wrapped_description = (
            _wrap_line(
                c,
                description,
                FONT_BASE,
                9.2,
                col_widths[0] - 12,
            )
            if li is not None
            else []
        )
        current_row_h = max(row_h, 8 + 11 * len(wrapped_description))
        if row_y - current_row_h < content_bottom:
            draw_page_footer()
            c.showPage()
            page_number += 1
            row_y = start_continuation_page(with_table_header=True)
        row_y -= current_row_h
        c.setFillColor(TEXT_DARK)
        c.line(table_x, row_y, table_x + table_w, row_y)
        if li is None:
            # Keep padded rows visually empty; placeholder punctuation can be
            # mistaken for a negative or missing charge on a final invoice.
            continue
        text_y = row_y + current_row_h - 13
        for description_line in wrapped_description:
            _draw_text(c, col_x[0] + 6, text_y, description_line, size=9.2)
            text_y -= 11
        value_y = row_y + current_row_h - 13
        qty = li.get("quantity")
        if qty is not None:
            qty_str = _fmt_qty(qty)
            _draw_center(c, (col_x[1] + col_right[1]) / 2, value_y, qty_str, size=9.2)
        unit = li.get("unit_price")
        if unit is not None:
            # Show $0.00 explicitly for zero-priced lines (e.g. a second
            # visa subclass bundled into the first item's fee). Leaving
            # the cell blank looked like a render bug.
            _draw_right(c, col_right[2] - 6, value_y, _fmt_money(unit, currency), size=9.2)
        amt = li.get("amount")
        if amt is not None:
            _draw_right(c, col_right[3] - 6, value_y, _fmt_money(amt, currency), size=9.2)

    pm_rows = _payment_method_rows(doc_type, company, payment_method, paid_date)
    note_lines: list[str] = []
    if notes:
        for raw_line in notes.splitlines() or [notes]:
            note_lines.extend(_wrap_line(c, raw_line, FONT_BASE, 8.9, content_w))

    summary_height = row_h + 4
    if is_gst_registered:
        summary_height += row_h
    summary_height += 26 + 6 + 30
    if pm_rows:
        summary_height += 16 * (1 + len(pm_rows))
    if note_lines:
        summary_height += 24 + 12 + 11 * len(note_lines)
    summary_height += 8
    if row_y - summary_height < content_bottom:
        draw_page_footer()
        c.showPage()
        page_number += 1
        row_y = start_continuation_page(with_table_header=False)

    # Use the document's persisted totals directly:
    #   subtotal       = pre-GST
    #   gst_amount     = 10% of taxable lines when registered, else 0
    #   total          = subtotal + gst_amount
    # The fees row, GST row and bottom TOTAL band all read from these,
    # so the PDF stays consistent with the list/detail UI and downstream
    # PR/Receipt copies. No reverse-derivation here.
    subtotal_d = Decimal(str(subtotal))
    gst_display = Decimal(str(gst_amount)) if is_gst_registered else Decimal("0.00")
    total_display = Decimal(str(total))

    # Subtotal row (right-aligned label + value, sitting below the table).
    # Label flips to "TOTAL (EXCL. GST)" when GST-registered so the reader
    # can distinguish it from the GST-inclusive total below.
    sub_y = row_y - row_h
    subtotal_label = "TOTAL (EXCL. GST)" if is_gst_registered else "SUBTOTAL"
    _draw_right(c, col_right[2] - 6, sub_y + 5, subtotal_label, size=9.2)
    _draw_right(c, col_right[3] - 6, sub_y + 5, _fmt_money(subtotal_d, currency), size=9.2)

    next_y = sub_y - 4

    # GST row only if GST-registered (per user: not registered → suppress)
    if is_gst_registered:
        next_y -= row_h
        _draw_right(c, col_right[2] - 6, next_y + 5, "GST (10%)", size=9.2)
        _draw_right(c, col_right[3] - 6, next_y + 5, _fmt_money(gst_display, currency), size=9.2)

    # TOTAL big blue band — labelled "TOTAL (INCL. GST)" when GST-registered.
    # The band spans more of the table width when the label is longer so
    # the text and the amount don't collide.
    total_band_h = 26
    if is_gst_registered:
        # Stretch the band left by one extra column-width so "TOTAL (INCL. GST)"
        # has breathing room before the right-aligned amount.
        total_band_w = col_widths[1] + col_widths[2] + col_widths[3]
        total_band_x = col_x[1]
    else:
        total_band_w = col_widths[2] + col_widths[3]
        total_band_x = col_x[2]
    next_y -= total_band_h + 6
    c.setFillColor(HEADER_BG)
    c.setStrokeColor(HEADER_BG)
    c.setLineWidth(0)
    c.roundRect(
        total_band_x,
        next_y,
        total_band_w,
        total_band_h,
        3,
        stroke=0,
        fill=1,
    )
    total_label = "TOTAL (INCL. GST)" if is_gst_registered else "TOTAL"
    total_size = 12.5 if is_gst_registered else 14
    _draw_text(c, total_band_x + 9, next_y + 7, total_label, font=FONT_BOLD, size=total_size, color=white)
    _draw_right(c, total_band_x + total_band_w - 9, next_y + 7, _fmt_money(total_display, currency), font=FONT_BOLD, size=total_size, color=white)

    # ----- Payment method table (bank details) -----
    pm_top = next_y - 30
    if pm_rows:
        pm_label_w = table_w * 0.35
        pm_row_h = 16
        # Header
        _draw_bar(c, table_x, pm_top - pm_row_h, table_w, pm_row_h, TABLE_HEADER_BG)
        c.setStrokeColor(BRAND_BLUE)
        c.setLineWidth(0.8)
        c.line(table_x, pm_top, table_x + table_w, pm_top)
        c.line(table_x, pm_top - pm_row_h, table_x + table_w, pm_top - pm_row_h)
        payment_section_title = "PAYMENT DETAILS" if doc_type == "receipt" else "BANK DETAILS"
        _draw_text(c, table_x + 6, pm_top - pm_row_h + 4, payment_section_title, font=FONT_BOLD, size=9, color=BRAND_BLUE)
        # Rows
        rr_y = pm_top - pm_row_h
        c.setStrokeColor(ROW_DIVIDER)
        for label, value in pm_rows:
            rr_y -= pm_row_h
            c.setStrokeColor(ROW_DIVIDER)
            c.line(table_x, rr_y, table_x + table_w, rr_y)
            _draw_text(c, table_x + 6, rr_y + 4, label, font=FONT_BOLD, size=8.7, color=TEXT_MUTED)
            _draw_text(c, table_x + pm_label_w + 6, rr_y + 4, value or "", size=9)
        # Outer border around the pm body
        body_h = pm_row_h * len(pm_rows)
        c.setStrokeColor(ROW_DIVIDER)
        c.setLineWidth(0.65)
        c.rect(table_x, pm_top - pm_row_h - body_h, table_w, body_h, stroke=1, fill=0)
        pm_bottom = pm_top - pm_row_h - body_h
    else:
        pm_bottom = pm_top

    # ----- Notes (optional) -----
    if note_lines:
        ny = pm_bottom - 24
        _draw_text(c, margin, ny, "NOTES", font=FONT_BOLD, size=8.7, color=BRAND_BLUE)
        ny -= 12
        for line in note_lines:
            _draw_text(c, margin, ny, line, size=8.9)
            ny -= 11

    draw_page_footer()
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def _company_address_lines(company: dict) -> list[str]:
    out: list[str] = []
    legal_name = company.get("legal_name")
    trading_name = company.get("trading_name")
    if legal_name and trading_name and legal_name.casefold() != trading_name.casefold():
        out.append(f"Legal name: {legal_name}")
    if company.get("address_line1"):
        out.append(company["address_line1"])
    if company.get("address_line2"):
        out.append(company["address_line2"])
    locality_bits = [company.get("suburb"), company.get("state"), company.get("postcode")]
    locality = ", ".join(b for b in locality_bits if b)
    if locality:
        out.append(locality)
    if company.get("phone"):
        out.append(f"Phone: {company['phone']}")
    if company.get("email"):
        out.append(f"Email: {company['email']}")
    if company.get("abn"):
        out.append(f"ABN: {company['abn']}")
    return out


def _customer_bill_to_lines(customer: dict) -> list[str]:
    out: list[str] = []
    if customer.get("name"):
        out.append(customer["name"])
    # Address may be multi-line; label the first line "Address:" and indent the
    # rest under it.
    addr_lines = [ln.strip() for ln in (customer.get("address") or "").splitlines() if ln.strip()]
    for i, line in enumerate(addr_lines):
        out.append(f"Address: {line}" if i == 0 else line)
    if customer.get("abn"):
        out.append(f"ABN: {customer['abn']}")
    if customer.get("email"):
        out.append(f"Email: {customer['email']}")
    if customer.get("phone"):
        out.append(f"Phone: {customer['phone']}")
    return out


def _wrap_line(c, text: str, font: str, size: float, max_w: float, indent: str = "  ") -> list[str]:
    """Word-wrap `text` to `max_w` points. Continuation lines get `indent` so a
    wrapped "Address: ..." reads as one field, not several. A single word longer
    than max_w is hard-broken so it never overflows the box."""
    def fits(s: str) -> bool:
        return string_width(s, font, size) <= max_w

    out: list[str] = []
    words = text.split()
    if not words:
        return [text]
    cur = ""
    for w in words:
        prefix = indent if out else ""
        candidate = f"{cur} {w}".strip()
        if fits(prefix + candidate) or not cur:
            # Hard-break a word that can't fit even alone on a line.
            if not cur and not fits(prefix + w):
                piece = ""
                for ch in w:
                    if fits(prefix + piece + ch):
                        piece += ch
                    else:
                        out.append(prefix + piece)
                        piece = ch
                        prefix = indent
                cur = piece
            else:
                cur = candidate
        else:
            out.append(prefix + cur)
            cur = w
    if cur:
        out.append((indent if out else "") + cur)
    return out


def _doc_info_rows(
    doc_type: str,
    doc_number: str,
    issue_date: date,
    expiration_date: date | None,
    paid_date: date | None,
    source_document_number: str | None,
) -> list[tuple[str, str]]:
    if doc_type == "receipt":
        rows = [("Receipt #", doc_number), ("Date", _fmt_date(issue_date))]
        if source_document_number:
            rows.append(("Invoice #", source_document_number))
        if paid_date:
            rows.append(("Paid On", _fmt_date(paid_date)))
        return rows
    # invoice
    rows = [("Invoice #", doc_number), ("Date", _fmt_date(issue_date))]
    if expiration_date:
        rows.append(("Due Date", _fmt_date(expiration_date)))
    return rows


def _payment_method_rows(
    doc_type: str,
    company: dict,
    payment_method: str | None,
    paid_date: date | None,
) -> list[tuple[str, str]]:
    """For receipts we summarise what was already paid. For invoices/payment
    requests we print the bank account so the customer knows where to send money."""
    if doc_type == "receipt":
        rows = [("Payment received", "Yes")]
        if paid_date:
            rows.append(("Paid on", _fmt_date(paid_date)))
        if payment_method:
            rows.append(("Method", payment_method))
        # Also show the bank account they paid into, for the customer's records
        rows.extend(_bank_rows(company))
        return rows
    # invoice — show bank details (only if filled in)
    rows = _bank_rows(company)
    return rows


def _bank_rows(company: dict) -> list[tuple[str, str]]:
    pairs = [
        ("Account Name", company.get("bank_account_name")),
        ("Bank", company.get("bank_name")),
        ("BSB", company.get("bank_bsb")),
        ("Account Number", company.get("bank_account_number")),
        ("SWIFT Code", company.get("bank_swift")),
    ]
    return [(k, v) for k, v in pairs if v]


def _fmt_qty(q) -> str:
    """Format a quantity: drop trailing zeros so "1.0000" displays as "1"."""
    s = str(Decimal(str(q)).normalize())
    if "." in s and "E" not in s.upper():
        s = s.rstrip("0").rstrip(".")
    if s in ("", "-"):
        s = "0"
    return s
