# AI Engineering Drawing Analysis & Automated Excel Report Generator

Upload an engineering drawing PDF, enter your part data, and get a formatted
Excel report. Every page of the drawing is analysed — not just the first — and
every value written to the report can be traced back to the page it came from.

The report always has the same ten columns, in the same order, whatever the
drawing contains:

| S No | PART NO | DESCRIPTION | DWG NO | WEIGHT (IN KG) | THICKNESS | PROCESS | LENGTH (mm) | WIDTH (mm) | HEIGHT (mm) |
| ---- | ------- | ----------- | ------ | -------------- | --------- | ------- | ----------- | ---------- | ----------- |

**You do not have to type any of it.** Leave the input grid empty and the
drawing identifies its own parts: from a parts-list table if it has one,
otherwise from the title block.

It is not tuned to any one company's drawing style. Column headings, part-number
formats, units and process names all vary by supplier, and the report carries
whatever the drawing actually says.

---

## Quick start

**One command.** From the project folder:

```bash
.venv\Scripts\python.exe run.py
```

or, with the virtualenv activated:

```bash
.venv\Scripts\activate      # Windows
python run.py
```

Then open **<http://localhost:8000>**.

First time only:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env       # then set GEMINI_API_KEY in .env
```

That is the whole application. It is served by FastAPI directly — **there is no
npm step, no build, and no second server**. Do not open port 5173; that is the
old React app and it has no part-report screen. See
[Troubleshooting](#troubleshooting).

> **Restarting matters.** The server loads your code at startup. If you changed
> anything — or if the columns look wrong — stop it with **Ctrl+C in the terminal
> where you launched it** and run it again. A server left running from an earlier
> session keeps serving the old code, and Windows will report the port as busy
> even after the process is gone.

### Prerequisites

- Python 3.10+
- A Gemini API key — free from <https://aistudio.google.com/apikey>

Without a key the app still starts and still produces a valid Excel file, but
every column will contain only what you typed; nothing is read from the drawing.
The banner across the top of the page always tells you which capabilities are
actually live.

---

## Using it

The interface is one page, in seven steps:

| # | Step | Notes |
| - | ---- | ----- |
| 1 | **Upload** | Drag in a PDF (or PNG/JPG/TIFF). It reports the page count so you can confirm all pages will be read. |
| 2 | **Input Data** | **Optional.** Leave the grid empty to read the parts list off the drawing. Fill rows in only to override what the drawing says — on any row you do fill in, **PART NO is required**, because it is how drawing data is matched to that row. |
| 3 | **Analyze Drawing** | Disabled until the input is valid, and it tells you exactly what is missing. |
| 4 | **Progress** | Live stage and page counter. A multi-page drawing takes a while — roughly 15 s per page. |
| 5 | **Extracted Drawing Information** | Everything read off the drawing, filterable by category, with page and confidence. |
| 6 | **Final Report Preview** | The exact ten columns that will be written, colour-coded by where each value came from. |
| 7 | **Download Excel Report** | Generates and downloads the `.xlsx`. |

### Two ways to run it

| Grid | What happens |
| --- | --- |
| **Empty** | *Discovery mode.* The drawing supplies its own rows. Zero typing. |
| **Filled** | *Supplied mode.* Your rows define the report exactly. The drawing never adds rows you did not ask for, and your typed values always win. |

Discovery never silently mixes with your input: if you type even one row, the
report contains exactly the rows you typed.

In discovery mode the rows come from the first of these that exists:

| Drawing has | Rows come from |
| --- | --- |
| A parts list / BOM / item list | Every row of that table, in table order |
| No parts list, one part per sheet | The title block of each sheet |
| Neither | Nothing — you are asked to enter a PART NO |

**Whatever names the table uses.** PARTS LIST, BILL OF MATERIALS, BOM, ITEM
LIST, STÜCKLISTE — and columns headed S.NO, SL, ITEM, POS, PART NO, PART CODE,
MATERIAL NO, DRAWING NUMBER, DWG NO, ZEICHNUNG. Matching is on meaning, not on
exact heading text, and the table can sit anywhere on the sheet.

On an assembly sheet the title block names the *assembly*, so it is deliberately
never used to fill a component's description or drawing number.

### How each cell is decided

Leave a field blank to have the drawing fill it in. Anything you type is kept
exactly as entered.

| Situation | What lands in the Excel cell | Shading |
| --- | --- | --- |
| You typed a value, drawing silent | your value | none |
| You typed a value, drawing agrees | your value | none (green text) |
| You typed a value, **drawing disagrees** | **your value** | amber + warning |
| You left it blank, drawing has it (confidence ≥ threshold) | drawing value | green |
| You left it blank, drawing value is low-confidence | `Not Detected` | red |
| Nobody has it | `Not Detected` | red |

**A value you type is never overwritten.** A disagreement is surfaced three
ways — an on-screen warning, an amber cell with a hover comment, and a row on
the Traceability sheet — but the report keeps what you entered. Blank cells are
the only ones the drawing may fill, and only above
`DIMENSION_CONFIDENCE_THRESHOLD` (default `0.4`).

### Why it says "Not Detected" instead of guessing

Preventing invented engineering values matters more than filling every cell, so
this is enforced in three places rather than by prompt wording alone:

1. The model must quote the text it read off the drawing (`source_text`) to
   support any value. A value it cannot quote is capped at 0.35 confidence.
2. Anything below `DIMENSION_CONFIDENCE_THRESHOLD` is reported as
   `Not Detected` rather than written to the report — but it is still recorded
   on the Traceability sheet, so you can see what was considered and rejected.
3. Agreement across pages can raise confidence slightly, but the bonus is
   capped so corroboration alone can never push a weak reading over the line.

`Not Detected` is the system working, not failing.

#### Units

Values are reported in the units the report headers state. Where the drawing
uses something else **and prints the unit**, it is converted — `1.85 LB` becomes
`0.839` in WEIGHT (IN KG), `8.50 IN` becomes `215.9` in LENGTH (mm) — and the
original text is kept in the Traceability sheet and the cell comment.

If a number is printed with no unit anywhere on the drawing, it is reported as
printed. Nothing is converted on an assumption.

#### Assembly sheets vs detail sheets

On an **assembly** drawing the BOM gives you PART NO, DESCRIPTION and DWG NO for
every component, but the sheet does not state each component's weight,
thickness, process or overall size — those live on the individual **detail**
sheets. So a single assembly page legitimately yields `Not Detected` in those
columns.

If your drawing set is a multi-sheet PDF (`Sheet 1/4`, `2/4`, …), upload the
**whole PDF**. Every page is analysed and evidence is merged per part, so the
detail sheets fill in what the assembly sheet cannot.

### Multi-part drawings

Add one row per part. Drawing information is matched to rows by Part No,
ignoring case and punctuation — `BR-1042`, `BR1042` and `br 1042` are treated as
the same part.

Data found for a part number you did not supply is **never** merged into another
row. It is listed separately as unattributed, both on screen and on the Drawing
Information sheet. Duplicate part numbers are rejected before analysis starts,
because they would make attribution ambiguous.

---

## The Excel workbook

| Sheet | Contents |
| --- | --- |
| **Report** | The ten fixed columns. Title block, frozen header row, autofilter, borders, banded rows, landscape fit-to-width. Numeric cells are stored as real numbers with unit-suffixed formats, so they sort and calculate correctly. |
| **Traceability** | Every cell: reported value, source, status, what you entered, what the drawing showed, page numbers, confidence, and an explanation. |
| **Drawing Information** | Everything read off the drawing — dimensions, tolerances, holes, welds, GD&T, datums, surface finishes, materials, notes, views — with page and confidence. |
| **Analysis Log** | Per page: OCR engine, regions found, characters read, whether the vision model ran, items found, part numbers seen, time, and any error. |

Hover any shaded cell on the Report sheet for its page reference and confidence.

### One Excel format everywhere

Both export endpoints write the same ten columns:

| Endpoint | Source of values |
| --- | --- |
| `/api/part-report/excel/{job_id}` | Your typed input + the drawing. **Use this one.** |
| `/api/reports/{document_id}/excel` | Drawing only — the analysis-only path used by the old React UI. It has no input form, so S No is auto-numbered and anything the drawing does not state reads `Not Detected`. |

The projection for the second path lives in `app/backend/legacy_adapter.py`. It
never back-fills a missing field from an unrelated dimension on the sheet.

---

## Troubleshooting

### I see nothing / "not found" / no output after clicking Analyze

Check the address bar. If it says **:5173** you are on the old React app, which
has no input grid and no part report. Go to **<http://localhost:8000>**.

If you are on :8000 and the columns look wrong (`S.No`, `Part No`, … instead of
`S No`, `PART NO`, `DWG NO`, …), the server is running old code. Stop it with
Ctrl+C in its terminal and start it again. Confirm with:

```bash
curl http://localhost:8000/api/part-report/capabilities
```

The `report_columns` it prints are the ones the running server will produce.

### Port 8000 is busy but nothing seems to be running

A force-killed server can leave the socket held on Windows. Close the terminal
window you launched it from. If that fails, either change `API_PORT` in `.env`
or sign out and back in.

### `[vite] http proxy error: /api/upload` — `AggregateError [ECONNREFUSED]`

You are running the old React dev server (`npm run dev`, port 5173), which
proxies `/api` to port 8000 — and nothing is listening there.

**This workflow does not use Vite.** Stop that server, run `python run.py`, and
open <http://localhost:8000> — not 5173.

### The app runs but nothing comes back from the drawing

Check the banner at the top of the page, or:

```bash
curl http://localhost:8000/api/part-report/capabilities
```

`vlm_available: false` means the vision model is not configured — see below.

### `404 ... model gemini-2.5-pro is no longer available to new users`

Google retires model names and restricts older ones to existing keys, so a key
that authenticates perfectly can still 404 on a model. The default is
`gemini-pro-latest`, an alias that tracks the current Pro model. To see exactly
what your key can reach:

```bash
python -m app.pipeline.gemini_client
```

It prints your configured model, whether it is available, and the full list. Set
`GEMINI_MODEL` in `.env` to any name from that list.

### Every column reads "Not Detected"

Either no API key is configured, or the drawing genuinely does not state those
values. Check the **Analysis Log** sheet — it records, per page, whether the
vision model ran and what it found.

### Uploading through the React UI produces the wrong-looking report

The React app at port 5173 has no input form for the nine fields and calls the
analysis-only endpoints. Use <http://localhost:8000>.

---

## Where your API key goes

| File | Committed to git? | Put your key here? |
| --- | --- | --- |
| `.env` | **No** — gitignored | **Yes.** This is the only file the app reads. |
| `.env.example` | **Yes** | **Never.** Placeholders only, so others know what to fill in. |

A key placed in `.env.example` gets published the moment you commit. If that
happens, revoke it at <https://console.cloud.google.com> — deleting the line
afterwards does not un-leak it, because it stays in git history.

---

## Configuration

All settings live in `.env` (see `.env.example`). The ones that matter:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | *(none)* | Required for any drawing analysis. |
| `GEMINI_MODEL` | `gemini-pro-latest` | Alias that tracks the current Pro model. |
| `GEMINI_TEMPERATURE` | `0.1` | Low, deliberately — this is extraction, not writing. |
| `DIMENSION_CONFIDENCE_THRESHOLD` | `0.4` | Below this, a drawing value is reported as `Not Detected`. Raise it to be stricter. |
| `PDF_RENDER_DPI` | `300` | Higher reads small annotation text better but is slower per page. |
| `OCR_MAX_IMAGE_SIZE` | `2048` | Long edge PaddleOCR sees. **Do not raise this far.** Its inference backend aborts the whole process on very large inputs — a 300 DPI sheet at 4096 px crashes it outright, while 2560, 2048 and 1600 all succeed and return the same region count. Boxes are scaled back to page coordinates afterwards, so nothing is lost. |
| `MAX_IMAGE_SIZE` | `4096` | Long-edge cap. A 300 DPI A1 sheet renders to ~10 000 px; without this the filters take minutes per page. |
| `API_PORT` | `8000` | Port the whole application is served on. |
| `DEBUG` | `true` | Enables uvicorn auto-reload. Set `false` in production. |
| `REPORT_COMPANY_NAME` | `Engineering Analysis System` | Printed in the Excel title block. |
| `YOLO_ENABLE_CUSTOM` | `false` | See [custom symbol detection](#custom-yolo11-symbol-detection). |

---

## How it works

```
                    ┌──────────────────────────────┐
   drawing.pdf ────▶│  DocumentProcessor (PyMuPDF) │  render every page @ 300 DPI
   + your part rows └──────────────┬───────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │                              │
             clean render                  preprocessed (OpenCV)
             (for the VLM)                 CLAHE → median → threshold
                    │                              │
                    │                     ┌────────▼────────┐
                    │                     │   OCREngine     │  PaddleOCR, or the
                    │                     │  reading order  │  PDF text layer
                    │                     └────────┬────────┘
                    │                              │
              ┌─────▼──────────────────────────────▼─────┐
              │           PartExtractor (Gemini)         │  per page:
              │   image + OCR text + your part list      │  evidence + findings
              └─────────────────────┬────────────────────┘
                                    │
              ┌─────────────────────▼────────────────────┐
              │              ReportResolver              │  merge evidence across
              │    user value wins · blanks filled ·     │  pages, decide each cell
              │    low confidence → "Not Detected"       │
              └─────────────────────┬────────────────────┘
                                    │
              ┌─────────────────────▼────────────────────┐
              │            ExcelReportWriter             │  4 sheets, fixed headers
              └──────────────────────────────────────────┘
