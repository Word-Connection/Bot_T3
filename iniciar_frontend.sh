#!/bin/bash
# Script para iniciar el frontend con el entorno virtual correcto

cd "$(dirname "$0")"

# Activar entorno virtual
if [ -f "venv/bin/activate" ]; then
    echo "Activando entorno virtual..."
    source venv/bin/activate
else
    echo "Error: No se encuentra el entorno virtual en venv/bin/activate"
    exit 1
fi

# Verificar que Flask esté instalado
python -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Error: Flask no está instalado en el entorno virtual"
    exit 1
fi

echo "Iniciando frontend..."
echo "URL: http://localhost:5555"
python frontend_control.py