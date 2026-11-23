"""Renders the synthetic demo corpora (see SYNTHESIS_PROMPTS.md) into the formats the
factory consumes: PDFs from the markdown sources, and the spares catalogue CSV.

    python demos/synthesize.py
"""
from __future__ import annotations

import csv
import random
import re
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = Path(__file__).parent


def md_to_pdf(src: Path, dst: Path) -> None:
    ss = getSampleStyleSheet()
    story = []
    for line in src.read_text().splitlines():
        s = line.strip()
        if not s:
            story.append(Spacer(1, 3 * mm))
        elif s.startswith("# "):
            story.append(Paragraph(s[2:], ss["Title"]))
        elif s.startswith("## "):
            story.append(Paragraph(s[3:], ss["Heading2"]))
        elif s.startswith("- "):
            story.append(Paragraph("• " + s[2:], ss["BodyText"]))
        else:
            story.append(Paragraph(s, ss["BodyText"]))
    dst.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(dst), pagesize=A4, title=src.stem).build(story)


# (part_no, description, equipment, maker, price, lead_days, moq, supplier, criticality)
CATALOGUE = [
    ("MT-SEP-1001", "Separator bowl O-ring kit", "Fuel oil separator", "Alfa Laval", 185.00, 7, 2, "Marinetech Spares", "B"),
    ("MT-SEP-1002", "Separator gravity disc set", "Fuel oil separator", "Alfa Laval", 420.00, 14, 1, "Marinetech Spares", "B"),
    ("MT-SEP-1003", "Separator major overhaul kit", "Fuel oil separator", "Alfa Laval", 2350.00, 21, 1, "Marinetech Spares", "B"),
    ("MT-SEP-1004", "Separator operating water valve", "Lube oil separator", "Alfa Laval", 610.00, 10, 1, "Marinetech Spares", "C"),
    ("MT-CMP-2001", "Main air compressor valve plate assembly", "Main air compressor", "Sperre", 1240.00, 18, 1, "Marinetech Spares", "A"),
    ("MT-CMP-2002", "Compressor piston ring set", "Main air compressor", "Sperre", 365.00, 12, 2, "Marinetech Spares", "A"),
    ("MT-CMP-2003", "Compressor unloader valve", "Main air compressor", "Sperre", 540.00, 15, 1, "Marinetech Spares", "B"),
    ("MT-CMP-2004", "Service air compressor filter element", "Service air compressor", "Atlas Copco", 48.50, 5, 10, "Marinetech Spares", "C"),
    ("MT-PMP-3001", "Fire pump mechanical seal", "Main fire pump", "Shinko", 780.00, 20, 1, "Marinetech Spares", "A"),
    ("MT-PMP-3002", "Fire pump impeller", "Main fire pump", "Shinko", 1960.00, 30, 1, "Marinetech Spares", "A"),
    ("MT-PMP-3003", "Ballast pump wear ring", "Ballast pump", "Shinko", 295.00, 14, 2, "Marinetech Spares", "C"),
    ("MT-PMP-3004", "Cooling SW pump mechanical seal", "Sea water cooling pump", "Naniwa", 640.00, 16, 1, "Marinetech Spares", "B"),
    ("MT-PMP-3005", "Emergency fire pump coupling insert", "Emergency fire pump", "Shinko", 155.00, 9, 2, "Marinetech Spares", "A"),
    ("MT-BLR-4001", "Boiler burner nozzle", "Auxiliary boiler", "Aalborg", 260.00, 12, 2, "Marinetech Spares", "B"),
    ("MT-BLR-4002", "Boiler flame scanner", "Auxiliary boiler", "Aalborg", 1480.00, 25, 1, "Marinetech Spares", "B"),
    ("MT-BLR-4003", "Boiler gauge glass kit", "Auxiliary boiler", "Klinger", 115.00, 6, 4, "Marinetech Spares", "B"),
    ("MT-DCK-5001", "Mooring winch brake lining", "Mooring winch", "Kawasaki", 890.00, 28, 2, "Marinetech Spares", "C"),
    ("MT-DCK-5002", "Hydraulic motor seal kit", "Deck crane", "Liebherr", 720.00, 21, 1, "Marinetech Spares", "B"),
    ("MT-DCK-5003", "Steering gear hydraulic pump seal kit", "Steering gear", "Rolls-Royce", 1150.00, 24, 1, "Marinetech Spares", "A"),
    ("MT-DCK-5004", "Lifeboat davit wire rope 16mm", "Lifeboat davit", "Schat-Harding", 2280.00, 35, 1, "Marinetech Spares", "A"),
    ("MT-PUR-6001", "Fresh water generator anode", "Fresh water generator", "Alfa Laval", 72.00, 5, 6, "Marinetech Spares", "C"),
    ("MT-PUR-6002", "Oily water separator coalescer filter", "Oily water separator", "RWO", 395.00, 11, 2, "Marinetech Spares", "B"),
    ("OE-ME-7001", "Main engine fuel injection valve nozzle", "Main engine", "MAN Energy Solutions", 1320.00, 21, 4, "Oceanic Engine Parts", "A"),
    ("OE-ME-7002", "Main engine exhaust valve spindle", "Main engine", "MAN Energy Solutions", 6850.00, 45, 1, "Oceanic Engine Parts", "A"),
    ("OE-ME-7003", "Main engine piston ring set (per cylinder)", "Main engine", "MAN Energy Solutions", 2140.00, 30, 1, "Oceanic Engine Parts", "A"),
    ("OE-ME-7004", "Main engine cylinder liner O-ring set", "Main engine", "MAN Energy Solutions", 310.00, 14, 2, "Oceanic Engine Parts", "A"),
    ("OE-ME-7005", "Main engine starting air valve overhaul kit", "Main engine", "MAN Energy Solutions", 980.00, 18, 1, "Oceanic Engine Parts", "A"),
    ("OE-ME-7006", "Main engine fuel pump plunger and barrel", "Main engine", "MAN Energy Solutions", 4420.00, 40, 1, "Oceanic Engine Parts", "A"),
    ("OE-ME-7007", "Cylinder lubricator pump unit", "Main engine", "MAN Energy Solutions", 3150.00, 35, 1, "Oceanic Engine Parts", "A"),
    ("OE-AE-8001", "Generator engine fuel injector", "Auxiliary engine", "Yanmar", 690.00, 14, 3, "Oceanic Engine Parts", "A"),
    ("OE-AE-8002", "Generator engine cylinder head gasket", "Auxiliary engine", "Yanmar", 145.00, 7, 3, "Oceanic Engine Parts", "B"),
    ("OE-AE-8003", "Generator engine connecting rod bearing set", "Auxiliary engine", "Yanmar", 860.00, 20, 1, "Oceanic Engine Parts", "A"),
    ("OE-AE-8004", "Generator engine lube oil filter", "Auxiliary engine", "Yanmar", 38.00, 4, 12, "Oceanic Engine Parts", "C"),
    ("OE-AE-8005", "Emergency generator engine starter motor", "Emergency generator", "Cummins", 1890.00, 22, 1, "Oceanic Engine Parts", "A"),
    ("OE-AE-8006", "Emergency generator fuel filter", "Emergency generator", "Cummins", 42.00, 4, 6, "Oceanic Engine Parts", "A"),
    ("OE-TC-9001", "Turbocharger nozzle ring", "Main engine turbocharger", "ABB", 7400.00, 50, 1, "Oceanic Engine Parts", "A"),
    ("OE-TC-9002", "Turbocharger bearing set", "Main engine turbocharger", "ABB", 3380.00, 32, 1, "Oceanic Engine Parts", "A"),
    ("OE-TC-9003", "Turbocharger air filter silencer mat", "Main engine turbocharger", "ABB", 265.00, 10, 2, "Oceanic Engine Parts", "B"),
    ("OE-TC-9004", "Aux engine turbocharger cartridge", "Auxiliary engine turbocharger", "MAN Energy Solutions", 5120.00, 42, 1, "Oceanic Engine Parts", "A"),
    ("OE-GV-9501", "Electronic governor actuator", "Main engine governor", "Woodward", 4780.00, 38, 1, "Oceanic Engine Parts", "A"),
    ("OE-GV-9502", "Governor speed pickup sensor", "Main engine governor", "Woodward", 410.00, 12, 1, "Oceanic Engine Parts", "A"),
    ("OE-ME-7008", "Main engine crosshead bearing shell", "Main engine", "MAN Energy Solutions", 5960.00, 48, 1, "Oceanic Engine Parts", "A"),
]


