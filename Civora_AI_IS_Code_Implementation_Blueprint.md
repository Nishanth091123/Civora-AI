# CIVORA AI — IS-Code-Based Structural Engineering Studio
## Consolidated implementation specification · 11 October 2026

**Status:** Engineering/software specification; **not** an implemented or verified structural design engine, and **not** a construction-ready design document.

## Product boundary
- Preserve the current working Civora AI v2.1 application, all project records, drawings, saved BOQ, BBS and rates. Never overwrite a production database during installation.
- Structural quantity estimation, engineering design, detailing, BBS, unified BOQ, and reports are separate but traceably linked modules.
- No default reinforcement design from room dimensions alone. If mandatory inputs or code checks are missing, mark `DESIGN INCOMPLETE` and suppress construction-ready reinforcement recommendations.
- Every design output identifies code edition, clause, assumptions, inputs, formula/method, intermediate values, check result, author, reviewer, revision and timestamp.
- A qualified structural engineer must review and approve any construction-use design or reinforcement drawing.

## 1. Applicable Indian standards — edition verification required
Verify the currently adopted editions, amendments and project-specific authority requirements **before coding each rule**. Candidate references include:
- IS 456 — plain and reinforced concrete design and detailing.
- IS 875 (relevant parts) — dead, imposed, wind and other loads as applicable.
- IS 1893 (relevant parts) — earthquake-resistant structural design criteria.
- IS 13920 — ductile design and detailing of RC structures under seismic forces, where applicable.
- IS 1786 — high-strength deformed steel bars and wires for concrete reinforcement.
- IS 1904 — design and construction of foundations in soils; other applicable foundation/geotechnical standards as appropriate.
- IS 2502 — bending and fixing of bars for concrete reinforcement, where applicable.
- IS 1200 (relevant parts) — methods of measurement for quantities.
- IS 10262 — concrete mix proportioning, only if mix design is implemented.

**Do not treat this list as an edition-verified or exhaustive compliance register.** Verify licensed standards and their amendments against BIS and applicable local requirements. The software must not reproduce copyrighted standards wholesale.

## 2. Design inputs shared across elements
Project: location and jurisdiction, intended use, occupancy, floor count, importance, structural system, exposure, durability and fire requirements.
Materials: concrete grade, reinforcement grade, cover assumptions subject to checks, unit weights, serviceability requirements.
Geometry: member positions, spans, supports, continuity, restraints, effective depths, openings, member sizes, clearances and elevations.
Actions: self-weight, finishes, live loads, walls, equipment, wind, seismic and other applicable loads; design load combinations and analysis results.
Ground: geotechnical report, allowable/design bearing parameters, settlement, water table and foundation conditions.
Quality: drawing revision, source of each input, units, reviewer and approval status.

## 3. Element-specific workflows
### Footings and foundations
Geotechnical inputs → design actions → bearing and stability checks → footing sizing → flexure, one-way and punching shear → reinforcement, anchorage, cover and development checks → plans/sections → BBS and excavation/PCC/RCC/formwork quantities. Include isolated, combined, strip and raft only with distinct validated methods.

### Columns
Axial load plus biaxial moments, slenderness and effective length → analysis/design checks → longitudinal steel → tie/spiral design → ductile confinement where applicable → lap/splice zoning and anchorage → elevations/sections → BBS and concrete/formwork quantities.

### Beams
Span/support/continuity and factored actions → flexure, shear, torsion where applicable, deflection and crack-control checks → top/bottom bars, development, curtailment, stirrups, seismic detailing where applicable → beam elevation/sections → BBS and quantities.

### Slabs
Panel geometry, supports, continuity, loading, openings and design moments → one-way/two-way or other justified analysis method → flexure, shear, deflection and serviceability checks → top/bottom reinforcement, spacing, development, anchorage and cover → plan/sections → BBS, concrete and formwork. A 10 ft × 10 ft room alone is insufficient to select slab thickness or reinforcement.

