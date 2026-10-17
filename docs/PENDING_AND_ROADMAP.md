# Civora AI — status and what is still pending
Version in this bundle: **3.4.0**. Updated 13 Oct 2026.

## Done (v2.5 → v3.3)
| Version | What |
|---|---|
| 2.5 | New interface: dashboard, project workflow, Download All |
| 2.6 | Smart Estimate (drawing → full estimate, only missing values asked), Rate Master |
| 2.7 | Multi-user: owner / engineer / colleague / dealer / customer roles, invite links, activity log, engineer sign-off |
| 2.8 | Quick Estimate from built-up area only (e.g. 1000 sq.ft → materials, cost, workflow) |
| 3.0 | Full redesign: Enterprise Hub + Building Studio + Smart Estimation; portfolio, wizard, workspace, Drawing Studio, Guided / Expert mode |
| 3.1 | Cost & BOQ (Cost Intelligence Center), Structural Studio, BBS Studio |
| 3.2 | Reinforcement detail drawings (footing, column, beam, slab: where rods go, bend, lap), site detail sheet |
| 3.3 | Reports Center (all projects + project documents + printable summary), Tamil interface on main screens |
| 3.4 | Data tab: see everything stored, upload, delete drawings / estimates / elements / bars / takeoffs, delete whole project (backup first), clear rates |

## Pending — your side
1. **Install 3.4 on your PC** and check it with one real project (folder `1_UPDATE_EXISTING_INSTALL`).
2. **GitHub** (`Nishanth091123/Civora-AI` created): upload the contents of `2_FULL_SOURCE\Civora_AI`, or give the Claude GitHub App access to the repo so it can be pushed for you.

## Pending — to build next (suggested order)
| # | Item | Why | Size |
|---|---|---|---|
| 1 | **GitHub upload** | version history, sharing | small (repo created; needs upload or app access) |
| 2 | **Public hosting** — Docker + Render / Railway, PostgreSQL instead of SQLite, file storage for uploads, secret key from environment | a link others can open. Streamlit cannot run this FastAPI app, so it is not used | medium |
| 3 | **Forgot password / reset** (email or admin reset) | needed once other people log in online | small |
| 4 | **Real structural design checks** — bounded RC slab first, then beam, column, footing (the old v2.4 step F) | today Civora gives quantities and typical detailing only; design stays "DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED" and never claims code compliance | large |
| 5 | **Better drawing reading** for scanned PDF / photos (DXF already best) | fewer manual entries | medium |
| 6 | **Notifications** (bell icon is not active yet), invite by WhatsApp / email automatically | team use | small–medium |
| 7 | **Tamil for long messages** (warnings, help text, BOQ basis notes still English) | full Tamil users | small |
| 8 | **Units / theme settings** (shown as "planned" in Settings) | comfort | small |
| 9 | Ideas: rate history and price trend per material, dealer quote comparison, stage-wise purchase schedule, site progress photos | business value for dealers / customers | later |

## Rules kept in every version
- Your database (`data\buildquant.db`), uploads and `session.key` are never overwritten; installers back up first and roll back on failure.
- Structural output is a planning aid, not a design: **DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED** until a licensed engineer approves it.