def write_catalogue(dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part_no", "description", "equipment", "maker", "unit_price_usd", "lead_time_days", "min_order_qty", "supplier", "criticality"])
        for r in CATALOGUE:
            w.writerow([r[0], r[1], r[2], r[3], f"{r[4]:.2f}", r[5], r[6], r[7], r[8]])


def main():
    for demo in ("hr_policy", "ship_spares"):
        src_dir, docs = HERE / demo / "_source", HERE / demo / "docs"
        if docs.exists():
            shutil.rmtree(docs)
        for md in sorted(src_dir.glob("*.md")):
            md_to_pdf(md, docs / f"{md.stem}.pdf")
    write_catalogue(HERE / "ship_spares" / "docs" / "spares_catalogue.csv")

    # Regression scenario: leave policy v5 changes three numbers.
    v2 = HERE / "hr_policy" / "docs_v2"
    if v2.exists():
        shutil.rmtree(v2)
    shutil.copytree(HERE / "hr_policy" / "docs", v2)
    txt = (HERE / "hr_policy" / "_source" / "leave_policy.md").read_text()
    txt = txt.replace("Version 4.2 - Effective 1 April 2026", "Version 5.0 - Effective 1 April 2027")
    txt = txt.replace("entitled to 24 working days", "entitled to 26 working days")
    txt = txt.replace("A maximum of 10 days of unused annual leave", "A maximum of 15 days of unused annual leave")
    txt = txt.replace("balance above 10 days lapses", "balance above 15 days lapses")
    txt = txt.replace("more than 2 consecutive days", "more than 3 consecutive days")
    tmp = HERE / "hr_policy" / "_leave_v5.md"
    tmp.write_text(txt)
    md_to_pdf(tmp, v2 / "leave_policy.pdf")
    tmp.unlink()
    print("synthesized:", sorted(str(p.relative_to(HERE)) for p in HERE.glob("*/docs*/*")))


if __name__ == "__main__":
    main()
