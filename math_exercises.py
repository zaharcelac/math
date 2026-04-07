#!/usr/bin/env python3
"""
Generate simple math exercises for grade 1.
Types: addition, subtraction, missing addends, missing minuend, missing subtrahend,
balance addition (X + Y = W + _) and balance subtraction (X - Y = W - _).
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
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

# Footer line for "TEST x OF y" (mm); optional URL is on the same line
PDF_SHEET_FOOTER_FROM_BOTTOM = 12
PDF_SHEET_FOOTER_LINE_HEIGHT = 5
# Reserve this much space from the bottom for the footer + auto page-break margin (content stays above)
PDF_FOOTER_ZONE_MM = (
    PDF_SHEET_FOOTER_FROM_BOTTOM + PDF_SHEET_FOOTER_LINE_HEIGHT + 3
)

# Fallback when env vars are unset and there is no ``request_base`` (e.g. CLI ``--print``).
# After ``WORKSHEET_FOOTER_URL``, ``PUBLIC_BASE_URL``, and ``request_base`` in
# :func:`resolve_worksheet_footer_url`.
DEFAULT_WORKSHEET_FOOTER_URL = "<URL HERE>"

# PDF vertical spacing (line height / gaps); multiplied by this factor vs previous defaults
PDF_LINE_SPACING_FACTOR = 2.5
PDF_GAP_SECTION = int(12 * PDF_LINE_SPACING_FACTOR)
PDF_CELL_TITLE_HEIGHT = int(10 * PDF_LINE_SPACING_FACTOR)
PDF_GAP_AFTER_TITLE = int(4 * PDF_LINE_SPACING_FACTOR)
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
    """Default PDF path: output/math_exercises_YYYY-MM-DD_HH-MM.pdf (local time)."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Path("output") / f"math_exercises_{ts}.pdf"


