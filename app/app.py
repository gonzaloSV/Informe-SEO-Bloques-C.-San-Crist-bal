"""
Informe SEO San Cristóbal · app Streamlit
Analiza Search Console por bloques (Captación, Marca, Blog, Plataformas alumnos)
y compara con el periodo anterior.

Arranque local:  streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import gsc_core as core

st.set_page_config(page_title="SEO San Cristóbal", page_icon="📈", layout="wide")

SITES = {
    "FP San Cristóbal · fpsancristobal.es": {"site": "sc-domain:fpsancristobal.es", "brand": "san cristobal"},
    "Colegio San Cristóbal · sancristobalsl.com": {"site": "sc-domain:sancristobalsl.com", "brand": "san cristobal"},
    "Otra web (escribir URL)": None,
}
COLORS = {"Captación": "#d9822b", "Marca": "#0f6b5c", "Blog": "#8a5a9e", "Plataformas alumnos": "#5b6b8c"}
COLOR_SCALE = alt.Scale(domain=list(COLORS), range=list(COLORS.values()))
COMPARE_MODES = {"Periodo anterior": "anterior", "Mismo periodo del año anterior": "interanual", "Sin comparar": "ninguno"}


# ---------- Acceso ----------

def _secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


def check_password() -> bool:
    expected = _secret("APP_PASSWORD")
    if not expected or st.session_state.get("auth_ok"):
        return True
    st.title("Informe SEO San Cristóbal")
    with st.form("login"):
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar"):
            if pwd == expected:
                st.session_state["auth_ok"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    return False


@st.cache_resource
def get_service():
    info = _secret("gcp_service_account")
    if info is None:
        here = Path(__file__).resolve().parent
        local = next((p for p in (here / "credentials.json", here.parent / "credentials.json") if p.exists()), None)
        if local is None:
            st.error("Faltan las credenciales: añade `gcp_service_account` en los secretos o un credentials.json junto a app.py.")
            st.stop()
        info = json.loads(local.read_text(encoding="utf-8"))
    return core.build_service(core.credentials_from_info(info))


# ---------- Datos ----------

@st.cache_data(ttl=3600, show_spinner=False)
def load_period(site, start, end, brand, platforms):
    paths = load_paths(site)
    return core.run_analysis(get_service(), site, start, end, brand, platforms, paths)


@st.cache_data(ttl=86400, show_spinner=False)
def load_paths(site):
    return core.load_site_paths(site)


def show_chart(chart):
    """Compatible con Streamlit antiguo (use_container_width) y nuevo (width)."""
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


# ---------- Formato ----------

def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def fmt_pct(x, dec=2):
    return f"{x * 100:.{dec}f} %".replace(".", ",")


def fmt_pos(x):
    return f"{x:.1f}".replace(".", ",") if x else "–"


def fmt_delta(n):
    return ("+" if n > 0 else "") + fmt_int(n) if n else "0"


def pct_change(cur, prev):
    if not prev:
        return None
    return (cur - prev) / prev


def table(df: pd.DataFrame, cols: dict, has_prev: bool, height=None):
    """Muestra una tabla con nombres en castellano y formato de número."""
    show = {k: v for k, v in cols.items() if k in df.columns and (has_prev or not k.endswith(("_prev",)) and not k.startswith("d_"))}
    out = df[list(show)].rename(columns=show)
    fmt = {}
    for k, v in show.items():
        if k in ("ctr", "ctr_prev"):
            fmt[v] = lambda x: fmt_pct(x)
        elif k in ("position", "position_prev"):
            fmt[v] = lambda x: fmt_pos(x) if pd.notna(x) else "–"
        elif k == "d_position":
            fmt[v] = lambda x: ("+" if x > 0 else "") + f"{x:.1f}".replace(".", ",") if pd.notna(x) else "–"
        elif k.startswith("d_"):
            fmt[v] = fmt_delta
        elif k in ("clicks", "impressions", "clicks_prev", "impressions_prev"):
            fmt[v] = fmt_int
    kwargs = {"height": height} if height else {}
    st.dataframe(out.style.format(fmt), hide_index=True, width="stretch", **kwargs)


# ---------- Interfaz ----------

def sidebar():
    with st.sidebar:
        st.header("Análisis")
        with st.form("params"):
            choice = st.selectbox("Web", list(SITES))
            custom = st.text_input(
                "URL o dominio (solo para 'Otra web')",
                placeholder="midominio.com o https://www.midominio.com/",
                help="Un dominio se consulta como propiedad de dominio (sc-domain:). "
                     "Una URL con https:// se consulta como propiedad de prefijo de URL. "
                     "La cuenta de servicio debe tener acceso a esa propiedad en Search Console.",
            )
            d_start, d_end = core.previous_month()
            dates = st.date_input("Fechas", value=(d_start, d_end), max_value=date.today(), format="DD/MM/YYYY")
            compare_label = st.radio("Comparar con", list(COMPARE_MODES), index=0)
            with st.expander("Ajustes de clasificación"):
                preset = SITES.get(choice) or {}
                brand = st.text_input("Términos de marca", value=preset.get("brand", ""),
                                      help="Separados por comas. Admiten tildes, guiones o palabras juntas.")
                platforms = st.text_input("Plataformas de alumnos", value=core.DEFAULT_PLATFORMS)
            submitted = st.form_submit_button("Analizar", type="primary", width="stretch")

    if SITES[choice] is None:
        site = core.normalize_property(custom)
        if not site:
            return None
    else:
        site = SITES[choice]["site"]
    if not isinstance(dates, (list, tuple)) or len(dates) != 2:
        st.sidebar.warning("Elige fecha de inicio y de fin.")
        return None
    return {
        "site": site,
        "start": dates[0],
        "end": dates[1],
        "mode": COMPARE_MODES[compare_label],
        "brand": tuple(t.strip() for t in brand.split(",") if t.strip()),
        "platforms": tuple(t.strip() for t in platforms.split(",") if t.strip()),
        "submitted": submitted,
    }


def kpi_row(cur, prev, cur_df, prev_df):
    t, p = core.totals(cur_df), core.totals(prev_df) if prev_df is not None else None
    capt = core.totals(cur_df[cur_df["bloque"] == "Captación"])
    capt_p = core.totals(prev_df[prev_df["bloque"] == "Captación"]) if prev_df is not None else None

    def delta(a, b, kind="int"):
        if b is None:
            return None
        if kind == "pct_rel":
            ch = pct_change(a, b)
            return None if ch is None else fmt_pct(ch, 1)
        if kind == "pp":
            return f"{(a - b) * 100:+.2f}".replace(".", ",") + " p.p."
        if kind == "pos":
            return f"{a - b:+.1f}".replace(".", ",")

    c = st.columns(5)
    c[0].metric("Clics", fmt_int(t["clicks"]), delta(t["clicks"], p and p["clicks"], "pct_rel"))
    c[1].metric("Impresiones", fmt_int(t["impressions"]), delta(t["impressions"], p and p["impressions"], "pct_rel"))
    c[2].metric("CTR", fmt_pct(t["ctr"]), delta(t["ctr"], p and p["ctr"], "pp"))
    c[3].metric("Posición media", fmt_pos(t["position"]), delta(t["position"], p and p["position"], "pos"),
                delta_color="inverse")
    c[4].metric("Clics de captación", fmt_int(capt["clicks"]), delta(capt["clicks"], capt_p and capt_p["clicks"], "pct_rel"))


def block_section(cmp, has_prev, labels):
    st.subheader("Bloques de búsqueda")
    order = [b for b in core.BLOQUES if b in set(cmp["bloque"])]
    cmp = cmp.set_index("bloque").reindex(order).reset_index()

    left, right = st.columns([3, 2])
    with left:
        rows = []
        for _, r in cmp.iterrows():
            rows.append({"bloque": r["bloque"], "periodo": labels[0], "clics": r["clicks"], "impresiones": r["impressions"]})
            if has_prev:
                rows.append({"bloque": r["bloque"], "periodo": labels[1], "clics": r["clicks_prev"], "impresiones": r["impressions_prev"]})
        long = pd.DataFrame(rows)
        metric = st.radio("Métrica", ["clics", "impresiones"], horizontal=True, key="block_metric", label_visibility="collapsed")
        chart = (
            alt.Chart(long)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                y=alt.Y("bloque:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)),
                x=alt.X(f"{metric}:Q", title=metric.capitalize()),
                color=alt.Color("bloque:N", scale=COLOR_SCALE, legend=None),
                opacity=alt.Opacity("periodo:N", scale=alt.Scale(domain=labels, range=[1, 0.35]),
                                    legend=alt.Legend(title=None, orient="bottom")),
                yOffset=alt.YOffset("periodo:N", sort=labels),
                tooltip=["bloque", "periodo", alt.Tooltip(f"{metric}:Q", format=",")],
            )
            .properties(height=260)
        )
        show_chart(chart)
    with right:
        share_rows = []
        for medida, col in (("Impresiones", "impressions"), ("Clics", "clicks")):
            total = cmp[col].sum() or 1
            for _, r in cmp.iterrows():
                share_rows.append({"bloque": r["bloque"], "medida": medida, "valor": int(r[col]),
                                   "cuota": r[col] / total, "orden": order.index(r["bloque"])})
        share_long = pd.DataFrame(share_rows)
        donut = (
            alt.Chart(share_long, title="Reparto del periodo actual")
            .mark_bar()
            .encode(
                y=alt.Y("medida:N", title=None, sort="descending", scale=alt.Scale(paddingInner=0.35)),
                x=alt.X("cuota:Q", stack="zero", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", title=None)),
                color=alt.Color("bloque:N", scale=COLOR_SCALE, legend=alt.Legend(title=None, orient="bottom", columns=2)),
                order=alt.Order("orden:Q"),
                tooltip=["bloque", "medida", alt.Tooltip("valor:Q", title="Total", format=","),
                         alt.Tooltip("cuota:Q", title="Cuota", format=".1%")],
            )
            .properties(height=alt.Step(40))
        )
        show_chart(donut)

    table(cmp, {
        "bloque": "Bloque", "clicks": "Clics", "clicks_prev": "Clics ant.", "d_clicks": "Δ clics",
        "impressions": "Impresiones", "impressions_prev": "Impr. ant.", "d_impressions": "Δ impr.",
        "ctr": "CTR", "position": "Posición", "d_position": "Δ pos.",
    }, has_prev)


def short_path(url):
    from urllib.parse import urlparse
    p = urlparse(url).path or "/"
    return p if len(p) <= 70 else p[:67] + "…"


def url_section(cur_df, prev_df, has_prev):
    """Palabras clave de una URL concreta, con las páginas ordenadas por importancia."""
    from urllib.parse import urlparse

    st.caption("Elige una página del desplegable (ordenadas por clics y, a igualdad, por impresiones) "
               "o pega una URL. Por defecto solo se muestran búsquedas de captación con intención comercial o transaccional.")
    c1, c2, c3 = st.columns([3, 3, 2])
    blocks = c1.multiselect("Bloques", core.BLOQUES, default=["Captación"], key="url_blocks")
    intents = c2.multiselect("Intención", core.INTENCIONES, default=["Transaccional", "Comercial"], key="url_intents",
                             help="Transaccional: matrícula, precio, plazas, requisitos… "
                                  "Comercial: busca un ciclo o un centro. Informativa: salidas, sueldo, qué es…")
    order_by = c3.radio("Ordenar por", ["Clics", "Impresiones"], key="url_order")

    def filt(df):
        if df is None:
            return None
        return df[df["bloque"].isin(blocks) & df["intencion"].isin(intents)]

    cur_f, prev_f = filt(cur_df), filt(prev_df)
    pages = core.aggregate(cur_f, "page")
    if pages.empty:
        st.info("No hay búsquedas con esos filtros en el periodo.")
        return
    pages = pages.sort_values(["clicks", "impressions"], ascending=False)
    labels = {r.page: f"{short_path(r.page)}   ·   {fmt_int(r.clicks)} clics · {fmt_int(r.impressions)} impr."
              for r in pages.itertuples()}

    sel_col, url_col = st.columns([3, 2])
    page = sel_col.selectbox(f"Página ({len(pages)} con búsquedas)", pages["page"].tolist(),
                             format_func=lambda u: labels.get(u, u), key="url_select")
    manual = url_col.text_input("…o pega una URL", key="url_manual",
                                placeholder="https://fpsancristobal.es/ciclo-fp-dietetica/")
    if manual.strip():
        path = (urlparse(manual.strip()).path or manual.strip()).split("#")[0].rstrip("/") or "/"
        found = [u for u in cur_df["page"].unique() if ((urlparse(u).path.rstrip("/")) or "/") == path]
        if not found:
            st.warning("Esa URL no tiene búsquedas en este periodo. Revisa que pertenezca a la web seleccionada.")
            return
        page = found[0]

    cur_p = cur_f[cur_f["page"] == page]
    prev_p = prev_f[prev_f["page"] == page] if prev_f is not None else None
    st.markdown(f"**[{page}]({page})**")
    if cur_p.empty:
        st.info("Esta página no tiene búsquedas con los filtros elegidos. Prueba a añadir bloques o intenciones.")
        return

    t = core.totals(cur_p)
    tp = core.totals(prev_p) if prev_p is not None and not prev_p.empty else None
    m = st.columns(5)
    m[0].metric("Clics", fmt_int(t["clicks"]), None if tp is None else fmt_delta(t["clicks"] - tp["clicks"]))
    m[1].metric("Impresiones", fmt_int(t["impressions"]),
                None if tp is None else fmt_delta(t["impressions"] - tp["impressions"]))
    m[2].metric("CTR", fmt_pct(t["ctr"]))
    m[3].metric("Posición media", fmt_pos(t["position"]),
                None if tp is None else f"{t['position'] - tp['position']:+.1f}".replace(".", ","), delta_color="inverse")
    m[4].metric("Palabras clave", fmt_int(cur_p["query"].nunique()))

    q = core.compare(cur_p, prev_p, ["query", "intencion"])
    q = q[q["impressions"] > 0]
    key = "clicks" if order_by == "Clics" else "impressions"
    q = q.sort_values([key, "impressions" if key == "clicks" else "clicks"], ascending=False)

    def kw_chart(data, field, title, color):
        data = data[data[field] > 0].sort_values(field, ascending=False).head(15)
        if data.empty:
            st.caption(f"{title}: sin datos en este periodo.")
            return
        chart = (
            alt.Chart(data, title=title)
            .mark_bar(color=color, cornerRadiusEnd=3)
            .encode(
                y=alt.Y("query:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260, labelOverlap=False)),
                x=alt.X(f"{field}:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                tooltip=[alt.Tooltip("query:N", title="Palabra clave"),
                         alt.Tooltip("impressions:Q", title="Impresiones", format=","),
                         alt.Tooltip("clicks:Q", title="Clics"),
                         alt.Tooltip("position:Q", title="Posición", format=".1f")],
            )
            .properties(height=max(180, 30 * len(data)))
        )
        show_chart(chart)

    g1, g2 = st.columns(2)
    with g1:
        kw_chart(q, "impressions", "Más impresiones (vistas)", "#e9a15c")
    with g2:
        kw_chart(q, "clicks", "Más clics", COLORS["Captación"])

    table(q, {"query": "Palabra clave", "intencion": "Intención", "clicks": "Clics", "d_clicks": "Δ clics",
              "impressions": "Impresiones", "d_impressions": "Δ impr.", "ctr": "CTR",
              "position": "Posición", "d_position": "Δ pos."}, has_prev, height=min(600, 38 * (len(q) + 1)))
    export = q.rename(columns={"query": "palabra_clave", "clicks": "clics", "impressions": "impresiones",
                               "position": "posicion"})
    st.download_button("Descargar palabras clave de esta URL (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"keywords_{short_path(page).strip('/').replace('/', '_') or 'home'}.csv",
                       mime="text/csv", key="url_dl")


def detail_section(cur_df, prev_df, has_prev):
    tabs = st.tabs(["Palabras clave por URL", "Captación", "Oportunidades", "Blog", "Marca", "Plataformas alumnos"])
    cols_page = {"pagina": "Página", "clicks": "Clics", "d_clicks": "Δ clics", "impressions": "Impresiones",
                 "d_impressions": "Δ impr.", "ctr": "CTR", "position": "Posición", "d_position": "Δ pos."}
    cols_query = {"query": "Consulta", "clicks": "Clics", "d_clicks": "Δ clics", "impressions": "Impresiones",
                  "d_impressions": "Δ impr.", "ctr": "CTR", "position": "Posición", "d_position": "Δ pos."}

    def part(df, bloque):
        return None if df is None else df[df["bloque"] == bloque]

    def by_page(bloque, n=15):
        c = core.compare(part(cur_df, bloque), part(prev_df, bloque), "page")
        c = c[c["impressions"] > 0].sort_values("impressions", ascending=False).head(n)
        c["pagina"] = c["page"].map(short_path)
        return c

    def by_query(bloque, n=25):
        c = core.compare(part(cur_df, bloque), part(prev_df, bloque), "query")
        return c[c["impressions"] > 0].sort_values("impressions", ascending=False).head(n)

    with tabs[0]:
        url_section(cur_df, prev_df, has_prev)

    with tabs[1]:
        pages = by_page("Captación")
        if pages.empty:
            st.info("Sin búsquedas de captación en este periodo.")
        else:
            bar = (
                alt.Chart(pages)
                .mark_bar(color=COLORS["Captación"], cornerRadiusEnd=3)
                .encode(
                    y=alt.Y("pagina:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
                    x=alt.X("impressions:Q", title="Impresiones"),
                    tooltip=[alt.Tooltip("pagina:N", title="Página"), alt.Tooltip("impressions:Q", title="Impresiones", format=","),
                             alt.Tooltip("clicks:Q", title="Clics"), alt.Tooltip("position:Q", title="Posición", format=".1f")],
                )
                .properties(height=max(180, 28 * len(pages)))
            )
            show_chart(bar)
            table(pages, cols_page, has_prev)
            st.markdown("**Consultas de captación**")
            table(by_query("Captación"), cols_query, has_prev, height=420)

    with tabs[2]:
        st.caption("Consultas de captación entre las posiciones 4 y 20, ordenadas por impresiones: "
                   "las que más rápido pueden ganar clics al subir a primera página.")
        opp = core.compare(part(cur_df, "Captación"), part(prev_df, "Captación"), ["query", "page"])
        opp = opp[(opp["position"] >= 4) & (opp["position"] <= 20) & (opp["impressions"] > 0)]
        opp = opp.sort_values("impressions", ascending=False).head(30)
        opp["pagina"] = opp["page"].map(short_path)
        if opp.empty:
            st.info("No hay consultas de captación entre las posiciones 4 y 20.")
        else:
            table(opp, {"query": "Consulta", "pagina": "Página", **{k: v for k, v in cols_query.items() if k != "query"}},
                  has_prev, height=520)

    with tabs[3]:
        pages = by_page("Blog")
        if pages.empty:
            st.info("Sin búsquedas genéricas que lleguen al blog en este periodo.")
        else:
            table(pages, cols_page, has_prev)
            st.markdown("**Consultas que llegan al blog**")
            table(by_query("Blog", 20), cols_query, has_prev)

    with tabs[4]:
        q = by_query("Marca", 20)
        st.info("Sin búsquedas de marca.") if q.empty else table(q, cols_query, has_prev)

    with tabs[5]:
        q = by_query("Plataformas alumnos", 20)
        st.info("Sin búsquedas de plataformas.") if q.empty else table(q, cols_query, has_prev)


def label_period(a, b):
    return f"{a:%d/%m/%Y} – {b:%d/%m/%Y}"


def main():
    if not check_password():
        return
    params = sidebar()
    st.title("Informe SEO por bloques")
    if params is None:
        st.info("Escribe el dominio o la URL de la web en la barra lateral y pulsa **Analizar**.")
        return

    site, start, end = params["site"], params["start"], params["end"]
    prev_range = core.comparison_period(start, end, params["mode"])
    cur_label = label_period(start, end)
    prev_label = label_period(*prev_range) if prev_range else None
    st.caption(f"**{site}** · {cur_label}" + (f" · comparado con {prev_label}" if prev_label else ""))

    try:
        with st.spinner("Descargando datos de Search Console…"):
            cur_df = load_period(site, start, end, params["brand"], params["platforms"])
            prev_df = load_period(site, *prev_range, params["brand"], params["platforms"]) if prev_range else None
    except Exception as e:  # permisos, propiedad inexistente, cuota…
        msg = str(e)
        if "403" in msg or "permission" in msg.lower():
            st.error(f"La cuenta de servicio no tiene acceso a **{site}**. Añádela como usuario de esa propiedad en Search Console.")
        elif "404" in msg or "not found" in msg.lower():
            st.error(f"No existe la propiedad **{site}** en Search Console. Prueba con el dominio o con la URL completa (https://…/).")
        else:
            st.error(f"No se han podido descargar los datos: {msg}")
        return

    if cur_df.empty:
        st.warning("Search Console no devuelve datos para ese periodo.")
        return

    has_prev = prev_df is not None
    kpi_row(cur_label, prev_label, cur_df, prev_df)
    st.divider()
    cmp = core.compare(cur_df, prev_df, "bloque")
    block_section(cmp, has_prev, [cur_label, prev_label] if has_prev else [cur_label])
    st.divider()
    detail_section(cur_df, prev_df, has_prev)

    st.divider()
    export = cur_df.rename(columns={"page": "pagina", "query": "consulta", "clicks": "clics",
                                    "impressions": "impresiones", "position": "posicion"})
    st.download_button("Descargar datos del periodo (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"gsc_{core.property_domain(site)}_{start}_{end}.csv", mime="text/csv")
    with st.expander("Cómo se clasifican las búsquedas"):
        st.markdown(
            "- **Plataformas alumnos**: la consulta contiene alguna plataforma de la lista (Moodle, Clickedu, aula virtual…).\n"
            "- **Marca**: la consulta contiene un término de marca.\n"
            "- **Blog**: búsqueda genérica que llega a una entrada del blog (según el sitemap de WordPress).\n"
            "- **Captación**: búsqueda genérica que llega a la home, a fichas o a formularios.\n\n"
            "Las URLs con ancla (#) se agrupan en su página. Los datos de los últimos 2-3 días pueden variar "
            "hasta que Google los consolida."
        )


main()
