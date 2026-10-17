# Civora AI 3.0 – Redesign plan and status

Direction chosen: **01 Enterprise Construction Hub + 03 Interactive Building Studio + 04 Smart Estimation Workspace**,
light-first, navy navigation, blue actions, teal engineering indicators, amber warnings.

Rule kept throughout: **the backend, database, calculations, routes, CSRF, ownership checks and exports are unchanged.**
New screens only read existing tables and post to existing routes; every additive table is listed below.

## 1. Information architecture

```
CIVORA AI · Construction Intelligence Workspace
WORKSPACE      Dashboard · Projects · Drawing Studio · Smart Estimate · Structural Studio
MANAGEMENT     BBS & BOQ · Rate Master · Reports · Team · Settings
Advanced tools Project workflow · Measure on drawing · Material takeoff · Design inputs · Design review · v2.0 worksheet
```

Project context bar (every project page): name · type · location · next stage · estimate revision · your role · saved state,
with tabs Workspace · Drawing Studio · Estimate · Structure · BBS & BOQ · Reports · Team.

End-to-end flow: Create project → Quick Estimate (area) → Drawing Studio (upload, verify sizes) → Smart Estimate
(missing values only) → quantities + preliminary frame → Rate Master pricing → engineer sign-off → reports / Download All.

## 2. Design tokens

| Token | Value | Use |
|---|---|---|
| Navy | `#142B45` | navigation, dark panels |
| Blue | `#2563EB` | primary actions, active states |
| Teal | `#0D9488` | engineering indicators, "what Civora read" |
| Amber | `#F59E0B` | warnings, typical values to check |
| Red | `#DC2626` | errors, destructive actions |
| Canvas | `#F3F6FA` | page background |
| Line / Ink / Mute | `#E2E8F0` / `#0F172A` / `#5B6B7F` | borders / text / secondary text |

Typography: Segoe UI / system sans-serif (works offline on Windows); Tamil text falls back to the system Tamil font.
Spacing on an 8 px scale; radius 10–16 px; white cards with a 1 px line border.

Status system (label + colour, never colour alone): **Draft · Needs input · In progress · Needs review · Checked**.

## 3. Shared components (`ui_shell.py`)

Shell (sidebar groups, top bar with search, mobile drawer + bottom bar) · project context bar · buttons (`cv-btn`, `ghost`, `sm`) ·
cards (`cv-card`) · status chips (`cv-status`) · stepper · key/value lists (`cv-kv`) · data tables (`cv-mt`, `pf-table`) ·
banners (success / warning / error) · Guided-mode help (`cv-guide`, hidden in Expert mode) · Expert-only controls (`cv-expert`) ·
empty states (`cv-empty`) · friendly error pages (403 / 404 / 410 inside the layout).
All older pages render inside the same shell and pick up the shared table, link and input styles.

## 4. Screens – status in 3.0

| Screen | 3.0 | Notes |
|---|---|---|
| Dashboard (command center) | **Done** | Quick Estimate question; active / needs-review / needs-input / budget tiles from real data; continue project; projects table; team activity |
| Projects portfolio | **Done** | table / card view, search, type and status filters, progress, estimate, last updated, shared role |
| New Project wizard | **Done** | Basic details → Building (area, floors) → How to start (area only / drawing / later) → Review; same POST route |
| Project workspace | **Done** | next-step banner, 6-step stepper, 6 workflow cards, files |
| Drawing Studio | **Done** | drawings list · zoomable viewer (PDF pages) · what Civora read (sizes, rooms, doors/windows) · measurement schedule |
| Smart Estimate | Done in 2.6, restyled | Quick Area and Drawing-based paths; every value marked From drawing / Worked out / Please check |
| Settings | **Done** | Guided / Expert mode, English / Tamil menu; planned items listed as planned, not as controls |
| Team | Done in 2.7 | roles, invites, activity, engineer sign-off |
| Rate Master | Done in 2.6 | |
| Structural Studio, BBS | Existing v2.1–2.3 pages inside the new shell | **Done 3.1**; reinforcement detail drawings + site detail sheet **3.2** |
| Unified BOQ & Cost center | BBS & BOQ opens the latest BOQ | **Done 3.1** |
| Reports document center | Reports card + Download All per project | **Done 3.3**: `/reports` (all projects, search, ready / needs-review filter), `/projects/{pid}/reports` (each document with what is inside, open / download via existing export routes), `/projects/{pid}/reports/summary` (printable one-page report) |
| Full Tamil interface | Menu + main headings | **Done 3.3** (`i18n_v330.py`): menus, headings, buttons, labels, statuses, materials and activity log on all main screens; exact whole-text matching only, numbers / units / form values / site terms (BOQ, BBS, RCC) untouched; untranslated text falls back to English |

