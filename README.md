# AI-Based Engineering Drawing Analysis & Automated Report Generation

An industrial-grade system that accepts engineering drawing PDFs or images, analyzes every page, extracts technical information, understands engineering symbols and relationships, validates extracted values using deterministic rules, and generates professional engineering analysis reports.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        React + TypeScript UI                     │
│   Upload │ Page Preview │ Data Tables │ Issues │ JSON │ Reports  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ REST API
┌────────────────────────────▼─────────────────────────────────────┐
│                        FastAPI Backend                            │
│   /api/upload  /api/analyze  /api/results  /api/reports          │
└────────┬───────────┬──────────────┬──────────────┬───────────────┘
         │           │              │              │
┌────────▼──┐ ┌──────▼─────┐ ┌─────▼────┐ ┌──────▼──────┐
│  Pipeline │ │   Rule     │ │ Database │ │   Report    │
│  Engine   │ │   Engine   │ │ (SQLite) │ │  Generator  │
│           │ │            │ │          │ │             │
│ DocProc ──┤ │ Dimensions │ │ Storage  │ │  PDF        │
│ OCR    ───┤ │ Tolerances │ │ Query    │ │  Excel      │
│ VLM    ───┤ │ Holes      │ │ History  │ │  JSON       │
│           │ │ GD&T       │ │          │ │             │
│           │ │ Welding    │ │          │ │             │
│           │ │ Materials  │ │          │ │             │
│           │ │ Cross-page │ │          │ │             │
└───────────┘ └────────────┘ └──────────┘ └─────────────┘
```

## Key Design Principles

- **Traceability**: Every extracted item carries `id`, `value`, `category`, `page_number`, `confidence`, `bounding_box`, `source_type`, and `source_text`
- **AI vs Fact Separation**: VLM outputs are clearly tagged with disclaimers; deterministic validation is never performed by AI
- **No Hallucination**: The system never invents dimensions, tolerances, or specifications; unverifiable data is flagged
- **Modular Architecture**: Each module (OCR, VLM, Rule Engine, Database, Reports) is independent and swappable
- **YOLO11-Ready**: Architecture supports custom YOLO11 object detection for welding symbols, GD&T, holes, and annotations

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| PDF Processing | PyMuPDF (fitz) |
| Image Processing | OpenCV |
| OCR | PaddleOCR |
| AI Reasoning | Gemini 2.5 Pro |
| Validation | Deterministic Python Rule Engine |
| Database | SQLite |
| Backend API | FastAPI + Uvicorn |
| Frontend UI | React 18 + TypeScript + Vite |
| Report PDF | ReportLab |
| Report Excel | openpyxl |

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- Gemini API Key (for AI reasoning layer)

### 1. Clone and configure

```bash
cd "Dimension Indicator"
cp .env.example .env
```

Edit `.env` and set your `GEMINI_API_KEY`.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Start the backend

```bash
python run.py
```

Backend runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### 5. Start the frontend

```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173` and proxies API requests to the backend.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | System health + OCR/VLM availability |
| `POST` | `/api/upload` | Upload a PDF or image |
| `POST` | `/api/analyze/{doc_id}` | Run full analysis pipeline |
| `GET` | `/api/progress/{doc_id}` | Get analysis progress |
| `GET` | `/api/results/{doc_id}` | Full analysis results |
| `GET` | `/api/results/{doc_id}/summary` | Extraction summary |
| `GET` | `/api/results/{doc_id}/page/{num}` | Single page results |
| `GET` | `/api/results/{doc_id}/items` | Filter extracted items |
| `GET` | `/api/results/{doc_id}/issues` | Detected issues |
| `GET` | `/api/results/{doc_id}/validation` | Validation result |
| `GET` | `/api/reports/{doc_id}/pdf` | Download PDF report |
| `GET` | `/api/reports/{doc_id}/excel` | Download Excel report |
| `GET` | `/api/pages/{doc_id}/{num}` | Rendered page image |
| `GET` | `/api/history` | List previous analyses |
| `DELETE` | `/api/history/{doc_id}` | Delete an analysis |

## Extracted Data Categories

| Category | Description |
|----------|-------------|
| Drawing Info | Drawing number, revision, title, scale, author, date |
| BOM / Parts | Part numbers, descriptions, quantities, materials |
| Dimensions | Linear, angular, radial, diameter values with units |
| Tolerances | Upper/lower limits, fit classes, tolerance zones |
| Holes | Type, diameter, depth, thread spec, quantity |
| Welding | Type, size, length, joint type, arrow/other side |
| GD&T | Characteristic, tolerance value, datums, modifiers |
| Datums | Labels, types, feature descriptions |
| Surface Finish | Roughness value, unit, manufacturing method |
| Material | Spec, name, grade, condition, standard |
| Manufacturing Notes | Numbered notes with type classification |
| Section Views | Labels, cut lines, view directions |
| Detail Views | Labels, scales, descriptions |
| Critical Characteristics | Safety, functional, regulatory flags |

## Engineering Rule Engine

The deterministic rule engine validates extracted data using 8 rule categories:

1. **Dimension Validation** — Negative values, missing nominal, tolerance bounds consistency
2. **Tolerance Validation** — Fit class verification, upper < lower detection, computed vs stated limit mismatch
3. **Hole Validation** — Invalid diameter/depth, blind holes without depth, tapped holes without thread spec
4. **GD&T Validation** — Unknown characteristics (ASME Y14.5), negative tolerances, missing datums on position
5. **Welding Validation** — Invalid weld size, missing side indication
6. **Material Validation** — Unknown material standard prefixes
7. **Cross-Page Consistency** — Conflicting metadata, duplicate part numbers
8. **Missing Information** — Dimensions without tolerances, pages without material info

## Report Generation

Three output formats:

### PDF Report
Professional multi-section report with:
- Executive Summary with validation status
- Extraction Summary table
- Drawing Information, BOM, Dimensions, Holes, Welding, GD&T, Surface Finish, Manufacturing Notes
- Issues and Warnings table with severity
- AI Interpretation section with disclaimer
- Final Engineering Summary

### Excel Report
Multi-sheet workbook with separate sheets for:
Summary, Dimensions, Holes, Welding, GD&T, Issues

### JSON Export
Complete structured data export with full traceability metadata.

## Future Enhancements

- **Custom YOLO11 Model**: Train on engineering drawing datasets for welding symbols, GD&T frames, hole callouts, and surface finish symbols
- **Multi-language OCR**: Extend PaddleOCR for non-English drawings
- **Batch Processing**: Process multiple drawings in parallel
- **On-Premise Deployment**: Docker containerization with GPU support
- **Database Migration**: Upgrade from SQLite to PostgreSQL for production
- **User Authentication**: Role-based access control for sensitive engineering data

## Project Structure

```
Dimension Indicator/
├── .env                              # Environment variables
├── .env.example                      # Environment template
├── requirements.txt                  # Python dependencies
├── run.py                            # Entry point
├── app/
│   ├── config.py                     # Settings management
│   ├── models/
│   │   ├── schemas.py                # 20+ Pydantic data models
│   │   └── database.py               # SQLite CRUD operations
│   ├── pipeline/
│   │   ├── document_processor.py     # PDF/Image → processed images
│   │   ├── ocr_engine.py             # PaddleOCR text extraction
│   │   ├── vlm_engine.py             # Gemini 2.5 Pro reasoning
│   │   └── orchestrator.py           # Pipeline coordinator
│   ├── engine/
│   │   └── rule_engine.py            # Deterministic validation
│   └── backend/
│       ├── api.py                    # FastAPI REST endpoints
│       └── report_generator.py       # PDF/Excel/JSON reports
├── frontend/                         # React + TypeScript
│   ├── src/
│   │   ├── types/index.ts            # TypeScript interfaces
│   │   ├── services/api.ts           # API client
│   │   ├── components/               # UI components
│   │   └── pages/                    # Page views
│   └── ...
├── models/yolov11/                   # YOLO11 model placeholder
├── uploads/                          # Uploaded drawings
└── output/                           # Generated reports
```

## License

Internal use. For questions or issues, refer to the project repository.
