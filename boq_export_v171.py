"""Civora v1.7.1: isolated, tested in-memory XLSX/PDF exporters.
No database writes, no guessed quantities, no external file paths.
"""
import io
import math
import re
from html import escape


def _num(value):
    try:
        x = float(value or 0)
        return x if math.isfinite(x) else 0.0
    except (ValueError, TypeError):
        return 0.0


def _clean(value):
    # Excel rejects several ASCII control characters; keep printable text.
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value if value is not None else ''))


def _rows(data):
    for row in data.get('rows', []):
        for item in row.get('items', []):
            qty, rate = _num(item.get('quantity')), _num(item.get('rate'))
            yield (_clean(row.get('work')), _clean(item.get('material')),
                   _clean(item.get('unit')), qty, rate, round(qty * rate, 2))


def basis_label(data):
    # v2.4.1: reports saved earlier were always measured on the external face.
    return _clean(data.get('measurement_basis_label') or 'External face (saved before v2.4.1)')


def cost_summary(data):
    material=sum(amount for *_,amount in _rows(data))
    extras=data.get('cost_extras') or {}
    labour=_num(extras.get('labour'))
    transport=_num(extras.get('transport'))
    other=_num(extras.get('other'))
    tax_pct=_num(extras.get('tax_percent'))
    subtotal=material+labour+transport+other
    tax=round(subtotal*tax_pct/100,2)
    return [('Materials',material),('Labour',labour),('Transport',transport),('Other charges',other),('Subtotal',subtotal),(f'Tax ({tax_pct:.2f}%)',tax),('GRAND TOTAL',round(subtotal+tax,2))]

def excel_bytes(data):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = 'Material BOQ'
    ws.append(['CIVORA AI - DRAFT MATERIAL BOQ'])
    ws.append(['Drawing', _clean(data.get('drawing_name', 'Drawing'))])
    ws.append(['Status', 'DRAFT - UNVERIFIED FOR PROCUREMENT'])
    ws.append(['Measurement basis (masonry)', basis_label(data)])
    ws.append(['Work', 'Material', 'Unit', 'Quantity', 'Rate (INR)', 'Amount (INR)'])
    total = 0.0
    for work, material, unit, qty, rate, amount in _rows(data):
        ws.append([work, material, unit, qty, rate, amount]); total += amount
    last = ws.max_row
    ws.append(['', '', '', '', 'TOTAL', round(total, 2)])
    for i, width in enumerate((52, 32, 20, 17, 18, 21), 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for cell in ws[5]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(fill_type='solid', fgColor='1C4260')
    for row in ws.iter_rows(min_row=6, min_col=4, max_col=6):
        for cell in row: cell.number_format = '#,##0.00'
    ws.freeze_panes = 'A6'
    if last >= 6: ws.auto_filter.ref = f'A5:F{last}'
    ws.sheet_view.showGridLines = False
    summary = wb.create_sheet('Work Cost Summary')
    summary.append(['Work', 'Material Cost (INR)'])
    costs = {}
    for work, material, unit, qty, rate, amount in _rows(data):
        costs[work] = costs.get(work, 0.0) + amount
    for work, amount in costs.items():
        summary.append([work, round(amount, 2)])
    summary.append(['TOTAL', round(total, 2)])
    summary.append([])
    summary.append(['PROJECT COST SUMMARY', 'INR'])
    for name,amount in cost_summary(data): summary.append([name,round(amount,2)])
    summary.column_dimensions['A'].width = 62
    summary.column_dimensions['B'].width = 24
    basis = wb.create_sheet('Measurement Basis')
    basis.append(['Measurement basis (masonry)', basis_label(data), ''])
    basis.append(['External plaster', 'External face', ''])
    basis.append([])
    basis.append(['Measurement', 'Quantity', 'Unit'])
    for item in data.get('breakdown', []):
        basis.append([_clean(item.get('measurement')), _num(item.get('quantity')), _clean(item.get('unit'))])
    basis.column_dimensions['A'].width = 58
    basis.column_dimensions['B'].width = 18
    basis.column_dimensions['C'].width = 16
    assumptions = wb.create_sheet('Assumptions')
    assumptions.append(['DRAFT ONLY - verify geometry, deductions, quantities and rates before procurement'])
    for note in data.get('notes', []): assumptions.append([_clean(note)])
    for note in data.get('skipped', []): assumptions.append(['Skipped: ' + _clean(note)])
    assumptions.column_dimensions['A'].width = 110
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def pdf_bytes(data):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, TableStyle, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import simpleSplit
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=27, rightMargin=27, topMargin=29, bottomMargin=29)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle('BOQCellFix', parent=styles['BodyText'], fontSize=8, leading=10, wordWrap='CJK')
    title = ParagraphStyle('BOQTitleFix', parent=styles['Title'], fontSize=15, leading=18)
    def p(value):
        # Standard reportlab fonts cannot represent every Unicode glyph. Keep the
        # content readable without crashing on rupee signs / en-dashes.
        text = _clean(value).replace('₹', 'INR ').replace('–', '-').replace('—', '-')
        text = text.encode('latin-1', 'replace').decode('latin-1')
        return Paragraph(escape(text), cell)
    story = [Paragraph('CIVORA AI - DRAFT MATERIAL BOQ', title),
             p('Drawing: ' + _clean(data.get('drawing_name', 'Drawing'))),
             p('Measurement basis (masonry): ' + basis_label(data) + '. External plaster: external face.'),
             p('UNVERIFIED ESTIMATE - REVIEW ALL ASSUMPTIONS'), Spacer(1, 12)]
    table_data = [[p(x) for x in ['Work', 'Material', 'Quantity', 'Unit', 'Rate (INR)', 'Amount (INR)']]]
    total = 0.0
    for work, material, unit, qty, rate, amount in _rows(data):
        table_data.append([p(work), p(material), p(f'{qty:,.2f}'), p(unit), p(f'{rate:,.2f}'), p(f'{amount:,.2f}')])
        total += amount
    table_data.append([p('TOTAL'), p(''), p(''), p(''), p(''), p(f'{total:,.2f}')])
    # Total table width 775pt < A4 landscape printable width (~788pt).
    tbl = LongTable(table_data, colWidths=[210, 185, 85, 90, 95, 105], repeatRows=1, hAlign='LEFT')
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1C4260')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F3F7FA')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D2D8DD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E3EDF4')),
    ]))
    story += [tbl, Spacer(1, 12), Paragraph('Project Cost Summary (INR)', styles['Heading2'])]
    for name,amount in cost_summary(data):story.append(p(f'{name}: {amount:,.2f}'))
    story += [Spacer(1, 12), Paragraph('Measurement basis and deductions', styles['Heading2'])]
    for item in data.get('breakdown', []):
        story.append(p(f"{_clean(item.get('measurement'))}: {_num(item.get('quantity')):,.2f} {_clean(item.get('unit'))}"))
    story += [Spacer(1, 9), Paragraph('Assumptions and limitations', styles['Heading2'])]
    for note in data.get('notes', []): story.append(p(note))
    for skipped in data.get('skipped', []): story.append(p('Skipped: ' + _clean(skipped)))
    story.append(p('Draft estimate. Missing rates and unverified quantities require review before procurement.'))
    doc.build(story)
    return out.getvalue()