## 5. Backend preservation

* No route removed or renamed. 3.0 adds read-only GET pages (`/projects/{pid}/studio`, `/projects/{pid}/boq`, `/settings`) and one POST (`/settings`).
* `POST /projects/new` keeps its fields; `floors` and `next` are optional extras.
* Additive tables only: `civora_rate_master_v260`, `civora_members_v270`, `civora_invites_v270`, `civora_activity_v270`,
  `civora_signoff_v270`, `civora_user_prefs_v300`. Every version is recorded in `schema_migrations`.
* Calculation modules (`engineering`, `measurement`, `drawing_schedule`, `intelligent_recognition`, BOQ export, structural v2.0–2.3)
  are fingerprint-checked by the installer and must be unchanged.
* Installer: database backup first, source backup, compile, full test suite, automatic rollback on any failure.

## 6. Regression test plan

`run_tests.py` runs everything on throw-away copies (the real database is never used):

* unit tests for calculations and measurement basis; data-safety tests;
* smoke tests that drive the real app over HTTP — v2.4 full drawing → BOQ → exports → structural; v2.5 UI;
  v2.6 Smart Estimate + Rate Master; v2.7 team roles and permissions (5 users); v2.8 Quick Estimate;
  v3.0 dashboard, portfolio filters, wizard (all three start paths), workspace, Drawing Studio, settings,
  context bar, Guided/Expert — and **no duplicate routes**.

## 7. Route inventory and route-to-screen mapping

