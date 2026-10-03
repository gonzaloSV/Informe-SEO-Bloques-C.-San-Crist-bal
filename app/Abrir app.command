#!/bin/bash
# Doble clic para abrir la app en el navegador (http://localhost:8501).
# La primera vez tarda un par de minutos porque instala lo necesario.
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "No encuentro Python 3.9 o superior. Instálalo desde python.org y vuelve a abrir este archivo."
  open "https://www.python.org/downloads/macos/"
  read -r -p "Pulsa Intro para cerrar..."; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno (solo la primera vez)..."
  "$PY" -m venv .venv || { read -r -p "No se pudo crear el entorno. Pulsa Intro..."; exit 1; }
fi

.venv/bin/python -m pip install -q --upgrade pip
if ! .venv/bin/python -m pip install -q -r requirements.txt; then
  echo "Ha fallado la instalación de dependencias. Copia el mensaje de arriba y pásaselo a Claude."
  read -r -p "Pulsa Intro para cerrar..."; exit 1
fi

echo ""
echo "Abriendo la app en http://localhost:8501 ... (cierra esta ventana para pararla)"
.venv/bin/python -m streamlit run app.py
