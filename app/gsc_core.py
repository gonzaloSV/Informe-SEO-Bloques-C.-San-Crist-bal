"""
gsc_core.py
Lógica común: descarga de Search Console, limpieza, clasificación en bloques
(Plataformas alumnos, Marca, Blog, Captación) y cálculo de periodos.
La usan la app (app.py) y se puede importar desde cualquier script.
"""

from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from datetime import date, timedelta
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
ROW_LIMIT = 25000
DEFAULT_PLATFORMS = "moodle,clickedu,aula virtual,campus virtual,alexia,educamos,itaca,intranet"
BLOQUES = ["Captación", "Marca", "Blog", "Plataformas alumnos"]


# ---------- Credenciales y servicio ----------

def credentials_from_info(info: dict):
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_info(dict(info), scopes=SCOPES)


def build_service(creds):
    from googleapiclient.discovery import build
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


# ---------- Propiedades ----------

def normalize_property(value: str) -> str:
    """Convierte lo que escribe el usuario en una propiedad válida de Search Console.
    'midominio.com'              -> 'sc-domain:midominio.com'
    'https://www.midominio.com'  -> 'https://www.midominio.com/'
    'sc-domain:midominio.com'    -> sin cambios
    """
    v = value.strip()
    if not v:
        return v
    if v.startswith("sc-domain:"):
        return "sc-domain:" + v.split(":", 1)[1].strip().strip("/").lower()
    if v.startswith(("http://", "https://")):
        return v if v.endswith("/") else v + "/"
    return "sc-domain:" + v.strip("/").lower().removeprefix("www.")


def property_domain(site: str) -> str:
    if site.startswith("sc-domain:"):
        return site.split(":", 1)[1]
    return urlparse(site).netloc.removeprefix("www.")


# ---------- Periodos ----------

def previous_month(today: date | None = None):
    today = today or date.today()
    first_this = today.replace(day=1)
    end = first_this - timedelta(days=1)
    return end.replace(day=1), end


def _is_full_month(start: date, end: date) -> bool:
    return start.day == 1 and end == start.replace(day=monthrange(start.year, start.month)[1])


def _minus_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - 1, day=28)


def comparison_period(start: date, end: date, mode: str):
    """mode: 'anterior' | 'interanual' | 'ninguno'"""
    if mode == "ninguno":
        return None
    if mode == "interanual":
        return _minus_one_year(start), _minus_one_year(end)
    if _is_full_month(start, end):  # mes completo -> mes completo anterior
        return previous_month(start)
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=days - 1), prev_end


# ---------- Descarga ----------

def fetch(service, site: str, start: date, end: date) -> pd.DataFrame:
    rows, start_row = [], 0
    while True:
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["page", "query"],
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
            "dataState": "all",  # incluye los últimos días aunque aún no estén consolidados
        }
        resp = service.searchanalytics().query(siteUrl=site, body=body).execute()
        batch = resp.get("rows", [])
        rows.extend(
            {
                "page": r["keys"][0],
                "query": r["keys"][1],
                "clicks": r.get("clicks", 0),
                "impressions": r.get("impressions", 0),
                "position": r.get("position", 0),
            }
            for r in batch
        )
        if len(batch) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT
    return pd.DataFrame(rows, columns=["page", "query", "clicks", "impressions", "position"])


# ---------- Limpieza ----------

