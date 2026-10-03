"""Genera .streamlit/secrets.toml a partir de credentials.json.
Uso: python3 make_secrets.py "tu-contraseña"
"""
import json
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
for candidate in (base / "credentials.json", base.parent / "credentials.json"):
    if candidate.exists():
        cred = json.loads(candidate.read_text(encoding="utf-8"))
        break
else:
    sys.exit("No encuentro credentials.json ni en esta carpeta ni en la superior.")

pwd = sys.argv[1] if len(sys.argv) > 1 else "cambia-esta-contraseña"
lines = [f"APP_PASSWORD = {json.dumps(pwd)}", "", "[gcp_service_account]"]
lines += [f"{k} = {json.dumps(v)}" for k, v in cred.items()]
out = base / ".streamlit" / "secrets.toml"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Creado {out}")
print("Copia su contenido en Settings > Secrets de tu app en Streamlit Community Cloud.")
