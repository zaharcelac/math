#!/usr/bin/env python3
"""
Generate simple math exercises for grade 1.
Types: addition, subtraction, missing addends, missing minuend, missing subtrahend,
balance addition (X + Y = W + _) and balance subtraction (X - Y = W - _).
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import io
import math
import os
import random
import sys
from pathlib import Path

# PDF font sizes
FONT_SIZE_HEADING = 22
FONT_SIZE_BODY = 26
# Longer lines (X + Y = W + _, X - Y = W - _); tune independently of FONT_SIZE_BODY
FONT_SIZE_BODY_ADDITION_BALANCE = 22
FONT_SIZE_BODY_SUBTRACTION_BALANCE = 22
FONT_SIZE_SHEET_FOOTER = 10

# Gap from physical page bottom to bottom of footer row (mm). Increase to move footer up.
PDF_SHEET_FOOTER_FROM_BOTTOM = 10
PDF_SHEET_FOOTER_LINE_HEIGHT = 5
# Reserve this much space from the bottom for the footer + auto page-break margin (content stays above)
PDF_FOOTER_ZONE_MM = (
    PDF_SHEET_FOOTER_FROM_BOTTOM + PDF_SHEET_FOOTER_LINE_HEIGHT + 3
)
# QR at end of footer line (same payload as resolved URL); only when QR is enabled (see env flags)
PDF_FOOTER_QR_SIZE_MM = 12
PDF_FOOTER_QR_GAP_MM = 10

# Fallback when env vars are unset and there is no ``request_base`` (e.g. CLI ``--print``).
# After ``WORKSHEET_FOOTER_URL``, ``PUBLIC_BASE_URL``, and ``request_base`` in
# :func:`resolve_worksheet_footer_url`.
DEFAULT_WORKSHEET_FOOTER_URL = "<URL HERE>"

# PDF vertical spacing (line height / gaps); multiplied by this factor vs previous defaults
PDF_LINE_SPACING_FACTOR = 2.5
PDF_GAP_SECTION = int(12 * PDF_LINE_SPACING_FACTOR)
PDF_CELL_TITLE_HEIGHT = int(10 * PDF_LINE_SPACING_FACTOR)
PDF_GAP_AFTER_TITLE_BASE = 2
PDF_GAP_AFTER_TITLE = int(PDF_GAP_AFTER_TITLE_BASE * PDF_LINE_SPACING_FACTOR)
PDF_GAP_TASK_ROW = int(8 * PDF_LINE_SPACING_FACTOR)
PDF_CELL_TASK_HEIGHT = int(8 * PDF_LINE_SPACING_FACTOR)
# Exercise grid width on the page (usable width ~190 mm on Letter)
PDF_TASK_COLUMNS = 2

# Exercise type keys (CLI --types)
TYPE_ADDITION = "addition"
TYPE_SUBTRACTION = "subtraction"
TYPE_ADDITION_MISSING_FIRST = "addition-missing-first"
TYPE_ADDITION_MISSING_SECOND = "addition-missing-second"
TYPE_SUBTRACTION_MISSING_MINUEND = "subtraction-missing-minuend"
TYPE_SUBTRACTION_MISSING_SUBTRAHEND = "subtraction-missing-subtrahend"
TYPE_ADDITION_BALANCE = "addition-balance"
TYPE_SUBTRACTION_BALANCE = "subtraction-balance"

EXERCISE_TYPES_ORDER: tuple[str, ...] = (
    TYPE_ADDITION,
    TYPE_SUBTRACTION,
    TYPE_ADDITION_MISSING_FIRST,
    TYPE_ADDITION_MISSING_SECOND,
    TYPE_SUBTRACTION_MISSING_MINUEND,
    TYPE_SUBTRACTION_MISSING_SUBTRAHEND,
    TYPE_ADDITION_BALANCE,
    TYPE_SUBTRACTION_BALANCE,
)

EXERCISE_TITLES: dict[str, str] = {
    TYPE_ADDITION: "ADDITION",
    TYPE_SUBTRACTION: "SUBTRACTION",
    TYPE_ADDITION_MISSING_FIRST: "ADDITION (MISSING FIRST ADDEND)",
    TYPE_ADDITION_MISSING_SECOND: "ADDITION (MISSING SECOND ADDEND)",
    TYPE_SUBTRACTION_MISSING_MINUEND: "SUBTRACTION (MISSING MINUEND)",
    TYPE_SUBTRACTION_MISSING_SUBTRAHEND: "SUBTRACTION (MISSING SUBTRAHEND)",
    TYPE_ADDITION_BALANCE: "ADDITION (BALANCE)",
    TYPE_SUBTRACTION_BALANCE: "SUBTRACTION (BALANCE)",
}

# Short illustrative lines for the web UI (blanks match worksheet underscore style).
EXERCISE_TYPE_EXAMPLES: dict[str, str] = {
    TYPE_ADDITION: "3 + 4 = ___",
    TYPE_SUBTRACTION: "7 - 2 = ___",
    TYPE_ADDITION_MISSING_FIRST: "___ + 5 = 8",
    TYPE_ADDITION_MISSING_SECOND: "3 + ___ = 9",
    TYPE_SUBTRACTION_MISSING_MINUEND: "___ - 4 = 3",
    TYPE_SUBTRACTION_MISSING_SUBTRAHEND: "9 - ___ = 4",
    TYPE_ADDITION_BALANCE: "2 + 3 = 1 + ___",
    TYPE_SUBTRACTION_BALANCE: "7 - 2 = 8 - ___",
}

# CLI --types: full names or abbreviations (case-insensitive)
EXERCISE_TYPE_ALIASES: dict[str, str] = {
    TYPE_ADDITION: TYPE_ADDITION,
    TYPE_SUBTRACTION: TYPE_SUBTRACTION,
    TYPE_ADDITION_MISSING_FIRST: TYPE_ADDITION_MISSING_FIRST,
    TYPE_ADDITION_MISSING_SECOND: TYPE_ADDITION_MISSING_SECOND,
    TYPE_SUBTRACTION_MISSING_MINUEND: TYPE_SUBTRACTION_MISSING_MINUEND,
    TYPE_SUBTRACTION_MISSING_SUBTRAHEND: TYPE_SUBTRACTION_MISSING_SUBTRAHEND,
    TYPE_ADDITION_BALANCE: TYPE_ADDITION_BALANCE,
    TYPE_SUBTRACTION_BALANCE: TYPE_SUBTRACTION_BALANCE,
    "a": TYPE_ADDITION,
    "add": TYPE_ADDITION,
    "s": TYPE_SUBTRACTION,
    "sub": TYPE_SUBTRACTION,
    "amf": TYPE_ADDITION_MISSING_FIRST,
    "am1": TYPE_ADDITION_MISSING_FIRST,
    "ams": TYPE_ADDITION_MISSING_SECOND,
    "am2": TYPE_ADDITION_MISSING_SECOND,
    "smf": TYPE_SUBTRACTION_MISSING_MINUEND,
    "sm1": TYPE_SUBTRACTION_MISSING_MINUEND,
    "smm": TYPE_SUBTRACTION_MISSING_MINUEND,
    "sms": TYPE_SUBTRACTION_MISSING_SUBTRAHEND,
    "sm2": TYPE_SUBTRACTION_MISSING_SUBTRAHEND,
    "smt": TYPE_SUBTRACTION_MISSING_SUBTRAHEND,
    "ab": TYPE_ADDITION_BALANCE,
    "balance": TYPE_ADDITION_BALANCE,
    "bal": TYPE_ADDITION_BALANCE,
    "sb": TYPE_SUBTRACTION_BALANCE,
    "subbalance": TYPE_SUBTRACTION_BALANCE,
    "subbal": TYPE_SUBTRACTION_BALANCE,
}


def default_pdf_output_path() -> Path:
    """Default PDF path: output/math_exercises_YYYY-MM-DD_HH-MM-SS.pdf (local time)."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path("output") / f"math_exercises_{ts}.pdf"


