# Civora AI — user guide

Planning aid only. Structural output stays **DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED** until a licensed engineer approves the design.

## 1. Create your account
Open Civora and choose **Create Account**. Each person in your team makes their own account.

## 2. Set your rates once
Menu → **Rate Master**. Enter today's prices from your dealer: cement per bag, steel per kg, bricks, ready-mix per m³, sand, labour per sq.ft, GST %. Leave anything you don't know blank; those lines show as "not priced". Clear one rate with ✕ or all of them with **Clear all my rates**.

## 3. Start an estimate
**Only the area known:** on the Dashboard type the built-up area and floors and press **Get full estimate**. Walls, openings and the frame use typical sizes, marked as such.

**With a drawing:** **New Project** → **Upload a drawing** (PDF, DXF, PNG or JPG). Civora reads sizes, rooms, doors and windows, then asks only for what is missing. Check the values marked "Please check".

## 4. Read the estimate
Project → **BBS & BOQ** (Cost & BOQ):
- totals, materials, labour, transport, GST and per sq.ft cost
- cost by stage: foundation, frame and slab, walls, finishes, roof
- every material with how it was worked out; change any rate and save
- **Revisions**: every saved estimate, with Delete

## 5. Structure, steel and site details
- **Structure** tab: add footings (F1), columns (C1), beams (B1) and slabs (S1) from the structural drawing.
- **BBS** tab: add bars named after the element, e.g. `F1-MESH`, `C1-MAIN`, `C1-TIES`, `B1-TOP`, `B1-BOT`, `B1-STIR`, `S1-MAIN`, `S1-DIST`. The order list by diameter is for the steel dealer.
- Click an element to see where the rods go, bend and lap. **Site detail sheet** prints all of them.

## 6. Team
Project → **Team**: create an invite link (send it on WhatsApp) or add someone by username.

| Role | Can do |
|---|---|
| Owner | Everything, including deleting files and the project |
| Engineer | Edit quantities and design inputs, sign off the design |
| Colleague | Edit drawings, estimates, quantities and rates |
| Dealer | View materials, cost and reports |
| Customer | View the estimate, cost and reports |

## 7. Reports
Menu → **Reports** shows every project. Inside a project, **Reports** lists each document with what is inside: project summary (print or save as PDF), Material BOQ (Excel, PDF), structural quantities and BBS (Excel, PDF, CSV), site detail sheet, review report, and **Download all (ZIP)**.

## 8. Stored data and delete
Project → **Data** lists everything saved. Delete one item, or delete the whole project by typing its name; a database backup is made first (`backups\db`, restore with `restore.bat`). Small ✕ buttons also sit next to drawings, elements and bars on their own screens.

## 9. Move your data to the online Civora
1. On your PC: **Settings → Move my data → Download my data (.zip)**.
2. Online: create your account, then **Settings → Move my data → Upload & add**.
Projects already there are skipped. Team members and sign-offs are not moved; invite the team again.

## 10. Tamil
**Settings → Language → தமிழ் + English**. Menus, headings, buttons and material names change to Tamil.

## Backups on your PC
- Automatic daily backup when Civora starts.
- `backup.bat` makes one now; `restore.bat` brings one back (stop the server first).
