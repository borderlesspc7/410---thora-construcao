"""Smoke test: upload + detect-tables."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx
from fpdf import FPDF

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"


def make_pdf(path: Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 10, "ORCAMENTO DE OBRA", ln=1)
    for row in [
        "Codigo | Descricao | Qtd | Valor Unit | Total",
        "001 | Cimento 50kg | 100 | 35,50 | 3550,00",
        "002 | Areia fina | 50 | 120,00 | 6000,00",
        "003 | Brita 0 | 30 | 85,00 | 2550,00",
    ]:
        pdf.cell(0, 8, row, ln=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def main() -> None:
    pdf_path = Path("data/test_sample.pdf")
    make_pdf(pdf_path)

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        with pdf_path.open("rb") as f:
            upload = client.post(
                "/api/upload",
                files={"file": ("test.pdf", f, "application/pdf")},
            )
        upload.raise_for_status()
        upload_data = upload.json()
        print("upload:", upload_data)

        upload_id = upload_data["upload_id"]
        detect = client.post(
            "/api/orcamentos/detect-tables",
            data={"upload_id": upload_id},
        )
        detect.raise_for_status()
        detect_data = detect.json()
        print("tables_found:", detect_data["tables_found"])
        if detect_data["options"]:
            print("first option:", {k: detect_data["options"][0].get(k) for k in ("id", "nome_tabela", "pagina")})
        else:
            print("WARN: nenhuma tabela detectada no PDF de teste")


if __name__ == "__main__":
    main()
