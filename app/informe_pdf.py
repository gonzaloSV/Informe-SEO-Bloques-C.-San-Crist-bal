"""
informe_pdf.py
Genera el informe en PDF con los mismos datos que muestra la app.
Solo depende de reportlab (no necesita navegador ni librerías del sistema),
así que funciona igual en el Mac que en Streamlit Cloud.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import gsc_core as core

BLOCK_COLORS = {"Captación": "#d9822b", "Marca": "#0f6b5c", "Blog": "#8a5a9e", "Plataformas alumnos": "#5b6b8c"}
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#e5e7eb")
ZEBRA = colors.HexColor("#f7f7f5")
BRAND = colors.HexColor("#0f6b5c")
GOOD = colors.HexColor("#0f7a3d")
BAD = colors.HexColor("#b42318")

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ---------- Formato ----------

def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def fmt_pct(x, dec=2):
    return f"{x * 100:.{dec}f} %".replace(".", ",")


def fmt_pos(x):
    return f"{x:.1f}".replace(".", ",") if x and pd.notna(x) else "–"


def fmt_signed(n):
    return ("+" if n > 0 else "") + fmt_int(n) if n else "0"


def fmt_signed_dec(x):
    if pd.isna(x):
        return "–"
    if abs(x) < 0.05:
        return "0,0"
    return ("+" if x > 0 else "") + f"{x:.1f}".replace(".", ",")


def rel_change(cur, prev):
    return None if not prev else (cur - prev) / prev


def short_path(url, limit=60):
    p = urlparse(url).path or "/"
    return p if len(p) <= limit else p[: limit - 1] + "…"


def lighten(hex_color, amount=0.6):
    c = colors.HexColor(hex_color)
    return colors.Color(c.red + (1 - c.red) * amount, c.green + (1 - c.green) * amount, c.blue + (1 - c.blue) * amount)


# ---------- Estilos ----------

S = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=BRAND,
                         spaceBefore=14, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK,
                         spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK,
                             leftIndent=10, bulletIndent=0, spaceAfter=3),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.8, leading=9.5, textColor=INK),
    "cell_r": ParagraphStyle("cell_r", fontName="Helvetica", fontSize=7.8, leading=9.5, textColor=INK, alignment=TA_RIGHT),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.white),
    "head_r": ParagraphStyle("head_r", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.white,
                             alignment=TA_RIGHT),
    "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
    "kpi_value": ParagraphStyle("kpi_value", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK),
    "kpi_delta": ParagraphStyle("kpi_delta", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
}


def P(text, style="body"):
    return Paragraph(text, S[style])


def colored(text, good):
    if good is None:
        return text
    return f'<font color="{(GOOD if good else BAD).hexval().replace("0x", "#")}">{text}</font>'


# ---------- Piezas ----------

def kpi_boxes(cur_df, prev_df):
    t = core.totals(cur_df)
    p = core.totals(prev_df) if prev_df is not None else None
    capt = core.totals(cur_df[cur_df["bloque"] == "Captación"])
    capt_p = core.totals(prev_df[prev_df["bloque"] == "Captación"]) if prev_df is not None else None

    def rel(a, b):
        ch = rel_change(a, b)
        return None if ch is None else (("+" if ch > 0 else "") + fmt_pct(ch, 1), ch > 0 if ch else None)

    def pp(a, b):
        d = (a - b) * 100
        return f"{d:+.2f}".replace(".", ",") + " p.p.", (d > 0 if d else None)

    def pos(a, b):
        if not a or not b:
            return None
        d = a - b
        if abs(d) < 0.05:
            return "0,0", None
        return f"{d:+.1f}".replace(".", ","), d < 0  # bajar de posición es mejorar

    items = [
        ("Clics", fmt_int(t["clicks"]), p and rel(t["clicks"], p["clicks"])),
        ("Impresiones", fmt_int(t["impressions"]), p and rel(t["impressions"], p["impressions"])),
        ("CTR", fmt_pct(t["ctr"]), p and pp(t["ctr"], p["ctr"])),
        ("Posición media", fmt_pos(t["position"]), p and pos(t["position"], p["position"])),
        ("Clics de captación", fmt_int(capt["clicks"]), capt_p and rel(capt["clicks"], capt_p["clicks"])),
    ]
    cells = []
    for label, value, delta in items:
        d = colored(*delta) if delta else ("sin comparar" if prev_df is None else "–")
        cells.append([P(label, "kpi_label"), P(value, "kpi_value"), P(d, "kpi_delta")])
    tbl = Table([cells], colWidths=[CONTENT_W / 5] * 5)
    tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def hbar_chart(rows, width=CONTENT_W, label_w=58 * mm, legend=None):
    """rows: lista de (etiqueta, valor, valor_anterior | None, color hex)."""
    has_prev = any(r[2] is not None for r in rows)
    bar_h, gap_in, gap_out = (7, 2, 9) if has_prev else (10, 0, 7)
    group_h = bar_h * (2 if has_prev else 1) + gap_in + gap_out
    legend_h = 16 if legend and has_prev else 0
    height = group_h * len(rows) + legend_h + 4
    d = Drawing(width, height)
    max_v = max([r[1] for r in rows] + [r[2] or 0 for r in rows] + [1])
    num_w = 40
    plot_w = width - label_w - num_w

    y = height - 2
    for label, val, prev, color in rows:
        y -= group_h - gap_out
        text = label if len(label) <= 48 else label[:47] + "…"
        d.add(String(label_w - 6, y + (group_h - gap_out) / 2 - 3, text, fontName="Helvetica", fontSize=7.8,
                     fillColor=INK, textAnchor="end"))
        top = y + (bar_h + gap_in if has_prev else 0)
        w = plot_w * val / max_v
        d.add(Rect(label_w, top, max(w, 0.5), bar_h, fillColor=colors.HexColor(color), strokeColor=None))
        d.add(String(label_w + w + 4, top + bar_h / 2 - 2.6, fmt_int(val), fontName="Helvetica-Bold", fontSize=7.2,
                     fillColor=INK))
        if has_prev:
            pv = prev or 0
            w2 = plot_w * pv / max_v
            d.add(Rect(label_w, y, max(w2, 0.5), bar_h, fillColor=lighten(color, 0.62), strokeColor=None))
            d.add(String(label_w + w2 + 4, y + bar_h / 2 - 2.6, fmt_int(pv), fontName="Helvetica", fontSize=7,
                         fillColor=MUTED))
        y -= gap_out
    d.add(Line(label_w, y + gap_out - 2, label_w, height - 2, strokeColor=RULE, strokeWidth=0.6))

    if legend_h:
        lx = label_w
        for name, fill in ((legend[0], colors.HexColor("#555b63")), (legend[1], lighten("#555b63", 0.62))):
            d.add(Rect(lx, 3, 9, 7, fillColor=fill, strokeColor=None))
            d.add(String(lx + 13, 4, name, fontName="Helvetica", fontSize=7.5, fillColor=MUTED))
            lx += 13 + len(name) * 4.1 + 18
    return d


def data_table(df, spec, has_prev):
    """spec: lista de (columna, cabecera, tipo, ancho_relativo).
    Tipos: text, int, dint, pct, pos, dpos. Las columnas de variación se omiten si no hay comparación."""
    spec = [s for s in spec if has_prev or s[2] not in ("dint", "dpos")]
    total = sum(s[3] for s in spec)
    widths = [CONTENT_W * s[3] / total for s in spec]
    header = [P(escape(h), "head" if kind == "text" else "head_r") for _, h, kind, _ in spec]
    body = []
    for _, r in df.iterrows():
        row = []
        for col, _, kind, _ in spec:
            v = r.get(col)
            if kind == "text":
                row.append(P(escape(str(v)), "cell"))
                continue
            if kind == "int":
                txt = fmt_int(v)
            elif kind == "pct":
                txt = fmt_pct(v)
            elif kind == "pos":
                txt = fmt_pos(v)
            elif kind == "dint":
                txt = colored(fmt_signed(v), (v > 0) if v else None)
            else:  # dpos
                txt = colored(fmt_signed_dec(v), (v < 0) if pd.notna(v) and abs(v) >= 0.05 else None)
            row.append(P(txt, "cell_r"))
        body.append(row)
    tbl = Table([header] + body, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(body) + 1, 2)]
    tbl.setStyle(TableStyle(style))
    return tbl


# ---------- Resumen automático ----------

def highlights(cur_df, prev_df):
    out = []
    t = core.totals(cur_df)
    p = core.totals(prev_df) if prev_df is not None else None
    if p and p["clicks"]:
        ch = rel_change(t["clicks"], p["clicks"])
        verbo = "suben" if ch > 0 else "bajan" if ch < 0 else "se mantienen"
        extra = f" un {fmt_pct(abs(ch), 1)}" if ch else ""
        out.append(f"Los clics {verbo}{extra}: de {fmt_int(p['clicks'])} a <b>{fmt_int(t['clicks'])}</b>. "
                   f"Las impresiones pasan de {fmt_int(p['impressions'])} a {fmt_int(t['impressions'])}.")
    else:
        out.append(f"<b>{fmt_int(t['clicks'])}</b> clics y {fmt_int(t['impressions'])} impresiones en el periodo.")

    capt = cur_df[cur_df["bloque"] == "Captación"]
    ct = core.totals(capt)
    if t["clicks"]:
        line = (f"La captación aporta el <b>{fmt_pct(ct['clicks'] / t['clicks'], 1)}</b> de los clics "
                f"({fmt_int(ct['clicks'])}) con una posición media de {fmt_pos(ct['position'])}.")
        if prev_df is not None:
            cp = core.totals(prev_df[prev_df["bloque"] == "Captación"])
            ch = rel_change(ct["clicks"], cp["clicks"])
            if ch is not None and ch != 0:
                line += f" Frente al periodo de comparación, {'crece' if ch > 0 else 'cae'} un {fmt_pct(abs(ch), 1)}."
        out.append(line)

    if not capt.empty:
        q = core.aggregate(capt, "query").sort_values(["clicks", "impressions"], ascending=False).iloc[0]
        if q["clicks"] > 0:
            out.append(f"La búsqueda de captación que más clics trae es «{escape(q['query'])}»: "
                       f"{fmt_int(q['clicks'])} clics en posición {fmt_pos(q['position'])}.")

    if prev_df is not None:
        pages = core.compare(capt, prev_df[prev_df["bloque"] == "Captación"], "page")
        if not pages.empty:
            up = pages.sort_values("d_clicks", ascending=False).iloc[0]
            down = pages.sort_values("d_clicks").iloc[0]
            if up["d_clicks"] > 0:
                out.append(f"Página de captación que más clics gana: {escape(short_path(up['page']))} "
                           f"({fmt_signed(up['d_clicks'])}).")
            if down["d_clicks"] < 0:
                out.append(f"La que más pierde: {escape(short_path(down['page']))} ({fmt_signed(down['d_clicks'])}). "
                           "Conviene revisar si ha bajado de posición o si la demanda es estacional.")

    opp = core.aggregate(capt, ["query", "page"]) if not capt.empty else pd.DataFrame()
    if not opp.empty:
        opp = opp[(opp["position"] >= 4) & (opp["position"] <= 20)]
        if not opp.empty:
            out.append(f"Hay <b>{fmt_int(len(opp))}</b> búsquedas de captación entre las posiciones 4 y 20 que suman "
                       f"{fmt_int(opp['impressions'].sum())} impresiones. Es el margen más rápido para ganar clics.")
    return out


# ---------- Documento ----------

def build_report(site: str, cur_label: str, prev_label: str | None, cur_df: pd.DataFrame,
                 prev_df: pd.DataFrame | None) -> bytes:
    domain = core.property_domain(site)
    has_prev = prev_df is not None
    generated = datetime.now().strftime("%d/%m/%Y")

    def part(df, bloque):
        return None if df is None else df[df["bloque"] == bloque]

    def by(bloque, key, n, sort="impressions"):
        c = core.compare(part(cur_df, bloque), part(prev_df, bloque), key)
        c = c[c["impressions"] > 0].sort_values([sort, "clicks"], ascending=False).head(n).copy()
        if "page" in c.columns:
            c["pagina"] = c["page"].map(lambda u: short_path(u, 48))
        return c

    cols_page = [("pagina", "Página", "text", 30), ("clicks", "Clics", "int", 7), ("d_clicks", "Var. clics", "dint", 8),
                 ("impressions", "Impr.", "int", 8), ("d_impressions", "Var. impr.", "dint", 8),
                 ("ctr", "CTR", "pct", 7), ("position", "Pos.", "pos", 6), ("d_position", "Var. pos.", "dpos", 7)]
    cols_query = [("query", "Consulta", "text", 30)] + cols_page[1:]

    story = [
        P("Informe SEO por bloques", "title"),
        Spacer(1, 3),
        P(f"<b>{escape(domain)}</b> · {cur_label}"
          + (f" · comparado con {prev_label}" if prev_label else "") + f"<br/>Datos de Google Search Console · "
          f"generado el {generated}", "meta"),
        Spacer(1, 12),
        kpi_boxes(cur_df, prev_df),
        P("Lo más destacado", "h2"),
    ]
    story += [Paragraph(h, S["bullet"], bulletText="•") for h in highlights(cur_df, prev_df)]

    # Bloques
    cmp = core.compare(cur_df, prev_df, "bloque")
    order = [b for b in core.BLOQUES if b in set(cmp["bloque"])]
    cmp = cmp.set_index("bloque").reindex(order).reset_index()
    rows = [(r["bloque"], int(r["clicks"]), int(r["clicks_prev"]) if has_prev else None, BLOCK_COLORS[r["bloque"]])
            for _, r in cmp.iterrows()]
    total_c = cmp["clicks"].sum() or 1
    total_i = cmp["impressions"].sum() or 1
    cmp["cuota_clics"] = cmp["clicks"] / total_c
    cmp["cuota_impr"] = cmp["impressions"] / total_i
    story.append(KeepTogether([
        P("Bloques de búsqueda", "h2"),
        P("Clics por bloque" + (" (periodo actual frente al de comparación)" if has_prev else ""), "note"),
        Spacer(1, 4),
        hbar_chart(rows, label_w=40 * mm, legend=[cur_label, prev_label] if has_prev else None),
        Spacer(1, 8),
        data_table(cmp, [("bloque", "Bloque", "text", 18), ("clicks", "Clics", "int", 8),
                         ("d_clicks", "Var. clics", "dint", 8), ("cuota_clics", "% clics", "pct", 8),
                         ("impressions", "Impr.", "int", 9), ("d_impressions", "Var. impr.", "dint", 9),
                         ("cuota_impr", "% impr.", "pct", 8), ("ctr", "CTR", "pct", 7),
                         ("position", "Pos.", "pos", 6), ("d_position", "Var. pos.", "dpos", 7)], has_prev),
    ]))

    # Captación
    pages = by("Captación", "page", 15)
    if pages.empty:
        story += [P("Captación", "h2"), P("Sin búsquedas de captación en este periodo.")]
    else:
        top = pages.head(10)
        chart_rows = [(r["pagina"], int(r["impressions"]), int(r["impressions_prev"]) if has_prev else None,
                       BLOCK_COLORS["Captación"]) for _, r in top.iterrows()]
        story += [
            KeepTogether([P("Captación", "h2"), P("Páginas con más impresiones de captación", "h3"),
                          hbar_chart(chart_rows, legend=[cur_label, prev_label] if has_prev else None)]),
            Spacer(1, 8),
            data_table(pages, cols_page, has_prev),
            P("Consultas de captación con más impresiones", "h3"),
            data_table(by("Captación", "query", 25), cols_query, has_prev),
        ]

    # Oportunidades
    opp = core.compare(part(cur_df, "Captación"), part(prev_df, "Captación"), ["query", "page"])
    opp = opp[(opp["position"] >= 4) & (opp["position"] <= 20) & (opp["impressions"] > 0)]
    opp = opp.sort_values("impressions", ascending=False).head(20).copy()
    story += [P("Oportunidades (posiciones 4 a 20)", "h2"),
              P("Búsquedas de captación que ya están cerca de la primera página. Subirlas unas posiciones "
                "suele traer más clics que trabajar palabras clave nuevas.", "note"), Spacer(1, 5)]
    if opp.empty:
        story.append(P("No hay búsquedas de captación entre las posiciones 4 y 20."))
    else:
        opp["pagina"] = opp["page"].map(lambda u: short_path(u, 40))
        story.append(data_table(opp, [("query", "Consulta", "text", 26), ("pagina", "Página", "text", 22),
                                      ("impressions", "Impr.", "int", 8), ("clicks", "Clics", "int", 7),
                                      ("ctr", "CTR", "pct", 7), ("position", "Pos.", "pos", 6),
                                      ("d_position", "Var. pos.", "dpos", 7)], has_prev))

    # Resto de bloques
    for bloque, key, title, cols, empty in (
        ("Blog", "page", "Blog: páginas con más impresiones", cols_page, "Sin búsquedas genéricas que lleguen al blog."),
        ("Marca", "query", "Marca: consultas principales", cols_query, "Sin búsquedas de marca."),
        ("Plataformas alumnos", "query", "Plataformas de alumnos: consultas principales", cols_query,
         "Sin búsquedas de plataformas."),
    ):
        data = by(bloque, key, 10)
        story.append(KeepTogether([P(title, "h2"), P(empty) if data.empty else data_table(data, cols, has_prev)]))

    story += [
        P("Cómo se clasifican las búsquedas", "h2"),
        P("<b>Plataformas alumnos</b>: la consulta menciona una plataforma (Moodle, Clickedu, aula virtual…). "
          "<b>Marca</b>: la consulta contiene el nombre del centro. <b>Blog</b>: búsqueda genérica que llega a una "
          "entrada del blog. <b>Captación</b>: búsqueda genérica que llega a la home, a una ficha o a un formulario. "
          "En la variación de posición, un número negativo es una mejora (la página sube). "
          "Las posiciones se ponderan por impresiones y los datos de los últimos 2-3 días pueden variar hasta que "
          "Google los consolida.", "note"),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 7 * mm, f"Informe SEO · {domain} · {cur_label}")
        canvas.drawRightString(PAGE_W - MARGIN, 7 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=18 * mm, title=f"Informe SEO {domain} {cur_label}",
                            author="Informe SEO San Cristóbal")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
