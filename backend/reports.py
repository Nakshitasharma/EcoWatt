"""Compact PDF report generation for the current building summary."""
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from xml.sax.saxutils import escape

GREEN = colors.HexColor("#176B4B")
INK = colors.HexColor("#17231F")
MUTED = colors.HexColor("#6E7B74")

def create_summary_pdf(summary: dict) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=17*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="EcoTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=INK, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name="EcoSection", parent=styles["Heading2"], fontSize=12, leading=15, textColor=GREEN, spaceBefore=13, spaceAfter=7))
    styles.add(ParagraphStyle(name="EcoBody", parent=styles["BodyText"], fontSize=9, leading=13, textColor=MUTED))
    styles.add(ParagraphStyle(name="EcoSmall", parent=styles["BodyText"], fontSize=8, leading=11, textColor=MUTED))
    story = [Paragraph("EcoWatt", styles["EcoTitle"]), Paragraph("ENERGY INTELLIGENCE · BUILDING SUMMARY", styles["EcoSmall"]), Spacer(1, 8*mm)]
    b=summary["building"]; m=summary["metrics"]; cov=summary["coverage"]
    story += [Paragraph(escape(str(b['name'])), styles["Heading1"]), Paragraph(f"Reporting coverage: {escape(str(cov['from']))} to {escape(str(cov['to']))}", styles["EcoBody"]), Paragraph(f"Generated: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}", styles["EcoBody"]), Spacer(1, 4*mm)]
    table = Table([["MEASURE", "VALUE", "BASIS"], ["Imported records", f"{summary['record_count']:,}", "Source readings stored in EcoWatt"], ["Latest reading", f"{m['latest']:,.3f} kWh", "Most recent valid source record"], ["Recent 24h", f"{m['last_24h']:,.3f} kWh", "Measured records within latest 24 hours"], ["Previous 24h", f"{m['previous_24h']:,.3f} kWh" if m['previous_24h'] is not None else "Unavailable", "Measured records in preceding window"], ["Peak record", f"{m['peak']:,.3f} kWh", "Maximum in imported coverage"]], colWidths=[43*mm, 40*mm, 89*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),GREEN),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("TEXTCOLOR",(0,1),(-1,-1),INK),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F8F5")]),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#E2EAE4")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story += [Paragraph("Measured consumption", styles["EcoSection"]), table]
    fc=summary.get("forecast") or {}
    story.append(Paragraph("Forecast evaluation", styles["EcoSection"]))
    if fc.get("available") and fc.get("metrics"):
        met=fc["metrics"]
        story.append(Paragraph(f"Method: {fc['method']}. Chronological holdout used {fc['test_records']} test records from {fc['training_records']} feature-ready observations. MAE: {met['mae']} kWh per record. RMSE: {met['rmse']} kWh per record. R²: {met['r2']}.",styles["EcoBody"]))
        future=fc.get("points",[])
        if future:
            rows=[["FORECAST STEP","ESTIMATE (kWh per record)"]]+[[x["timestamp"],f"{x['value']:.3f}"] for x in future[:24]]
            t=Table(rows,colWidths=[80*mm,92*mm],repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF4ED")),("TEXTCOLOR",(0,0),(-1,0),GREEN),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#E2EAE4")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAF8")]),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
            story += [Spacer(1,4*mm),t]
    else: story.append(Paragraph(f"Forecast unavailable: {fc.get('reason','Not enough data for model evaluation.')}",styles["EcoBody"]))
    story += [Paragraph("Anomaly review", styles["EcoSection"])]
    anomalies=summary.get("anomalies",[])
    if anomalies:
        ar=[["TIME","OBSERVED","BASELINE","DEVIATION","SEVERITY"]]+[[x["timestamp"],f"{x['observed']:.2f}",f"{x['baseline']:.2f}",f"{x['deviation']:+.2f}",x["severity"]] for x in anomalies[-8:]]
        t=Table(ar,colWidths=[60*mm,25*mm,25*mm,28*mm,25*mm],repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF4ED")),("TEXTCOLOR",(0,0),(-1,0),GREEN),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#E2EAE4")),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story.append(t)
    else: story.append(Paragraph("No records crossed the current rolling statistical threshold, or there is insufficient data.",styles["EcoBody"]))
    story.append(Paragraph("Evidence-based recommendation", styles["EcoSection"]))
    recommendations=summary.get("recommendations",{}).get("items",[])
    if recommendations:
        for rec in recommendations:
            story += [Paragraph(escape(str(rec["title"])),styles["Heading3"]),Paragraph(escape(str(rec["reason"])),styles["EcoBody"]),Paragraph(escape(str(rec["suggested_action"])),styles["EcoBody"]),Paragraph("Savings impact: not estimated; whole-building meter readings do not attribute end uses.",styles["EcoSmall"]),Spacer(1,2*mm)]
    else: story.append(Paragraph("No recommendation is available from the current dataset coverage.",styles["EcoBody"]))
    scenarios=summary.get("simulations",[])
    if scenarios:
        story.append(Paragraph("Saved what-if scenarios",styles["EcoSection"]))
        sr=[["SCENARIO","BASELINE (kWh)","SCENARIO (kWh)"]]+[[escape(str(x["name"])),f"{x['baseline_kwh']:.2f}",f"{x['scenario_kwh']:.2f}"] for x in scenarios]
        st=Table(sr,colWidths=[86*mm,43*mm,43*mm],repeatRows=1)
        st.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF4ED")),("TEXTCOLOR",(0,0),(-1,0),GREEN),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#E2EAE4")),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(st)
    story += [Paragraph("Interpretation and limitations", styles["EcoSection"]), Paragraph("These are source meter readings and derived calculations, not utility-verified bills. Forecasts use a short-range time-feature model; held-out performance does not guarantee future accuracy. Anomaly flags are statistical deviations and do not establish energy wastage. Whole-building data cannot identify end-use causes. No energy or cost savings are promised. Tariff and emissions assumptions are omitted unless explicitly configured.",styles["EcoBody"]), Spacer(1,8*mm), Paragraph("Source note: Building data, units, interval and meter identity should be verified against the source documentation. EcoWatt preserves the selected unit and records attribution for bundled BDG2 sample data.",styles["EcoSmall"])]
    def footer(canvas, doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#DCE6DF")); canvas.line(18*mm,13*mm,A4[0]-18*mm,13*mm)
        canvas.setFont("Helvetica",7); canvas.setFillColor(MUTED); canvas.drawString(18*mm,8.5*mm,"EcoWatt · Forecast Today. Save Tomorrow."); canvas.drawRightString(A4[0]-18*mm,8.5*mm,f"Page {doc.page}"); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
