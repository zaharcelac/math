# Grade 1 math worksheet generator

`math_exercises.py` prints randomized arithmetic exercises to the terminal and optionally builds a **US Letter** PDF for printing. Tasks are tuned for early learners: operands and sums/differences stay within bounds you choose.

## Requirements

- **Python 3.9+** (uses `list[str]` style annotations with `from __future__ import annotations` for broader compatibility)
- **PDF output:** [fpdf2](https://pypi.org/project/fpdf2/) and [qrcode](https://pypi.org/project/qrcode/) with Pillow for footer QR codes (see `requirements.txt`)
- **Web UI (optional):** FastAPI, Uvicorn, Jinja2, python-multipart (same `requirements.txt`)

## Install

```bash
pip install -r requirements.txt
```

## Web UI (MVP)

Small browser UI with **FastAPI** and **HTMX**: fill the form, get a PDF download. The CLI below is unchanged for scripts and cron.

From the repository root:

```bash
uvicorn web.app:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 . With JavaScript enabled, validation errors update in place; on success the PDF is returned in the same response (no extra download URL or server-side session). Without JavaScript, submitting the form still returns the PDF as a normal file download.

### Behind a reverse proxy (e.g. Traefik)

The app applies **`ProxyHeadersMiddleware`** so `X-Forwarded-Proto` / `X-Forwarded-For` from the proxy are honored without extra Uvicorn flags. You can tune trust with environment variables:

| Variable | Purpose |
|----------|---------|
| `TRUSTED_PROXY_IPS` | Comma-separated IPs or CIDRs of proxies that may set forwarded headers. Default `*` (trust any direct client—typical in a private Docker network). Tighten in production if the app is reachable without the proxy. |
| `ROOT_PATH` | If the app is mounted under a URL prefix **without** the proxy stripping it (uncommon), set this to that prefix (e.g. `/math`) so OpenAPI and path helpers stay correct. Usually leave unset when Traefik strips the prefix before the request hits Uvicorn. |

No sticky sessions or Traefik-specific download routes are required: PDF bytes are returned directly from `POST /generate`.

## Quick start

```bash
# Text only (default: all exercise types, 12 tasks each, max operand 20)
python3 math_exercises.py

# PDF for printing (default file: output/math_exercises_YYYY-MM-DD_HH-MM.pdf)
python3 math_exercises.py --print

# PDF at an explicit path
python3 math_exercises.py --print -o worksheet.pdf

# Fewer tasks, larger numbers, only addition and subtraction
python3 math_exercises.py --total 10 --max-number 50 --types a s --print
```

## Command-line options

| Option | Meaning |
|--------|---------|
| `--total N` | Number of problems **per selected type** (default: 12). |
| `--max-number N` | No operand or sum/difference may exceed this bound (default: 20). Blanks use as many underscores as there are digits in `N`. |
| `--types TYPE …` | Which exercise kinds to include (default: **all**). Order in the PDF follows the order you list. See [Exercise types](#exercise-types). |
| `--print` | Write a PDF (requires fpdf2). |
| `-o` / `--output PATH` | PDF output path. If omitted with `--print`, default is `output/math_exercises_YYYY-MM-DD_HH-MM.pdf` (local time). The `output` directory is created if needed. |
| `--sheets N` | With `--print`, generate **N** independent worksheets in one PDF (each fully regenerated). Footer shows `TEST i OF N`. Ignored without `--print`. |
| `--seed N` | Fixed RNG seed. With `--print` and multiple sheets, sheet *i* uses seed `N + i`. |

Run `python3 math_exercises.py -h` for built-in help.

## Exercise types

Each type uses `--total` problems. Default order when `--types` is omitted:

| Type key | Abbreviations | Pattern |
|----------|---------------|---------|
| `addition` | `a`, `add` | `a + b = __` |
| `subtraction` | `s`, `sub` | `a - b = __` |
| `addition-missing-first` | `amf`, `am1` | `__ + b = c` |
| `addition-missing-second` | `ams`, `am2` | `a + __ = c` |
| `subtraction-missing-minuend` | `smf`, `sm1`, `smm` | `__ - b = c` |
| `subtraction-missing-subtrahend` | `sms`, `sm2`, `smt` | `a - __ = c` |
| `addition-balance` | `ab`, `balance`, `bal` | `a + b = c + __` (same sum both sides; all values ≤ max-number) |
| `subtraction-balance` | `sb`, `subbalance`, `subbal` | `a - b = c - __` (same difference both sides; all values ≤ max-number) |

Example:

```bash
python3 math_exercises.py --types addition subtraction-missing-minuend --total 8 --print
```

## PDF layout

- **Paper:** US Letter.
- **Font:** Courier; section titles are centered; problems use a **two-column** grid (left column left-aligned, right column right-aligned).
- **Alignment:** Operands and blanks are padded to the width of `--max-number` so `+`, `-`, and `=` line up.
- **Structure:** Each **exercise type** starts on a **new page** within a worksheet.
- **Footer (every page):** centered line of the form  
  `TEST i OF n   MAX-NUMBER …   TOTAL …`  
  where `i`/`n` come from `--sheets`, and the last two fields mirror `--max-number` and `--total`.
- **Footer URL (optional):** when resolved, the URL is appended on the **same** centered line as `TEST … MAX-NUMBER … TOTAL …`, and a **small QR code** is drawn under that line encoding the **same** URL string. Order of precedence: `WORKSHEET_FOOTER_URL`, `PUBLIC_BASE_URL`, the request’s `base_url` (web app), then `DEFAULT_WORKSHEET_FOOTER_URL` in `math_exercises.py`. Env overrides everything else.

With `--print` and `--sheets` greater than 1, stdout shows only the **first** worksheet; the PDF contains all sheets.

## Generation rules

Within each worksheet (one run of `build_sections`):

- **No duplicate** problem strings across all selected types on that sheet.
- At most **about 5%** of problems (per type) may include the **numeric value 0** (values like 10 or 20 do not count as “zero problems”).
- If the constraints cannot be satisfied (e.g. `--total` too large for `--max-number`), the program exits with an error suggesting you relax limits.

## Files

| File | Role |
|------|------|
| `math_exercises.py` | CLI and generator |
| `requirements.txt` | `fpdf2` and `qrcode[pil]` for `--print` (PDF + footer QR) |

## License

Add your license here if applicable.