### Staircases, retaining walls, shear walls, tanks and special elements
Each requires its own geometry, loads, structural model, design checks and detailing rules. No reuse of a generic `length × width × depth` design method for irregular structural systems. Rectangular decomposition may be used for quantity takeoff only when verified.

## 4. Reinforcement design and BBS
- Engineering design determines required steel area and verifies chosen bar sizes, number, spacing and arrangement; a separate detailing engine generates drawings and schedules.
- Hooks, bends, bend deductions, laps, anchorage, confinement zones, spacing and curtailment must be tied to verified code rules and element context; do not use generic fixed lap multipliers or unverified stirrup spacing.
- Bar records: element ID, drawing ID/revision, bar mark, shape, diameter, grade, count, segment dimensions, bends/hooks/laps, cutting length, unit mass, total mass, wastage and checking status.
- BBS should show dimensioned bar-shape sketches and permit approved manual overrides with change history.
- Flag congestion, missing development length, unsuitable lap location, cover conflicts and clashes as design checks, not as automatic approvals.

## 5. Professional interface
Project Dashboard → Structural Studio → [Elements | Design Inputs | Analysis & Checks | Reinforcement Views | BBS | Unified BOQ | Reports | Review & Approval].
- Elements: element-specific input forms, units, help diagrams, drawing references, saved drafts.
- Analysis: input completeness, load combinations, calculation trace, PASS/FAIL/NOT CHECKED.
- Reinforcement: plan, section, elevation and bar shape views labelled `PRELIMINARY / NOT FOR CONSTRUCTION` until approved.
- BBS: searchable editable schedule with recalculation, revision control and CSV/Excel export.
- Unified BOQ: reconciliation between drawing, original v2.0 worksheet and v2.1 structural records, explicit source mapping and duplicate exclusion.
- Reports: quantity measurement sheets, analysis calculation notes, design-check schedule, reinforcement drawings, BBS, rates, abstract, Excel/PDF and approvals.

## 6. Database and migration
Add new versioned tables rather than modifying or deleting existing measurement tables: design_projects, design_elements, design_inputs, load_cases, load_combinations, analysis_runs, design_checks, rebar_layouts, bbs_revisions, boq_links, approval_events and report_revisions.
- Stable UUIDs, project ownership checks, CSRF protection, parameterized SQL, migration version tracking, transactions and audit log.
- Dry-run migrations, database backup, rollback plan and preservation of existing v2.0/v2.1 records.
- No automatic cost double counting; link each priced work item to one approved source quantity.

## 7. Acceptance gates before release
1. Verified standards register: editions, amendments, applicability and clause traceability reviewed by qualified structural engineer.
2. Independent benchmark calculations for every implemented design case, with unit tests and tolerance limits.
3. Failure-case tests: inadequate reinforcement, missing loads, invalid spans, seismic detailing failures, development/lap issues and shear/punching failures.
4. BBS reconciliation against independently checked bar cutting lengths and total weights.
5. BOQ reconciliation, deduplication, rates, tax and export checks.
6. Multi-project security, migrations, backup/restore, regression tests of existing drawing/BOQ functions and Windows installation tests.
7. Review/approval workflow: draft, checked, approved, superseded; no construction-ready export without required approvals.

## 8. Proposed implementation sequence within ONE consolidated release
A. Freeze current v2.1 and back up source/database.
B. Establish verified code register and benchmark cases.
C. Build element-specific inputs and geometry/quantity validation.
D. Implement tested analysis/design checks for a declared set of structural systems; disable unsupported designs.
E. Implement code-traceable reinforcement detailing and bar-shape visualization.
F. Build advanced BBS and quantity reconciliation.
G. Build unified BOQ/cost, reports and approval flow.
H. Run engineering review, regression and deployment acceptance tests.

**Explicitly deferred:** automatic PDF/DXF drawing recognition and geometry-to-structural-model mapping.

## Delivery honesty
This blueprint is a complete *scope and acceptance specification*, not complete executable IS-code-based structural design software. The existing v2.1 source can be used as the integration baseline; design rules cannot be responsibly certified without licensed code references, benchmark calculations and qualified engineering review.