def resolve_worksheet_footer_url(request_base: str | None = None) -> str | None:
    """URL for the PDF footer.

    Priority: ``WORKSHEET_FOOTER_URL``, ``PUBLIC_BASE_URL``, ``request_base`` (e.g. web
    ``str(request.base_url)``), then :data:`DEFAULT_WORKSHEET_FOOTER_URL`. The code default
    must not run before ``request_base`` or the web UI would show a placeholder instead of
    the real origin.
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


def digit_slots(max_number: int) -> int:
    """Character width for every number and blank: same as digit count of --max-number."""
    return max(1, len(str(max_number)))


def align_equation_line(task: str, max_number: int) -> str:
    """Fixed columns: each operand/result/blank is digit_slots wide; numbers right-aligned."""
    col_w = digit_slots(max_number)
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
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate addition tasks: a + b = blanks where a, b, and a+b <= max_number."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    tasks: list[str] = []
    zero_count = 0
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        a = random.randint(0, max_number)
        b = random.randint(0, max_number)
        if a + b > max_number:
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    return tasks


def generate_subtraction_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate subtraction tasks: a - b = blanks where a, b, and a-b <= max_number."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    tasks: list[str] = []
    zero_count = 0
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        a = random.randint(0, max_number)
        b = random.randint(0, max_number)
        if a < b:
            a, b = b, a
        if a - b > max_number:
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    return tasks


def generate_addition_missing_first_addend_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate __ + b = c (first addend missing)."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        b = random.randint(0, max_number)
        c = random.randint(b, max_number)
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_addition_missing_second_addend_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate a + __ = c (second addend missing)."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        a = random.randint(0, max_number)
        c = random.randint(a, max_number)
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_missing_minuend_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate __ - b = c (minuend missing)."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        b = random.randint(0, max_number)
        c = random.randint(0, max_number)
        if b + c > max_number:
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_missing_subtrahend_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate a - __ = c (subtrahend missing)."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    while len(tasks) < total and attempts < total * 400:
        attempts += 1
        a = random.randint(0, max_number)
        c = random.randint(0, a)
        if a - c > max_number:
            continue
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_addition_balance_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate X + Y = W + _ with X+Y = W+answer and all of X,Y,W,answer ≤ max_number (and X+Y ≤ max_number).
    W is never equal to X or Y."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        x = random.randint(0, max_number)
        y = random.randint(0, max_number)
        s = x + y
        if s > max_number:
            continue
        w_lo = max(0, s - max_number)
        w_hi = min(s, max_number)
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def generate_subtraction_balance_tasks(
    total: int, max_number: int, blank_w: int, shared_seen: set[str]
) -> list[str]:
    """Generate X - Y = W - _ with X-Y = W-answer, X≥Y, all operands/answers ≤ max_number.
    W is never equal to X or Y."""
    bl = "_" * blank_w
    max_zero = max_equations_with_zero(total)
    zero_count = 0
    tasks: list[str] = []
    attempts = 0
    max_attempts = total * 500

    while len(tasks) < total and attempts < max_attempts:
        attempts += 1
        x = random.randint(0, max_number)
        y = random.randint(0, max_number)
        if x < y:
            x, y = y, x
        s = x - y
        if s > max_number:
            continue
        # W - ? = S  =>  ? = W - S; need W ≥ S and ? ≤ max_number (automatic when W ≤ max_number)
        w_lo = s
        w_hi = max_number
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
            f"containing 0 (max_number={max_number}). "
            "Increase --max-number or reduce --total."
        )
    random.shuffle(tasks)
    return tasks


def format_output(sections: list[tuple[str, list[str]]], max_number: int) -> str:
    """Format exercises for text output: (section title, tasks)."""
    lines: list[str] = []
    for title, tasks in sections:
        if lines:
            lines.append("")
        aligned = [align_equation_line(t, max_number) for t in tasks]
        lines.extend([title, "-" * 40, *aligned])
    return "\n".join(lines)


def _render_pdf_sheet_footer(
    pdf: object,
    test_index: int,
    test_count: int,
    max_number: int,
    tasks_per_type: int,
    footer_url: str | None = None,
) -> None:
    """Draw TEST x OF y, max-number, total, and optional URL on one footer line."""
    from fpdf.enums import XPos, YPos

    label = (
        f"TEST {test_index} OF {test_count}   "
        f"MAX-NUMBER {max_number}   TOTAL {tasks_per_type}"
    )
    text = f"{label}   {footer_url}" if footer_url else label
    pdf.set_auto_page_break(auto=False)
    pdf.set_y(-PDF_SHEET_FOOTER_FROM_BOTTOM)
    pdf.set_font("courier", size=FONT_SIZE_SHEET_FOOTER)
    pdf.multi_cell(
        0,
        PDF_SHEET_FOOTER_LINE_HEIGHT,
        text,
        align="C",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_auto_page_break(auto=True, margin=PDF_FOOTER_ZONE_MM)


def _render_pdf_worksheet_page(
    pdf: object,
    sections: list[tuple[str, list[str]]],
    max_number: int,
    tasks_per_type: int,
    test_index: int,
    test_count: int,
    footer_url: str | None = None,
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
            line = align_equation_line(task, max_number)
            col_idx = i % cols
            cell_align = "R" if col_idx == cols - 1 else "L"
            pdf.cell(width, PDF_CELL_TASK_HEIGHT, line, align=cell_align)

        _render_pdf_sheet_footer(
            pdf, test_index, test_count, max_number, tasks_per_type, footer_url
        )


def _build_pdf_document(
    pages_sections: list[list[tuple[str, list[str]]]],
    max_number: int,
    tasks_per_type: int,
    footer_url: str | None = None,
):
    """Build in-memory FPDF workbook (US Letter)."""
    from fpdf import FPDF

    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=PDF_FOOTER_ZONE_MM)
    test_count = len(pages_sections)
    for idx, sections in enumerate(pages_sections, start=1):
        _render_pdf_worksheet_page(
            pdf, sections, max_number, tasks_per_type, idx, test_count, footer_url
        )
    return pdf


def generate_pdf_bytes(
    pages_sections: list[list[tuple[str, list[str]]]],
    max_number: int,
    tasks_per_type: int,
    footer_url: str | None = None,
) -> bytes:
    """Render workbook to PDF bytes (same layout as file output)."""
    pdf = _build_pdf_document(pages_sections, max_number, tasks_per_type, footer_url)
    raw = pdf.output(dest="S")
    return bytes(raw)


def generate_pdf(
    pages_sections: list[list[tuple[str, list[str]]]],
    output_path: Path,
    max_number: int,
    tasks_per_type: int,
    footer_url: str | None = None,
) -> None:
    """Write workbook PDF to disk."""
    pdf = _build_pdf_document(pages_sections, max_number, tasks_per_type, footer_url)
    pdf.output(str(output_path))


def build_workbook_pages(
    exercise_types: list[str],
    total: int,
    max_number: int,
    sheets: int,
    seed: int | None,
) -> list[list[tuple[str, list[str]]]]:
    """Build all worksheet page lists (one per --sheets), same logic as CLI."""
    pages: list[list[tuple[str, list[str]]]] = []
    for i in range(sheets):
        if seed is not None:
            random.seed(seed + i)
        pages.append(build_sections(exercise_types, total, max_number))
    return pages


def generate_workbook_pdf_bytes(
    exercise_types: list[str],
    total: int,
    max_number: int,
    sheets: int,
    seed: int | None,
    footer_url: str | None = None,
) -> bytes:
    """High-level: validate inputs via same generators as CLI; return PDF bytes.

    ``footer_url`` is passed to :func:`resolve_worksheet_footer_url` (e.g. ``str(request.base_url)``
    from the web app). For CLI, omit it and use env vars and/or :data:`DEFAULT_WORKSHEET_FOOTER_URL`.
    """
    pages = build_workbook_pages(exercise_types, total, max_number, sheets, seed)
    resolved = resolve_worksheet_footer_url(footer_url)
    return generate_pdf_bytes(pages, max_number, total, footer_url=resolved)


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
    types: list[str], total: int, max_number: int
) -> list[tuple[str, list[str]]]:
    """Generate tasks for each type in order; titles from EXERCISE_TITLES."""
    bw = digit_slots(max_number)
    shared_seen: set[str] = set()
    generators: dict[str, Callable[[int, int, int, set[str]], list[str]]] = {
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
        tasks = generators[key](total, max_number, bw, shared_seen)
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
        "--max-number",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number used in equations (default: 20)",
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
            "output/math_exercises_YYYY-MM-DD_HH-MM.pdf using current local time)"
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
    if args.max_number < 0:
        print("Error: --max-number must be non-negative", file=sys.stderr)
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
                    build_sections(exercise_types, args.total, args.max_number)
                )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(format_output(pages[0], args.max_number))
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
                args.max_number,
                args.total,
                footer_url=resolve_worksheet_footer_url(),
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
            sections = build_sections(exercise_types, args.total, args.max_number)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(format_output(sections, args.max_number))
        if args.sheets > 1:
            print(
                "Note: --sheets applies only with --print; ignored here.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
