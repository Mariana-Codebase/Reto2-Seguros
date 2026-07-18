"""
pdfgen.py
---------
Genera los PDF reales en el servidor (resumen de recomendación y carátula de
póliza) con fpdf2. Se guardan en docs_generados/ y se sirven en /docs/{archivo}.

Se usa la fuente core 'helvetica' (codificación latin-1), que cubre el español.
sanitize() reemplaza los pocos caracteres no soportados (·, →, …) para evitar
errores de codificación.
"""

from __future__ import annotations

from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .config import settings

DOCS_DIR = settings.DOCS_DIR

GREEN = (10, 143, 77)
INK = (15, 30, 46)
GRAY = (107, 122, 144)


def sanitize(text: str) -> str:
    if text is None:
        return ""
    repl = {"·": "-", "→": "->", "…": "...", "—": "-", "–": "-", "“": '"', "”": '"', "’": "'", "•": "-"}
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


class _Doc(FPDF):
    titulo_doc = "Documento"

    def header(self):
        self.set_fill_color(*GREEN)
        self.rect(0, 0, 210, 4, "F")
        self.set_xy(12, 12)
        self.set_fill_color(*GREEN)
        self.set_text_color(255, 255, 255)
        self.set_font("helvetica", "B", 15)
        self.cell(12, 12, "C", align="C", fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_text_color(*INK)
        self.set_xy(28, 12)
        self.set_font("helvetica", "B", 13)
        self.cell(0, 6, "Colsubsidio", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(28, 18)
        self.set_text_color(*GRAY)
        self.set_font("helvetica", "", 9)
        self.cell(0, 5, sanitize("Seguros - Asesora digital Clara"),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GREEN)
        self.set_line_width(0.6)
        self.line(12, 30, 198, 30)
        self.set_xy(12, 38)

    def footer(self):
        self.set_y(-16)
        self.set_x(12)
        self.set_text_color(*GRAY)
        self.set_font("helvetica", "", 7.5)
        txt = ("Documento generado por Clara. Datos tratados conforme a la Ley 1581 de 2012. "
               "Colsubsidio - NIT 860.007.336-1.")
        self.multi_cell(0, 4, sanitize(txt), align="C")


def _title(pdf: _Doc, titulo: str, sub: str):
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", "B", 17)
    pdf.multi_cell(0, 8, sanitize(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*GRAY)
    pdf.set_font("helvetica", "", 10.5)
    pdf.multi_cell(0, 5, sanitize(sub), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)


def _section(pdf: _Doc, titulo: str):
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*GREEN)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, sanitize(titulo.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(220, 226, 233)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*INK)


def _bullets(pdf: _Doc, items: list[str]):
    pdf.set_font("helvetica", "", 10.5)
    for it in items:
        pdf.set_x(14)
        pdf.multi_cell(0, 5.5, sanitize("-  " + it), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _kv(pdf: _Doc, k: str, v: str):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 10.5)
    pdf.set_text_color(*GRAY)
    pdf.cell(55, 6.5, sanitize(k), new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.multi_cell(0, 6.5, sanitize(v), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generar_resumen_pdf(session_id: str, perfil: dict[str, Any], opciones: list[dict[str, Any]],
                        perfil_humano: str) -> str:
    pdf = _Doc()
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    _title(pdf, "Resumen de tu recomendacion de seguros",
           "Preparado por Clara con base en el perfil que compartiste.")

    _section(pdf, "Perfil detectado")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 10.5)
    pdf.multi_cell(0, 5.5, sanitize(perfil_humano), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    for i, o in enumerate(opciones):
        _section(pdf, f"Opcion {i + 1}: {o['nombre']} - {o['precio_formateado']}/mes")
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "I", 10)
        pdf.set_text_color(*GRAY)
        pdf.multi_cell(0, 5.5, sanitize(o.get("por_que", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*INK)
        pdf.ln(1)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 6, "Coberturas clave", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _bullets(pdf, o.get("cubre", []))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 6, "Exclusiones principales", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _bullets(pdf, o.get("no_cubre", []))
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "I", 8.5)
        pdf.set_text_color(*GRAY)
        pdf.multi_cell(0, 4.5, sanitize("Fuente: " + o.get("fuente", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*INK)
        pdf.ln(2)

    fname = f"resumen_{session_id}.pdf"
    pdf.output(str(DOCS_DIR / fname))
    return fname


def generar_contrato_pdf(session_id: str, c: dict[str, Any]) -> str:
    """Contrato en un solo PDF: datos del tomador, datos del bien asegurado,
    detalle completo de la póliza (amparos, exclusiones, condiciones), prima y
    bloque de firma electrónica."""
    pdf = _Doc()
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    estado_txt = "Contrato firmado" if c.get("firmado") else "Borrador - pendiente de firma"
    _title(pdf, "Contrato de seguro - " + c["producto"],
           f"Solicitud {c['solicitud']}  -  {estado_txt}")

    _section(pdf, "Datos del tomador")
    t = c.get("tomador", {})
    _kv(pdf, "Nombre", t.get("nombre", ""))
    _kv(pdf, "Documento", t.get("documento", ""))
    _kv(pdf, "Correo", t.get("correo", ""))
    _kv(pdf, "Telefono", t.get("telefono", ""))
    if t.get("direccion"):
        _kv(pdf, "Direccion", t["direccion"])
    pdf.ln(2)

    bien = c.get("bien")
    if bien and bien.get("items"):
        _section(pdf, bien.get("titulo", "Bien asegurado"))
        for item in bien["items"]:
            k, v = (item[0], item[1]) if isinstance(item, (list, tuple)) else ("Dato", item)
            _kv(pdf, str(k), str(v))
        pdf.ln(2)

    _section(pdf, "Amparos incluidos (que cubre)")
    _bullets(pdf, c.get("cubre", []))
    _section(pdf, "Exclusiones (que no cubre)")
    _bullets(pdf, c.get("no_cubre", []))
    _section(pdf, "Condiciones generales")
    _bullets(pdf, c.get("condiciones", []))

    _section(pdf, "Prima y vigencia")
    if c.get("precio"):
        _kv(pdf, "Prima mensual", c.get("precio_formateado", ""))
    _kv(pdf, "Vigencia", c.get("vigencia", ""))
    _kv(pdf, "Inicio", c.get("inicio", ""))
    _kv(pdf, "Fin", c.get("fin", ""))
    pdf.ln(4)

    _section(pdf, "Firma del afiliado")
    firma = c.get("firma") or {}
    if c.get("firmado") and firma:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "BI", 15)
        pdf.set_text_color(*INK)
        pdf.cell(0, 9, sanitize(firma.get("nombre", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y() + 1, 96, pdf.get_y() + 1)
        pdf.ln(3)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*GRAY)
        pdf.multi_cell(0, 5, sanitize(
            f"Firmado electronicamente el {firma.get('at', '')}. "
            "El afiliado acepta las condiciones generales del producto y autoriza el tratamiento de sus datos (Ley 1581 de 2012)."),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*GRAY)
        pdf.multi_cell(0, 5, sanitize(
            "Pendiente de firma. El afiliado firma electronicamente desde el chat para aceptar las condiciones "
            "y continuar con el pago."),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    fname = f"contrato_{c['solicitud']}.pdf"
    pdf.output(str(DOCS_DIR / fname))
    return fname


def generar_poliza_pdf(session_id: str, poliza: dict[str, Any]) -> str:
    pdf = _Doc()
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    _title(pdf, "Caratula de poliza - " + poliza["producto"],
           "Poliza activa. Conserva este documento.")

    _section(pdf, "Datos de la poliza")
    _kv(pdf, "Numero de poliza", poliza["numero"])
    _kv(pdf, "Producto", poliza["producto"])
    _kv(pdf, "Tomador", poliza.get("tomador", "Afiliado Colsubsidio"))
    _kv(pdf, "Estado", "Activa")
    _kv(pdf, "Vigencia inicio", poliza["inicio"])
    _kv(pdf, "Vigencia fin", poliza["fin"])
    if poliza.get("precio"):
        _kv(pdf, "Prima mensual", "$" + f"{int(poliza['precio']):,}".replace(",", "."))
    if poliza.get("referencia"):
        _kv(pdf, "Referencia de pago", poliza["referencia"])
    pdf.ln(3)

    bien = poliza.get("bien")
    if bien and bien.get("items"):
        _section(pdf, bien.get("titulo", "Bien asegurado"))
        for item in bien["items"]:
            k, v = (item[0], item[1]) if isinstance(item, (list, tuple)) else ("Dato", item)
            _kv(pdf, str(k), str(v))
        pdf.ln(3)

    _section(pdf, "Amparos incluidos")
    _bullets(pdf, poliza.get("cubre", []))
    _section(pdf, "Exclusiones")
    _bullets(pdf, poliza.get("no_cubre", []))

    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(0, 5, sanitize(
        "Ante un siniestro comunicate con la linea nacional 018000 94 7900. "
        "Fuente de condiciones: " + poliza.get("fuente", "")),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    fname = f"poliza_{poliza['numero']}.pdf"
    pdf.output(str(DOCS_DIR / fname))
    return fname
