# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Prism Portal** is an AI-powered inventory management & business intelligence ERP system. It tracks product inventory, distributor sales, and provides predictive analytics.

## Development Commands

### Running the Backend

```bash
cd backend
python app.py          # Runs Flask dev server on port 5001

```

### Production Server

```bash
cd backend && gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 2
```

### Dependencies

```bash
pip install -r requirements.txt
```

Key packages: Flask 3.1.0, Flask-SQLAlchemy, psycopg2-binary (PostgreSQL), groq (AI), openpyxl (Excel export), gunicorn.

### Environment Setup

Copy and configure `backend/.env` with:
- `DATABASE_URL` — PostgreSQL connection string
- `GROQ_API_KEY` — API key for Groq LLM
- `GROQ_MODEL` — e.g. `openai/gpt-oss-120b`
- `SECRET_KEY`, `FLASK_ENV`, `FLASK_DEBUG`

## Architecture

### Backend (`backend/`)

**Application Factory pattern** — `app.py` calls `create_app()`, registering routes and extensions. Config is loaded from `config.py` based on `FLASK_ENV`.

**Layered structure:**
- `routes.py` — thin API route handlers (14+ endpoints), delegates to services
- `services.py` — all business logic: inventory status, forecasting, distributor analytics, Excel export
- `models.py` — SQLAlchemy ORM models
- `ai_service.py` — Groq LLM integration, builds system snapshot from live DB state
- `extensions.py` — shared SQLAlchemy instance to avoid circular imports

**Database models:**
- `Product` — SKU catalog with stock levels, pricing (revenue + cost), min stock thresholds
- `Distributor` — partner entities with region/tier classification
- `Sale` — immutable ledger of product→distributor transactions; price/cost captured at sale time
- `StockTransaction` — audit log for all inventory changes (SALE, RESTOCK, RETURN, ADJUSTMENT)

**Key API endpoints:**
| Route | Purpose |
|---|---|
| `GET /api/inventory` | Product list with computed stock status |
| `POST /api/sales` | Record sale; atomically deducts stock |
| `POST /api/restock` / `POST /api/adjustment` | Stock operations |
| `GET /api/stats` | Dashboard KPIs |
| `GET /api/analytics/forecast` | 30-day burn rate projections |
| `GET /api/alerts` | Low/critical/OOS stock alerts |
| `GET /api/performance` | Distributor MoM growth & auto-tiering |
| `GET /api/reports/excel` | Download Excel workbook |
| `POST /api/ai/brain` | LLM strategic insights against live data |

**Transaction safety:** Sales use `SELECT ... FOR UPDATE` row-level locking to prevent concurrent stock deductions.

**Forecasting logic:** 30-day burn rate in `services.py` → days-until-OOS projections. Distributor tiers (Gold/Silver/Bronze) are auto-computed from sales volume.

### Frontend

Three standalone HTML files served by Flask routes:
- `dashboard_overview.html` — KPIs, alerts, activity feed, OOS projections
- `inventory_management.html` — product table, stock adjustments, restocking
- `distributor_performance.html` — distributor analytics and tier breakdown

All frontends use **Tailwind CSS** + **Chart.js** + **Material Design Symbols**. No build step — static HTML with CDN imports.

## Design System

Detailed spec in `DESIGN.md`. Key tokens:
- **Primary color:** Deep indigo `#3525cd`
- **Typography:** Manrope (headlines) + Inter (body)
- **Philosophy:** "Digital Gallery" — intentional asymmetry, generous white space, no-border cards, glass morphism effects
- **Spacing:** 7rem margins, `rounded-full`/`rounded-xl` preferred over standard `rounded-lg`

Follow `DESIGN.md` for any UI changes to maintain visual consistency.

## Deployment

Configured for **Heroku** via `Procfile`. PostgreSQL is a remote server (not local). Connection pooling is configured in `config.py` (`pool_pre_ping=True`, `pool_recycle=300`).