```

Two renderings of each page are kept deliberately. The vision model gets the
**clean** render: binarising or sharpening a drawing before sending it to a VLM
destroys thin extension lines, centre lines and light GD&T glyphs — exactly the
detail it is being asked to read. The OCR detector gets the preprocessed one,
tuned for line drawings rather than photographs of documents.

### Module map

```
app/
├── config.py                      settings, loaded from .env
├── models/
│   ├── part_schemas.py            the fixed ten-column contract + provenance types
│   ├── schemas.py                 legacy extraction models (20+ item types)
│   └── database.py                SQLite storage for legacy analyses
├── pipeline/
│   ├── document_processor.py      PDF/image → clean + preprocessed page renders
│   ├── ocr_engine.py              PaddleOCR (2.x and 3.x) with a PDF-text fallback
│   ├── gemini_client.py           SDK-agnostic Gemini wrapper; also a CLI model lister
│   ├── part_extractor.py          per-page extraction + part attribution
│   ├── part_pipeline.py           the orchestration above — every page, no early exit
│   ├── symbol_detector.py         YOLO11 hook (inert until weights are supplied)
│   ├── vlm_engine.py              legacy VLM layer
│   └── orchestrator.py            legacy pipeline coordinator
├── engine/
│   ├── report_resolver.py         the cell-decision policy
│   └── rule_engine.py             legacy deterministic validation
├── backend/
│   ├── api.py                     FastAPI app, serves the UI at /
│   ├── part_routes.py             the part-report REST API
│   ├── excel_report.py            the four-sheet workbook writer
│   ├── legacy_adapter.py          projects a legacy analysis onto the ten columns
│   └── report_generator.py        legacy PDF/JSON reports
└── ui/                            the interface — plain HTML/CSS/JS, no build step
    ├── index.html
    ├── styles.css
    └── app.js

