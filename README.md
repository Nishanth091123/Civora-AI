# Civora AI

**Construction estimating workspace for homes and small buildings.**
Give Civora a drawing, or just the built-up area, and it works out the materials, steel, cost, BOQ, bar bending schedule, reinforcement sketches and reports, in English or Tamil, for a team of owners, engineers, colleagues, dealers and customers.

![Dashboard](docs/screenshots/01_dashboard.png)

> **Planning aid only.** Structural output is labelled **DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED** until a licensed engineer approves the design. Civora does not certify compliance with any code.

## What it does

| Area | What you get |
|---|---|
| **Quick Estimate** | Type the built-up area and floors (e.g. 1,000 sq.ft, G+1) and get cement bags, steel, bricks, RMC, sand, tiles, paint and cost in one step |
| **Smart Estimate** | Upload a plan (PDF, DXF, PNG or JPG). Civora reads what it can and asks only for the missing measurements |
| **Rate Master** | Your own local prices; every new estimate is priced with them |
| **Cost & BOQ** | Cost by construction stage, every material with how it was worked out, revisions, double-counting alerts |
| **Structural Studio** | Footings, columns, beams and slabs with concrete, formwork and steel checks |
| **Reinforcement details** | Where the rods go, bend and lap: footing, column, beam and slab sketches and a printable site detail sheet |
| **BBS Studio** | Bar bending schedule and the steel order list by diameter |
| **Reports Center** | Excel and PDF BOQ, structural reports, printable project summary, Download all (ZIP) |
| **Team** | Owner, Engineer, Colleague, Dealer and Customer roles, invite links, activity, engineer sign-off |
| **Stored data** | Every saved item in one place with Delete; delete a whole project with a backup made first |
| **Move my data** | Download your projects as one file and upload them into another Civora (PC to online) |
| **Tamil interface** | Menus, headings, buttons and material names in Tamil; numbers and site terms stay as they are |
| **Multi-drawing analysis** | Upload ground floor, first floor and section sheets together (multi-page PDFs split by page); Civora compares them and makes one combined estimate, each floor on its own size |
| **Vastu guide** | Plot facing + where each room is → ideal / acceptable / avoid, score, suggestions and the ideal layout (English + Tamil) |
| **Rate per sq.ft** | Type today's rate (e.g. ₹2,500 / sq.ft) next to any total: area × rate, compared with the detailed BOQ |
| **PostgreSQL** | Online data in Neon / Supabase PostgreSQL (SQLite stays for the PC); `migrate_to_postgres.py` copies PC data online |
| **Preview → Save → Delete** | Every calculation is shown first; nothing is stored until you press Save, and a Delete button sits next to every saved result |
| **Vastu from a drawing** | Upload a plan: room names are read with their positions, you say which side is North, Civora checks every room |
| **Sample drawings** | `sample_drawings/Civora_Sample_Estimate_Plan` (material estimate) and `Civora_Sample_Vastu_Plan` (Vastu) in PDF, PNG and DXF |

## Owner, users and data safety (v3.8.0)
- **Six sections:** Home · Projects · Estimate · Structure · Guide · More. Every tool lives inside one of them.
- **Site owner:** the username in `CIVORA_OWNER` (default `nishanth_s`). Sees and opens every project; nobody else can delete anything in the owner's projects. More → **Users & activity**: each user's projects, estimates, features used, working hours and audit trail; delete a user to the Recycle Bin or permanently. Everyone else registers directly as an engineer.
- **Recycle Bin:** every delete goes to More → Recycle Bin first. Anything can be restored; only the site owner deletes permanently. Nothing is deleted automatically.
- **Rate Master:** Tamil Nadu average market prices filled in; every value editable.
- **Structure:** 48 element types (piles, pile caps, strip footings, circular columns, ring beams, flat / sunken / cantilever slabs, stairs, tanks, lift pit …).
- **Guide:** Vastu guide, IS code guide, how-to, sample drawings.

