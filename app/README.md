# Informe SEO San Cristóbal (app web)

App de Streamlit que lee Search Console y clasifica las búsquedas en cuatro bloques: **Captación, Marca, Blog y Plataformas alumnos**.

- Selector de web: fpsancristobal.es, sancristobalsl.com o cualquier otra (dominio o URL).
- Fechas libres. Por defecto, el mes anterior completo.
- Comparación con el periodo anterior, con el mismo periodo del año pasado o sin comparar.
- KPIs con variación, gráficos por bloque, páginas y consultas de cada bloque, oportunidades (posiciones 4-20) y descarga en CSV.
- Acceso protegido con contraseña.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `app.py` | La interfaz |
| `gsc_core.py` | Descarga, limpieza y clasificación |
| `requirements.txt` | Dependencias |
| `make_secrets.py` | Genera los secretos a partir de `credentials.json` |
| `.streamlit/config.toml` | Colores de la app |
| `.streamlit/secrets.example.toml` | Plantilla de secretos |

## 1. Dar acceso a la cuenta de servicio (una vez por web)

En Search Console, para **cada** propiedad (fpsancristobal.es y sancristobalsl.com):
*Ajustes → Usuarios y permisos → Añadir usuario*, con el `client_email` de `credentials.json` y permiso **Restringido**.

## 2. Probarla en el Mac

Haz doble clic en **Abrir app.command**. Se abre una ventana de Terminal, instala lo necesario (la primera vez tarda un par de minutos) y abre la app en el navegador, en `http://localhost:8501`.

- Si macOS avisa de que no puede abrirlo porque es de un desarrollador no identificado: clic derecho sobre el archivo → **Abrir** → **Abrir**.
- Para pararla, cierra la ventana de Terminal.
- En local lee el `credentials.json` de la carpeta superior y no pide contraseña.

Funciona con el Python 3.9 que trae macOS.

## 3. Publicarla con URL propia (Streamlit Community Cloud, gratis)

1. Crea un repositorio **privado** en GitHub y sube el contenido de esta carpeta `app/`.
   El `.gitignore` ya impide subir `credentials.json` y `secrets.toml`.
2. Genera los secretos en el Mac:
   ```bash
   python3 make_secrets.py "la-contraseña-que-quieras"
   ```
   Se crea `.streamlit/secrets.toml`.
3. Entra en <https://share.streamlit.io> con tu cuenta de GitHub → **Create app** → elige el repositorio, rama `main` y archivo `app.py`.
4. En **Advanced settings → Secrets** pega el contenido de `.streamlit/secrets.toml`.
5. Elige la URL (por ejemplo `seo-sancristobal.streamlit.app`) y pulsa **Deploy**.

La app queda en esa URL y pide la contraseña al entrar. Si cambias el código en GitHub, se actualiza sola.

## Notas

- La propiedad por defecto es `sc-domain:` (propiedad de dominio). Si alguna web está dada de alta como prefijo de URL, elige "Otra web" y escribe la URL completa con `https://`.
- Los datos se guardan en caché una hora para no repetir llamadas a la API.
- Los últimos 2-3 días pueden variar hasta que Google los consolida.
- El bloque Blog se detecta con el sitemap de WordPress (Yoast, Rank Math o el nativo). En una web que no sea WordPress, solo cuentan como blog las URLs bajo `/blog/`, `/category/`, `/tag/` o `/noticias/`.
