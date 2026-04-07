"""
MVP web UI: FastAPI + Jinja2 + HTMX.
- Plain form submit returns PDF directly.
- HTMX requests get validation errors as HTML partials; success uses HX-Redirect to /download/{token}.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

# Project root (parent of web/)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from math_exercises import (  # noqa: E402
    EXERCISE_TYPES_ORDER,
    EXERCISE_TITLES,
    default_pdf_output_path,
    generate_workbook_pdf_bytes,
    parse_exercise_type_tokens,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Short-lived PDF cache for HTMX redirect-after-POST (token -> bytes)
_pdf_cache: dict[str, bytes] = {}

# Reasonable limits for a public form
MAX_TOTAL = 60
MAX_MAX_NUMBER = 200
MAX_SHEETS = 20

app = FastAPI(
    title="Math worksheets",
    description="Generate grade-1 style math worksheets as PDF.",
)


def _filename_for_download() -> str:
    return default_pdf_output_path().name


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "types_order": EXERCISE_TYPES_ORDER,
            "type_titles": EXERCISE_TITLES,
            "errors": None,
            "values": {
                "total": 12,
                "max_number": 20,
                "sheets": 1,
                "seed": "",
            },
            "selected_types": set(EXERCISE_TYPES_ORDER),
        },
    )


@app.post("/generate")
async def generate(request: Request) -> Response:
    """Build PDF. HTMX: validation errors as partial; success → 204 + HX-Redirect to /download/{token}."""
    form = await request.form()
    try:
        total = int(form.get("total", 12))
        max_number = int(form.get("max_number", 20))
        sheets = int(form.get("sheets", 1))
    except (TypeError, ValueError):
        total, max_number, sheets = 12, 20, 1
    seed = str(form.get("seed") or "")
    types = form.getlist("types")

    hx = request.headers.get("HX-Request") == "true"
    errors: list[str] = []

    if total < 1 or total > MAX_TOTAL:
        errors.append(f"Total must be between 1 and {MAX_TOTAL}.")
    if max_number < 0 or max_number > MAX_MAX_NUMBER:
        errors.append(f"Max number must be between 0 and {MAX_MAX_NUMBER}.")
    if sheets < 1 or sheets > MAX_SHEETS:
        errors.append(f"Sheets must be between 1 and {MAX_SHEETS}.")

    selected = types if types else []
    if not selected:
        errors.append("Select at least one exercise type.")

    exercise_types: list[str] = []
    if not errors:
        try:
            exercise_types = parse_exercise_type_tokens(selected)
        except ValueError as e:
            errors.append(str(e))

    seed_val: int | None = None
    if not errors and seed.strip():
        try:
            seed_val = int(seed.strip())
        except ValueError:
            errors.append("Seed must be an integer.")

    if errors:
        ctx = {
            "types_order": EXERCISE_TYPES_ORDER,
            "type_titles": EXERCISE_TITLES,
            "errors": errors,
            "values": {
                "total": total,
                "max_number": max_number,
                "sheets": sheets,
                "seed": seed,
            },
            "selected_types": set(selected),
        }
        if hx:
            return templates.TemplateResponse(request, "partials/errors.html", ctx)
        return templates.TemplateResponse(
            request, "index.html", ctx, status_code=422
        )

    try:
        pdf_bytes = generate_workbook_pdf_bytes(
            exercise_types, total, max_number, sheets, seed_val
        )
    except RuntimeError as e:
        ctx = {
            "types_order": EXERCISE_TYPES_ORDER,
            "type_titles": EXERCISE_TITLES,
            "errors": [str(e)],
            "values": {
                "total": total,
                "max_number": max_number,
                "sheets": sheets,
                "seed": seed,
            },
            "selected_types": set(selected),
        }
        if hx:
            return templates.TemplateResponse(request, "partials/errors.html", ctx)
        return templates.TemplateResponse(request, "index.html", ctx, status_code=422)

    filename = _filename_for_download()

    if hx:
        token = str(uuid4())
        _pdf_cache[token] = pdf_bytes
        resp = Response(status_code=204)
        resp.headers["HX-Redirect"] = str(request.url_for("download_pdf", token=token))
        return resp

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/download/{token}")
async def download_pdf(request: Request, token: str) -> Response:
    pdf_bytes = _pdf_cache.pop(token, None)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="Download expired or invalid link.")
    filename = _filename_for_download()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