tests/test_part_report.py          26 tests, run offline with no API key
frontend/                          legacy React app (optional, not required)
```

---

## API

### Part report — the main workflow

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/part-report/capabilities` | What the server can do right now |
| `POST` | `/api/part-report/upload` | Upload a drawing → `document_id` + page count |
| `POST` | `/api/part-report/analyze` | Start analysis → `job_id`. Send `"parts": []` for discovery mode. |
| `GET` | `/api/part-report/progress/{job_id}` | Stage, percentage, current page |
| `GET` | `/api/part-report/result/{job_id}` | Table, findings, warnings, stats |
| `GET` | `/api/part-report/excel/{job_id}` | Download the `.xlsx` |
| `GET` | `/api/part-report/page-image/{document_id}/{page}` | Rendered page PNG |
| `DELETE` | `/api/part-report/job/{job_id}` | Discard a job and its cached result |

Analysis runs on a worker thread and the client polls `/progress`. Results are
also cached to `output/results/{job_id}.json`, so a finished report survives a
server restart.

Example:

```bash
DOC=$(curl -s -F "file=@drawing.pdf" \
      http://localhost:8000/api/part-report/upload | jq -r .document_id)

JOB=$(curl -s -X POST http://localhost:8000/api/part-report/analyze \
      -H "Content-Type: application/json" \
      -d "{\"document_id\":\"$DOC\",
           \"parts\":[{\"s_no\":\"1\",\"part_no\":\"BR-1042\",\"thickness\":\"6\"}]}" \
      | jq -r .job_id)

curl -s "http://localhost:8000/api/part-report/progress/$JOB"
curl -s -o report.xlsx "http://localhost:8000/api/part-report/excel/$JOB"
```