def resolve_worksheet_footer_url(request_base: str | None = None) -> str | None:
    """URL for the PDF footer.

    Priority: ``WORKSHEET_FOOTER_URL``, ``PUBLIC_BASE_URL``, ``request_base`` (e.g. web
    ``str(request.base_url)``), then :data:`DEFAULT_WORKSHEET_FOOTER_URL`. The code default
    must not run before ``request_base`` or the web UI would show a placeholder instead of
    the real origin.

    Whether the URL appears in the footer text and whether a QR is drawn is controlled by
    ``WORKSHEET_FOOTER_SHOW_URL`` and ``WORKSHEET_FOOTER_SHOW_QR`` (see
    :func:`footer_render_options`).
    """
    for key in ("WORKSHEET_FOOTER_URL", "PUBLIC_BASE_URL"):
        raw = os.environ.get(key)
        if raw and raw.strip():
            return raw.strip().rstrip("/")
    if request_base and str(request_base).strip():
        return str(request_base).strip().rstrip("/")
    if DEFAULT_WORKSHEET_FOOTER_URL and DEFAULT_WORKSHEET_FOOTER_URL.strip():
        return DEFAULT_WORKSHEET_FOOTER_URL.strip().rstrip("/")
    return None


def _env_flag(name: str, *, default: bool = True) -> bool:
    """True if env ``name`` is unset (use ``default``) or a truthy string (1/true/yes/on)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class FooterRenderOptions:
    """Resolved footer URL plus whether to show it in text and/or as a QR."""

    url: str | None
    show_url_text: bool
    show_qr: bool


def footer_render_options(resolved_url: str | None) -> FooterRenderOptions:
    """Build footer rendering flags from env (defaults: show URL text and QR when a URL exists)."""
    if not resolved_url:
        return FooterRenderOptions(url=None, show_url_text=False, show_qr=False)
    return FooterRenderOptions(
        url=resolved_url,
        show_url_text=_env_flag("WORKSHEET_FOOTER_SHOW_URL", default=True),
        show_qr=_env_flag("WORKSHEET_FOOTER_SHOW_QR", default=True),
    )


def _pdf_footer_reserve_mm(footer: FooterRenderOptions) -> float:
    """Bottom margin for auto page-break: one footer line + optional QR on the same row."""
    if footer.url and footer.show_qr:
        return max(
            PDF_FOOTER_ZONE_MM,
            PDF_FOOTER_QR_SIZE_MM + PDF_FOOTER_QR_GAP_MM + PDF_SHEET_FOOTER_LINE_HEIGHT,
        )
    return PDF_FOOTER_ZONE_MM


def _footer_url_for_display(url: str) -> str:
    """Return ``url`` without a leading ``http://`` or ``https://`` (any letter case).

    The PDF footer line uses this for a shorter printed string; the QR still encodes the
    full resolved URL.
    """
    u = url.strip()
    lower = u.lower()
    if lower.startswith("https://"):
        return u[8:]
    if lower.startswith("http://"):
        return u[7:]
    return u


def _truncate_text_to_width(pdf: object, text: str, max_w: float) -> str:
    """Shorten ``text`` so ``get_string_width`` fits ``max_w`` (ellipsis if needed)."""
    if pdf.get_string_width(text) <= max_w:
        return text
    ellipsis = "..."
    if pdf.get_string_width(ellipsis) > max_w:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid] + ellipsis
        if pdf.get_string_width(candidate) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ellipsis if lo > 0 else ellipsis


def _footer_qr_png(url: str) -> io.BytesIO:
    """PNG bytes for a small QR code encoding the full ``url`` (footer text may omit the scheme)."""
    import qrcode

    buf = io.BytesIO()
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=2,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def digit_slots(min_value: int, max_value: int) -> int:
    """Character width for every number and blank: widest digit count in [min_value, max_value]."""
    return max(1, len(str(min_value)), len(str(max_value)))


def align_equation_line(task: str, min_value: int, max_value: int) -> str:
    """Fixed columns: each operand/result/blank is digit_slots wide; numbers right-aligned."""
    col_w = digit_slots(min_value, max_value)
    blank_fill = "_" * col_w
    parts = task.split()

    def slot(token: str) -> str:
        if token and set(token) <= {"_"}:
            return blank_fill
        return str(int(token)).rjust(col_w)

    # X + Y = W + _  (equal sums; missing last addend on the right)
    if (
        len(parts) == 7
        and parts[3] == "="
        and parts[1] == "+"
        and parts[5] == "+"
    ):
        a, _p1, b, _eq, w, _p2, c = parts
        return f"{slot(a)} + {slot(b)} = {slot(w)} + {slot(c)}"

    # X - Y = W - _  (equal differences; missing subtrahend on the right)
    if (
        len(parts) == 7
        and parts[3] == "="
        and parts[1] == "-"
        and parts[5] == "-"
    ):
        a, _p1, b, _eq, w, _p2, c = parts
        return f"{slot(a)} - {slot(b)} = {slot(w)} - {slot(c)}"

    if len(parts) != 5 or parts[3] != "=" or parts[1] not in ("+", "-"):
        return task

    a, op, b, _eq, c = parts
    return f"{slot(a)} {op} {slot(b)} = {slot(c)}"


def max_equations_with_zero(total: int) -> int:
    """Max count of equations that may include the value 0 (at most 5% of total, rounded up)."""
    if total < 1:
        return 0
    return min(total, math.ceil(total * 0.05))


def equation_includes_zero_value(task: str) -> bool:
    """True if any shown integer operand/result in the task is exactly 0 (not 10, 20, …)."""
    for p in task.split():
        if p in ("+", "-", "="):
            continue
        if p and set(p) <= {"_"}:
            continue
        try:
            if int(p) == 0:
                return True
        except ValueError:
            pass
    return False


def generate_addition_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate addition tasks: a + b = blanks where a, b in [min_value, max_value] and a+b <= max_value."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    tasks: list[str] = []
    zero_count = 0
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        a = random.randint(min_value, max_value)
        b = random.randint(min_value, max_value)
        sm = a + b
        if sm > max_value or sm < min_value:
            continue
        s = f"{a} + {b} = {bl}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique addition tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    return tasks


def generate_subtraction_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate subtraction tasks: a - b = blanks with a, b in [min_value, max_value] and a-b <= max_value."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    tasks: list[str] = []
    zero_count = 0
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        a = random.randint(min_value, max_value)
        b = random.randint(min_value, max_value)
        if a < b:
            a, b = b, a
        d = a - b
        if d > max_value or d < min_value:
            continue
        s = f"{a} - {b} = {bl}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique subtraction tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    return tasks


def generate_addition_missing_first_addend_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate __ + b = c (first addend missing); b, c and implied a=c-b in [min_value, max_value]."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        b = random.randint(min_value, max_value)
        c_lo = b + min_value
        if c_lo > max_value:
            continue
        c = random.randint(c_lo, max_value)
        s = f"{bl} + {b} = {c}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique first-missing-addend tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_addition_missing_second_addend_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate a + __ = c (second addend missing); a, c and implied b=c-a in [min_value, max_value]."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        a = random.randint(min_value, max_value)
        c_lo = a + min_value
        if c_lo > max_value:
            continue
        c = random.randint(c_lo, max_value)
        s = f"{a} + {bl} = {c}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique second-missing-addend tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_missing_minuend_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate __ - b = c (minuend missing); b, c and implied a=b+c in [min_value, max_value], a <= max_value."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        b = random.randint(min_value, max_value)
        c = random.randint(min_value, max_value)
        if b + c > max_value:
            continue
        s = f"{bl} - {b} = {c}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique missing-minuend tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_missing_subtrahend_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate a - __ = c (subtrahend missing); a, c and implied b=a-c in [min_value, max_value]."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        a = random.randint(min_value, max_value)
        c_lo = max(min_value, a - max_value)
        c_hi = min(a, a - min_value)
        if c_lo > c_hi:
            continue
        c = random.randint(c_lo, c_hi)
        s = f"{a} - {bl} = {c}"
        if s in shared_seen:
            continue
        z = equation_includes_zero_value(s)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s)
        tasks.append(s)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique missing-subtrahend tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_addition_balance_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate X + Y = W + _ with X+Y = W+answer; X,Y,W,answer in [min_value, max_value] and X+Y ≤ max_value.
    W is never equal to X or Y."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        x = random.randint(min_value, max_value)
        y = random.randint(min_value, max_value)
        s = x + y
        if s > max_value:
            continue
        w_lo = max(min_value, s - max_value)
        w_hi = min(max_value, s - min_value)
        choices = [w for w in range(w_lo, w_hi + 1) if w not in (x, y)]
        if not choices:
            continue
        w = random.choice(choices)
        s_line = f"{x} + {y} = {w} + {bl}"
        if s_line in shared_seen:
            continue
        z = equation_includes_zero_value(s_line)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s_line)
        tasks.append(s_line)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique addition-balance tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_balance_tasks(
    total: int, min_value: int, max_value: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate X - Y = W - _ with X-Y = W-answer, X≥Y; X,Y,W,answer in [min_value, max_value].
    W is never equal to X or Y."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        x = random.randint(min_value, max_value)
        y = random.randint(min_value, max_value)
        if x < y:
            x, y = y, x
        s = x - y
        if s > max_value:
            continue
        # W - ? = S  =>  ? = W - S; need W ≥ S, answer in [min_value, max_value]
        w_lo = s + min_value
        w_hi = min(max_value, s + max_value)
        choices = [w for w in range(w_lo, w_hi + 1) if w not in (x, y)]
        if not choices:
            continue
        w = random.choice(choices)
        s_line = f"{x} - {y} = {w} - {bl}"
        if s_line in shared_seen:
            continue
        z = equation_includes_zero_value(s_line)
        if z and zero_count >= max_zero:
            continue
        shared_seen.add(s_line)
        tasks.append(s_line)
        if z:
            zero_count += 1

    if len(tasks) < total:
        raise RuntimeError(
            f"Could not generate {total} unique subtraction-balance tasks with at most {max_zero} "
            f"containing 0 (min_value={min_value}, max_value={max_value}). "
            "Widen the value range (--max-value / --min-value) or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def format_output(
    sections: list[tuple[str, list[str]]], min_value: int, max_value: int
) -> str:
    """Format exercises for text output: (section title, tasks)."""
    lines: list[str] = []
    for title, tasks in sections:
        if lines:
            lines.append("")
        aligned = [align_equation_line(t, min_value, max_value) for t in tasks]
        lines.extend([title, "-" * 40, *aligned])
    return "\n".join(lines)


def _render_pdf_sheet_footer(
    pdf: object,
    test_index: int,
    test_count: int,
    min_value: int,
    max_value: int,
    tasks_per_type: int,
    footer: FooterRenderOptions,
) -> None:
    """Draw TEST line; optional URL in text and/or QR (see :class:`FooterRenderOptions`)."""
    from fpdf.enums import XPos, YPos

    label = (
        f"SET {test_index} OF {test_count}   "
        f"MIN-VALUE {min_value}   MAX-VALUE {max_value}   TOTAL {tasks_per_type}"
    )
    url = footer.url
    show_url = bool(url and footer.show_url_text)
    show_qr = bool(url and footer.show_qr)
    url_display = _footer_url_for_display(url) if url else ""
    text = f"{label}   {url_display}" if show_url else label
    margin = _pdf_footer_reserve_mm(footer)
    pdf.set_auto_page_break(auto=False)
    pdf.set_font("courier", size=FONT_SIZE_SHEET_FOOTER)
    if show_qr and url:
        qr_h = PDF_FOOTER_QR_SIZE_MM
        gap = PDF_FOOTER_QR_GAP_MM
        line_h = PDF_SHEET_FOOTER_LINE_HEIGHT
        cm = pdf.c_margin
        # cell() adds horizontal padding; keep text+QR on one row within epw.
        max_plain_w = pdf.epw - gap - qr_h - 2 * cm
        line_text = _truncate_text_to_width(pdf, text, max_plain_w)
        cell_w = pdf.get_string_width(line_text) + 2 * cm
        total_w = cell_w + gap + qr_h
        row_h = max(qr_h, line_h)
        row_top = pdf.h - row_h - PDF_SHEET_FOOTER_FROM_BOTTOM
        x_start = pdf.l_margin + max(0.0, (pdf.epw - total_w) / 2)
        text_y = row_top + (row_h - line_h) / 2
        qr_y = row_top + (row_h - qr_h) / 2

        pdf.set_xy(x_start, text_y)
        pdf.cell(
            None,
            line_h,
            line_text,
            new_x=XPos.RIGHT,
            new_y=YPos.TOP,
        )
        qr_x = pdf.get_x() + gap
        qr_buf = _footer_qr_png(url)
        pdf.image(
            qr_buf,
            x=qr_x,
            y=qr_y,
            w=qr_h,
            h=qr_h,
            alt_text=f"QR {url}",
        )
    else:
        pdf.set_y(-PDF_SHEET_FOOTER_FROM_BOTTOM)
        pdf.multi_cell(
            0,
            PDF_SHEET_FOOTER_LINE_HEIGHT,
            text,
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.set_auto_page_break(auto=True, margin=margin)


def _render_pdf_worksheet_page(
    pdf: object,
    sections: list[tuple[str, list[str]]],
    min_value: int,
    max_value: int,
    tasks_per_type: int,
    test_index: int,
    test_count: int,
    footer: FooterRenderOptions,
) -> None:
    """Draw one worksheet: each exercise type on its own page; footer on every page."""
    from fpdf.enums import XPos, YPos

    cols = PDF_TASK_COLUMNS
    for _sec_idx, (title, tasks) in enumerate(sections):
        pdf.add_page()
        pdf.set_font("courier", "B", size=FONT_SIZE_HEADING)
        pdf.cell(
            0,
            PDF_CELL_TITLE_HEIGHT,
            title,
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        if title == EXERCISE_TITLES[TYPE_ADDITION_BALANCE]:
            body_size = FONT_SIZE_BODY_ADDITION_BALANCE
        elif title == EXERCISE_TITLES[TYPE_SUBTRACTION_BALANCE]:
            body_size = FONT_SIZE_BODY_SUBTRACTION_BALANCE
        else:
            body_size = FONT_SIZE_BODY
        pdf.set_font("courier", size=body_size)
        pdf.ln(PDF_GAP_AFTER_TITLE)

        for i, task in enumerate(tasks):
            if i > 0 and i % cols == 0:
                pdf.ln(PDF_GAP_TASK_ROW)
            width = 190 / cols
            line = align_equation_line(task, min_value, max_value)
            col_idx = i % cols
            cell_align = "R" if col_idx == cols - 1 else "L"
            pdf.cell(width, PDF_CELL_TASK_HEIGHT, line, align=cell_align)

        _render_pdf_sheet_footer(
            pdf, test_index, test_count, min_value, max_value, tasks_per_type, footer
        )


def _build_pdf_document(
    pages_sections: list[list[tuple[str, list[str]]]],
    min_value: int,
    max_value: int,
    tasks_per_type: int,
    footer: FooterRenderOptions,
):
    """Build in-memory FPDF workbook (US Letter)."""
    from fpdf import FPDF

    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=_pdf_footer_reserve_mm(footer))
    test_count = len(pages_sections)
    for idx, sections in enumerate(pages_sections, start=1):
        _render_pdf_worksheet_page(
            pdf, sections, min_value, max_value, tasks_per_type, idx, test_count, footer
        )
    return pdf


def generate_pdf_bytes(
    pages_sections: list[list[tuple[str, list[str]]]],
    min_value: int,
    max_value: int,
    tasks_per_type: int,
    footer: FooterRenderOptions,
) -> bytes:
    """Render workbook to PDF bytes (same layout as file output)."""
    pdf = _build_pdf_document(pages_sections, min_value, max_value, tasks_per_type, footer)
    raw = pdf.output(dest="S")
    return bytes(raw)


def generate_pdf(
    pages_sections: list[list[tuple[str, list[str]]]],
    output_path: Path,
    min_value: int,
    max_value: int,
    tasks_per_type: int,
    footer: FooterRenderOptions,
) -> None:
    """Write workbook PDF to disk."""
    pdf = _build_pdf_document(pages_sections, min_value, max_value, tasks_per_type, footer)
    pdf.output(str(output_path))


def build_workbook_pages(
    exercise_types: list[str],
    total: int,
    min_value: int,
    max_value: int,
    sheets: int,
    seed: int | None,
) -> list[list[tuple[str, list[str]]]]:
    """Build all worksheet page lists (one per --sheets), same logic as CLI."""
    pages: list[list[tuple[str, list[str]]]] = []
    for i in range(sheets):
        if seed is not None:
            random.seed(seed + i)
        pages.append(build_sections(exercise_types, total, min_value, max_value))
    return pages


def generate_workbook_pdf_bytes(
    exercise_types: list[str],
    total: int,
    max_value: int,
    sheets: int,
    seed: int | None,
    footer_url: str | None = None,
    *,
    min_value: int = 0,
) -> bytes:
    """High-level: validate inputs via same generators as CLI; return PDF bytes.

    ``footer_url`` is passed to :func:`resolve_worksheet_footer_url` (e.g. ``str(request.base_url)``
    from the web app). For CLI, omit it and use env vars and/or :data:`DEFAULT_WORKSHEET_FOOTER_URL`.

    Whether the URL appears in the footer line and whether a QR is drawn is set by
    ``WORKSHEET_FOOTER_SHOW_URL`` and ``WORKSHEET_FOOTER_SHOW_QR`` (:func:`footer_render_options`).
    """
    pages = build_workbook_pages(
        exercise_types, total, min_value, max_value, sheets, seed
    )
    resolved = resolve_worksheet_footer_url(footer_url)
    return generate_pdf_bytes(
        pages,
        min_value,
        max_value,
        total,
        footer=footer_render_options(resolved),
    )


def parse_exercise_type_tokens(tokens: list[str]) -> list[str]:
    """Resolve abbreviations to canonical keys; deduplicate while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in tokens:
        key = raw.strip().lower()
        if key not in EXERCISE_TYPE_ALIASES:
            valid = ", ".join(EXERCISE_TYPES_ORDER)
            aliases = (
                "a, add, s, sub, amf, am1, ams, am2, smf, sm1, smm, sms, sm2, smt, "
                "ab, balance, bal, sb, subbalance, subbal"
            )
            raise ValueError(
                f"unknown exercise type {raw!r}; use {valid}, or abbreviations: {aliases}"
            )
        canon = EXERCISE_TYPE_ALIASES[key]
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def build_sections(
    types: list[str], total: int, min_value: int, max_value: int
) -> list[tuple[str, list[str]]]:
    """Generate tasks for each type in order; titles from EXERCISE_TITLES."""
    bw = digit_slots(min_value, max_value)
    shared_seen: set[str] = set()
    generators: dict[str, Callable[[int, int, int, int, set[str]], list[str]]] = {
        TYPE_ADDITION: generate_addition_tasks,
        TYPE_SUBTRACTION: generate_subtraction_tasks,
        TYPE_ADDITION_MISSING_FIRST: generate_addition_missing_first_addend_tasks,
        TYPE_ADDITION_MISSING_SECOND: generate_addition_missing_second_addend_tasks,
        TYPE_SUBTRACTION_MISSING_MINUEND: generate_subtraction_missing_minuend_tasks,
        TYPE_SUBTRACTION_MISSING_SUBTRAHEND: generate_subtraction_missing_subtrahend_tasks,
        TYPE_ADDITION_BALANCE: generate_addition_balance_tasks,
        TYPE_SUBTRACTION_BALANCE: generate_subtraction_balance_tasks,
    }
    sections: list[tuple[str, list[str]]] = []
    for key in types:
        tasks = generators[key](total, min_value, max_value, bw, shared_seen)
        sections.append((EXERCISE_TITLES[key], tasks))
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate simple math exercises for grade 1."
    )
    parser.add_argument(
        "--total",
        type=int,
        default=12,
        help="Number of tasks per type (default: 12)",
    )
    parser.add_argument(
        "--max-value",
        type=int,
        default=20,
        metavar="N",
        help="Maximum value used in equations (default: 20)",
    )
    parser.add_argument(
        "--min-value",
        type=int,
        default=0,
        metavar="N",
        help="Minimum value for operands and shown results (default: 0)",
    )
    parser.add_argument(
        "--print",
        dest="generate_pdf",
        action="store_true",
        help="Generate PDF for printing (US Letter format)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=(
            "Output PDF path when --print is used (default: "
            "output/math_exercises_YYYY-MM-DD_HH-MM-SS.pdf using current local time)"
        ),
    )
    parser.add_argument(
        "--sheets",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Number of worksheet pages in the PDF (default: 1). "
            "Each page is a full exercise set; footer shows TEST i OF n for worksheet i of n. "
            "Ignored without --print."
        ),
    )
    parser.add_argument(
        "--types",
        nargs="+",
        default=None,
        metavar="TYPE",
        help=(
            "Exercise types to include (default: all). "
            "Names: addition, subtraction, addition-missing-first, addition-missing-second, "
            "subtraction-missing-minuend, subtraction-missing-subtrahend, addition-balance, "
            "subtraction-balance. "
            "Abbreviations: a, add, s, sub, amf, am1, ams, am2, smf, sm1, smm, sms, sm2, smt, "
            "ab, balance, bal, sb, subbalance, subbal. "
            "Order on the worksheet follows the order given."
        ),
    )

    args = parser.parse_args()

    if args.types is not None:
        try:
            exercise_types = parse_exercise_type_tokens(args.types)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        exercise_types = list(EXERCISE_TYPES_ORDER)

    if not exercise_types:
        print("Error: at least one exercise type is required", file=sys.stderr)
        return 1

    if args.total < 1:
        print("Error: --total must be at least 1", file=sys.stderr)
        return 1
    if args.min_value < 0:
        print("Error: --min-value must be non-negative", file=sys.stderr)
        return 1
    if args.max_value < 0:
        print("Error: --max-value must be non-negative", file=sys.stderr)
        return 1
    if args.min_value > args.max_value:
        print(
            "Error: --min-value must be less than or equal to --max-value",
            file=sys.stderr,
        )
        return 1
    if args.sheets < 1:
        print("Error: --sheets must be at least 1", file=sys.stderr)
        return 1

    if args.generate_pdf:
        pages: list[list[tuple[str, list[str]]]] = []
        try:
            for i in range(args.sheets):
                if args.seed is not None:
                    random.seed(args.seed + i)
                pages.append(
                    build_sections(
                        exercise_types, args.total, args.min_value, args.max_value
                    )
                )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(format_output(pages[0], args.min_value, args.max_value))
        if args.sheets > 1:
            print(
                f"(Text above is TEST 1 OF {args.sheets}; PDF has {args.sheets} worksheets, each labeled TEST i OF {args.sheets}.)",
                file=sys.stderr,
            )
        try:
            pdf_path = args.output if args.output is not None else default_pdf_output_path()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            generate_pdf(
                pages,
                pdf_path,
                args.min_value,
                args.max_value,
                args.total,
                footer=footer_render_options(resolve_worksheet_footer_url()),
            )
            print(f"\nPDF saved to: {pdf_path}", file=sys.stderr)
        except ImportError as e:
            print(
                f"Error: PDF generation requires fpdf2. Install with: pip install fpdf2\n{e}",
                file=sys.stderr,
            )
            return 1
    else:
        if args.seed is not None:
            random.seed(args.seed)
        try:
            sections = build_sections(
                exercise_types, args.total, args.min_value, args.max_value
            )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(format_output(sections, args.min_value, args.max_value))
        if args.sheets > 1:
            print(
                "Note: --sheets applies only with --print; ignored here.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