## Screens

| | |
|---|---|
| ![Quick estimate](docs/screenshots/02_quick_estimate.png) Quick estimate | ![Drawing Studio](docs/screenshots/03_drawing_studio.png) Drawing Studio |
| ![Cost and BOQ](docs/screenshots/04_cost_and_boq.png) Cost & BOQ | ![Structural Studio](docs/screenshots/05_structural_studio.png) Structural Studio |
| ![Reinforcement detail](docs/screenshots/06_reinforcement_detail.png) Reinforcement detail | ![BBS Studio](docs/screenshots/07_bbs_studio.png) BBS Studio |
| ![Reports](docs/screenshots/08_reports_center.png) Reports Center | ![Team](docs/screenshots/09_team_roles.png) Team and roles |
| ![Stored data](docs/screenshots/10_stored_data.png) Stored data | ![Tamil](docs/screenshots/11_tamil_interface.png) Tamil interface |

## Run on your PC (Windows)
```
cd /d C:\Civora_AI
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-app.txt
run.bat
```
Open http://127.0.0.1:8000. Your database, uploads and login key live in `data\` and are never committed to GitHub.

## Put it online
- **Render (full app):** this repo has a `Dockerfile` and `render.yaml`. On Render choose **New → Blueprint**, pick this repo and click **Apply**.

### Keep your data safe on Render – PostgreSQL (v3.7.0, recommended)
1. Create a free PostgreSQL database at **neon.tech** (region: Asia Pacific / Singapore). Copy the connection string `postgresql://USER:PASSWORD@HOST/DB?sslmode=require`.
2. Render → civora-ai → **Environment** → add `DATABASE_URL` = that string → **Save** (Render redeploys).
3. Civora → Advanced tools → **Data storage** must say **PostgreSQL database**.
4. Copy your PC data online once (optional):
```
cd /d C:\Civora_AI
set DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
.venv\Scripts\python.exe migrate_to_postgres.py
```
Users, logins, projects, estimates **and drawing files** are all stored in PostgreSQL, so restarts and redeploys lose nothing. On the PC, without `DATABASE_URL`, Civora keeps using the SQLite file as before.

### Older option: GitHub cloud backup (v3.6.0)
Render's free plan has **no permanent disk**: every restart, sleep or redeploy starts a fresh server and deletes `data\` (users, logins, projects, drawings). Turn on the free cloud backup once:
1. GitHub → **New repository** → name `civora-data`, **Private**, tick *Add a README*.
2. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate. Repository access: only `civora-data`. Permissions → **Contents: Read and write**. Copy the token.
3. Render → civora-ai → **Environment** → add
   `CIVORA_BACKUP_REPO` = `Nishanth091123/civora-data`, `CIVORA_BACKUP_TOKEN` = the token, `CIVORA_SECRET_KEY` = any long random text → **Save**.
4. Open **Advanced tools → Data storage** in Civora: it must say **Cloud backup on**.

Civora then restores the latest backup at start-up, saves a snapshot within ~30 seconds of every change, and once more when Render shuts the server down. Each save is a git commit, so old versions can be recovered from the repo history. Drawing files over 25 MB in total are left out of the backup (`CIVORA_BACKUP_UPLOADS_MB` to change).
Paid alternative: Render disk mounted at `/app/data` + `CIVORA_DATA_DIR=/app/data/civora`.
- **Streamlit (Civora AI Lite):** `streamlit_app.py` runs Quick Estimate on Streamlit Community Cloud with the same calculation engine. Main file path: `streamlit_app.py`.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for step-by-step use.

## Tests
```
.venv\Scripts\python.exe run_tests.py
```
The app tests run on a temporary copy; your real database is never touched.

## Built with
FastAPI · SQLite · openpyxl · ReportLab · PyMuPDF · ezdxf · OpenCV · Tesseract OCR

Built by Nishanth S.