def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Une anclas (#) en su URL y fusiona variantes de una misma consulta
    ('Curso SEO', 'curso  seo', 'cúrso seo'). La posición se pondera por impresiones."""
    cols = ["page", "query", "clicks", "impressions", "position"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df.copy()
    df["page"] = df["page"].astype(str).str.split("#").str[0].str.strip()
    # Misma consulta en varias anclas: clics sumados, impresiones y posición del mejor ancla
    df = (
        df.sort_values("position")
        .groupby(["page", "query"], as_index=False)
        .agg(clicks=("clicks", "sum"), impressions=("impressions", "max"), position=("position", "first"))
    )
    df["query"] = df["query"].astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    df["_key"] = df["query"].map(strip_accents)
    df["_posw"] = df["position"] * df["impressions"]
    label = (
        df.sort_values(["clicks", "impressions"], ascending=False)
        .drop_duplicates(["page", "_key"])[["page", "_key", "query"]]
    )
    out = (
        df.groupby(["page", "_key"], as_index=False)[["clicks", "impressions", "_posw"]].sum()
        .merge(label, on=["page", "_key"])
    )
    out["position"] = (out["_posw"] / out["impressions"].where(out["impressions"] > 0)).fillna(0).round(1)
    out = out.astype({"clicks": "int64", "impressions": "int64"})
    return out[cols]


# ---------- Sitemap ----------

def _sitemap_paths(domain: str, names) -> set:
    for host in (domain, "www." + domain):
        for name in names:
            try:
                req = Request(f"https://{host}/{name}", headers={"User-Agent": "Mozilla/5.0 (seo-report)"})
                with urlopen(req, timeout=15) as r:
                    xml = r.read().decode("utf-8", "ignore")
                paths = {urlparse(loc).path for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml)}
                paths = {p for p in paths if not p.endswith(".xml")}
                if paths:
                    return paths
            except Exception:
                continue
    return set()


def load_site_paths(site: str):
    """Entradas y páginas de WordPress (Yoast, Rank Math o el sitemap nativo)."""
    domain = property_domain(site)
    posts = _sitemap_paths(domain, ["post-sitemap.xml", "wp-sitemap-posts-post-1.xml"])
    pages = _sitemap_paths(domain, ["page-sitemap.xml", "wp-sitemap-posts-page-1.xml"])
    return posts, pages


# ---------- Clasificación ----------

def build_terms_regex(terms):
    terms = [strip_accents(t.strip().lower()) for t in terms if t and t.strip()]
    if not terms:
        return None
    # Cada término admite espacios, guiones o nada entre palabras
    patterns = [r"[\s\-_.]*".join(map(re.escape, t.split())) for t in terms]
    return re.compile(r"(?:" + "|".join(patterns) + r")")


def is_blog(page: str, posts: set, pages: set) -> bool:
    path = urlparse(page).path or "/"
    if path in posts or re.match(r"^/(blog|category|categoria|tag|etiqueta|author|noticias)/", path):
        return True
    # URL que ya no está entre las páginas del sitemap: entrada antigua o renombrada
    return bool(pages) and path not in pages and path != "/"


def classify(df: pd.DataFrame, brand_terms, platform_terms, site_paths) -> pd.DataFrame:
    """Prioridad: Plataformas alumnos > Marca > Blog > Captación."""
    df = df.copy()
    if df.empty:
        df["bloque"] = pd.Series(dtype=str)
        return df
    brand_re = build_terms_regex(brand_terms)
    platform_re = build_terms_regex(platform_terms)
    q = df["query"].map(strip_accents)
    posts, pages = site_paths

    df["bloque"] = "Captación"
    df.loc[df["page"].map(lambda u: is_blog(u, posts, pages)), "bloque"] = "Blog"
    if brand_re is not None:
        df.loc[q.str.contains(brand_re), "bloque"] = "Marca"
    if platform_re is not None:
        df.loc[q.str.contains(platform_re), "bloque"] = "Plataformas alumnos"
    return df


# ---------- Agregados ----------

def aggregate(df: pd.DataFrame, by) -> pd.DataFrame:
    """Suma clics e impresiones y calcula CTR y posición media ponderada."""
    by = [by] if isinstance(by, str) else list(by)
    if df.empty:
        return pd.DataFrame(columns=by + ["clicks", "impressions", "ctr", "position"])
    tmp = df.assign(_posw=df["position"] * df["impressions"])
    g = tmp.groupby(by, as_index=False)[["clicks", "impressions", "_posw"]].sum()
    g["ctr"] = (g["clicks"] / g["impressions"].where(g["impressions"] > 0)).fillna(0)
    g["position"] = (g["_posw"] / g["impressions"].where(g["impressions"] > 0)).fillna(0)
    return g.drop(columns="_posw")


def totals(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    clicks, impr = int(df["clicks"].sum()), int(df["impressions"].sum())
    pos = float((df["position"] * df["impressions"]).sum() / impr) if impr else 0.0
    return {"clicks": clicks, "impressions": impr, "ctr": clicks / impr if impr else 0.0, "position": pos}


def compare(cur: pd.DataFrame, prev: pd.DataFrame | None, key) -> pd.DataFrame:
    """Une periodo actual y anterior por la clave y añade variaciones."""
    key = [key] if isinstance(key, str) else list(key)
    a = aggregate(cur, key)
    if prev is None:
        return a
    b = aggregate(prev, key).rename(columns={
        "clicks": "clicks_prev", "impressions": "impressions_prev", "ctr": "ctr_prev", "position": "position_prev"})
    m = a.merge(b, on=key, how="outer")
    for c in ["clicks", "impressions", "clicks_prev", "impressions_prev"]:
        m[c] = m[c].fillna(0).astype("int64")
    for c in ["ctr", "ctr_prev"]:
        m[c] = m[c].fillna(0.0)
    m["d_clicks"] = m["clicks"] - m["clicks_prev"]
    m["d_impressions"] = m["impressions"] - m["impressions_prev"]
    m["d_position"] = m["position"] - m["position_prev"]  # negativo = mejora
    return m


def run_analysis(service, site, start, end, brand_terms, platform_terms, site_paths=None):
    """Descarga, limpia y clasifica un periodo."""
    site_paths = site_paths if site_paths is not None else load_site_paths(site)
    raw = fetch(service, site, start, end)
    return classify(clean(raw), brand_terms, platform_terms, site_paths)