| Method | Route | Screen |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/favicon.svg` | (asset) |
| GET | `/files/{fid}` | Files |
| GET | `/guest` | Sign in / guest |
| POST | `/guest/estimate` | Material takeoff (advanced) |
| GET | `/invite/{raw}` | Team |
| POST | `/invite/{raw}` | Team |
| GET | `/login` | Sign in / guest |
| POST | `/login` | Sign in / guest |
| POST | `/logout` | Sign in / guest |
| GET | `/materials` | Material takeoff (advanced) |
| GET | `/projects` | Projects portfolio |
| GET | `/projects/new` | New Project wizard |
| POST | `/projects/new` | New Project wizard |
| GET | `/projects/{pid}` | Project workspace |
| GET | `/projects/{pid}/boq` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/boq` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/boq.csv` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/preview` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/save` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/saved/{mid}` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/saved/{mid}/delete` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/adaptive` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/adaptive` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/auto` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/auto` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/boq` | BBS & BOQ / cost |
| POST | `/projects/{pid}/drawings/{fid}/boq/save` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/{fid}/boq/{bid}` | BBS & BOQ / cost |
| POST | `/projects/{pid}/drawings/{fid}/boq/{bid}/costs` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/{fid}/boq/{bid}/excel` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/{fid}/boq/{bid}/pdf` | BBS & BOQ / cost |
| POST | `/projects/{pid}/drawings/{fid}/boq/{bid}/rates` | BBS & BOQ / cost |
| GET | `/projects/{pid}/drawings/{fid}/intelligence` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/intelligence` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/intelligence/overlay` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/media` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/preview` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/recognition` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/recognition` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/recognition/overlay` | Drawing tools (advanced) |
| GET | `/projects/{pid}/drawings/{fid}/residential` | Drawing tools (advanced) |
| POST | `/projects/{pid}/drawings/{fid}/residential` | Drawing tools (advanced) |
| GET | `/projects/{pid}/estimate` | Material takeoff (advanced) |
| POST | `/projects/{pid}/estimate` | Material takeoff (advanced) |
| GET | `/projects/{pid}/materials` | Material takeoff (advanced) |
| POST | `/projects/{pid}/materials` | Material takeoff (advanced) |
| POST | `/projects/{pid}/materials/commit` | Material takeoff (advanced) |
| POST | `/projects/{pid}/materials/preview` | Material takeoff (advanced) |
| POST | `/projects/{pid}/materials/{mid}/delete` | Material takeoff (advanced) |
| POST | `/projects/{pid}/quick` | Smart Estimate / Quick Estimate |
| POST | `/projects/{pid}/rates/apply` | BBS & BOQ / cost |
| POST | `/projects/{pid}/signoff` | Structural Studio – design inputs & review |
| GET | `/projects/{pid}/smart` | Smart Estimate / Quick Estimate |
| POST | `/projects/{pid}/smart/upload` | Smart Estimate / Quick Estimate |
| GET | `/projects/{pid}/smart/{fid}` | Smart Estimate / Quick Estimate |
| POST | `/projects/{pid}/smart/{fid}` | Smart Estimate / Quick Estimate |
| GET | `/projects/{pid}/structural` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/add` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/advanced` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/add` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/bbs/add` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/bbs/{bar_id}/delete` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/advanced/export.csv` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/advanced/export.pdf` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/advanced/export.xlsx` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/rates` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/{item_id}/delete` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/advanced/{item_id}/edit` | Structural Studio – quantities & BBS |
| POST | `/projects/{pid}/structural/advanced/{item_id}/edit` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/design` | Structural Studio – design inputs & review |
| POST | `/projects/{pid}/structural/design/save` | Structural Studio – design inputs & review |
| GET | `/projects/{pid}/structural/design/{rid}` | Structural Studio – design inputs & review |
| GET | `/projects/{pid}/structural/export.csv` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/structural/review` | Structural Studio – design inputs & review |
| GET | `/projects/{pid}/structural/review/export.csv` | Structural Studio – design inputs & review |
| GET | `/projects/{pid}/structural/review/report.html` | Structural Studio – design inputs & review |
| POST | `/projects/{pid}/structural/{sid}/delete` | Structural Studio – quantities & BBS |
| GET | `/projects/{pid}/studio` | Drawing Studio |
| GET | `/projects/{pid}/studio/{fid}` | Drawing Studio |
| GET | `/projects/{pid}/takeoff` | Material takeoff (advanced) |
| POST | `/projects/{pid}/takeoff` | Material takeoff (advanced) |
| GET | `/projects/{pid}/takeoff/export.csv` | Material takeoff (advanced) |
| GET | `/projects/{pid}/takeoff/preview` | Material takeoff (advanced) |
| POST | `/projects/{pid}/takeoff/save` | Material takeoff (advanced) |
| GET | `/projects/{pid}/takeoff/{tid}` | Material takeoff (advanced) |
| POST | `/projects/{pid}/takeoff/{tid}/delete` | Material takeoff (advanced) |
| GET | `/projects/{pid}/team` | Team |
| POST | `/projects/{pid}/team/add` | Team |
| POST | `/projects/{pid}/team/invite` | Team |
| POST | `/projects/{pid}/team/remove` | Team |
| POST | `/projects/{pid}/team/role` | Team |
| POST | `/projects/{pid}/upload` | Files |
| POST | `/projects/{pid}/uploads/{fid}/delete` | Files |
| GET | `/projects/{pid}/workflow` | Project workflow & reports |
| GET | `/projects/{pid}/workflow/download-all` | Project workflow & reports |
| POST | `/quick` | Smart Estimate / Quick Estimate |
| GET | `/rates` | Rate Master |
| POST | `/rates` | Rate Master |
| GET | `/register` | Sign in / guest |
| POST | `/register` | Sign in / guest |
| GET | `/settings` | Settings |
| POST | `/settings` | Settings |

105 route+method pairs, each registered exactly once (checked by the smoke tests).