### Legacy analysis endpoints

Used by the optional React app. Full drawing catalogue, no input form.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/upload` · `/api/analyze/{id}` | Upload and analyse |
| `GET` | `/api/progress/{id}` · `/api/results/{id}` | Progress and full result |
| `GET` | `/api/results/{id}/items` · `/issues` · `/validation` · `/json` · `/dcl` | Filtered views |
| `GET` | `/api/reports/{id}/excel` · `/pdf` | Reports (Excel uses the ten fixed columns) |
| `GET` | `/api/history` · `DELETE /api/history/{id}` | Stored analyses |
| `GET` | `/api/health` · `/api/status` | Service state |

Interactive docs: <http://localhost:8000/docs>

---

## Tests

```bash
python tests/test_part_report.py     # or: pytest tests/test_part_report.py
```

26 tests. The vision model is stubbed, so they run offline with no API key and
no cost. They cover the cell-decision policy, full multi-page traversal,
cross-page evidence merging, part matching across punctuation, discovery from
an empty grid, the title-block fallback for drawings with no parts list, the
guarantee that supplied rows are never joined by discovered ones, the guarantee
that findings are never mixed between parts, the fixed header contract, numeric
formatting, graceful degradation without a key, and a full API round trip.

---

## Optional extras

### OCR for scanned drawings

PaddleOCR is not installed by default — it is a large download. Without it the
app reads the PDF's own vector text layer, which is *exact* for CAD-exported
drawings: those are the glyphs the CAD package wrote, not a recognition guess.
It only comes up empty for scanned or image-only pages.

Install it if you process scanned drawings:

```bash
pip install paddlepaddle paddleocr
```

Both the 2.x and 3.x APIs are supported; the correct one is detected at runtime.
The Analysis Log sheet records which engine actually read each page.

Pages are downscaled to `OCR_MAX_IMAGE_SIZE` before detection, because
PaddleOCR's backend crashes the process on full-resolution 300 DPI sheets.
Detected boxes are scaled back to page coordinates, so the downscale affects
only what the detector sees, not what is reported.

### Custom YOLO11 symbol detection

For drawing objects OCR cannot read and a VLM localises only loosely — GD&T
feature control frames, welding symbols, hole callouts, datum triangles, section
markers.

```bash
pip install ultralytics
# in .env:
#   YOLO_ENABLE_CUSTOM=true
#   YOLO_MODEL_PATH=models/yolov11/best.pt
```

Map your trained class names to finding categories in `CLASS_TO_CATEGORY` in
`app/pipeline/symbol_detector.py`. No other code changes are needed — the
pipeline already calls the detector for every page and merges what it returns
into the findings. Until weights exist it returns nothing rather than
fabricating boxes.

### The legacy React UI

Optional, and not required for anything above.

```bash
cd frontend && npm install && npm run dev     # needs python run.py already running
```

It provides the drawing-catalogue views (dimension control list, issues, JSON
inspector) but has no input form for the ten fixed columns.

---

## Tech stack

| Component | Technology |
| --- | --- |
| Language | Python 3.10+ |
| PDF rendering | PyMuPDF |
| Image processing | OpenCV |
| OCR | PaddleOCR (optional) · PDF text layer fallback |
| Vision model | Gemini via `google-genai` |
| Excel | pandas + openpyxl |
| API | FastAPI + Uvicorn |
| Interface | Plain HTML/CSS/JS, served by FastAPI |
| Symbol detection | Ultralytics YOLO11 (optional) |
| Storage | SQLite + JSON result cache |

---

## What the drawing analysis extracts

Beyond the nine report columns, everything below is captured on the **Drawing
Information** sheet with page number and confidence:

| Category | Examples |
| --- | --- |
| Dimensions | Linear, angular, radial, diameter, with units |
| Tolerances | Upper/lower limits, fit classes, general tolerance blocks |
| Holes | Type, diameter, depth, thread spec, quantity |
| Welding | Type, size, joint type, arrow/other side |
| GD&T | Characteristic, tolerance value, datum references, modifiers |
| Datums | Labels, types, feature descriptions |
| Surface finish | Roughness value and unit, method |
| Material | Spec, name, grade |
| Manufacturing notes | Numbered notes, general notes |
| Views | Section and detail markers, scales |
| Title block | Drawing number, revision, title, scale, author, date |
| BOM | Part numbers, descriptions, quantities, materials |

---

## Known limitations

- **Accuracy depends on the drawing.** Faint scans, hand annotation and dense
  title blocks all reduce confidence, which means more `Not Detected` — by
  design, rather than a wrong value.
- **Overall dimensions are the hardest field.** If the drawing states no overall
  or stock size, the system will not derive one from feature dimensions.
- **An assembly sheet alone cannot fill every column.** Per-part weight,
  thickness, process and size live on the detail sheets — upload the complete
  multi-sheet PDF, not just the assembly page.
- **A drawing that states nothing states nothing.** If a sheet never prints a
  process or a thickness, those columns read `Not Detected` no matter how the
  drawing is laid out. The system reads; it does not estimate.
- **Throughput is roughly 15 s per page**, dominated by the vision model call.
  Pages are processed sequentially.
- **Weight is converted only when a unit is printed.** A bare number is reported
  as-is, never assumed to be kilograms.

## Roadmap

- Trained YOLO11 weights for GD&T, welding and hole symbols
- Parallel page processing
- Batch upload across multiple drawings
- Non-English OCR
- Docker packaging with GPU support

## License

Internal use.
