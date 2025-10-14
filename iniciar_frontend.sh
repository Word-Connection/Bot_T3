#!/bin/bash

echo "====================================="
echo "   Iniciador Frontend Control Bot T3"
echo "====================================="

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no está instalado"
    read -p "Presiona Enter para continuar..."
    exit 1
fi

# Verificar que existe el proyecto configurado
if [ ! -d "Workers-T3" ]; then
    echo "ERROR: No se encuentra Workers-T3"
    echo "Ejecuta primero el setup para configurar el proyecto"
    read -p "Presiona Enter para continuar..."
    exit 1
fi

# Activar entorno virtual si existe
if [ -f ".venv/bin/activate" ]; then
    echo "Activando entorno virtual..."
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    echo "Activando entorno virtual..."
    source venv/bin/activate
else
    echo "ADVERTENCIA: No se encuentra entorno virtual"
    echo "Se intentará usar Python del sistema"
fi

# Instalar Flask si no está
echo "Verificando dependencias..."
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Instalando Flask..."
    pip install flask
fi

# Iniciar frontend
echo ""
echo "====================================="
echo "   Iniciando Frontend de Control"
echo "====================================="
echo ""
echo "🚀 El navegador se abrirá automáticamente en:"
echo "📱 http://localhost:5555"
echo ""
echo "⚠️  IMPORTANTE:"
echo "   - NO cierres esta terminal"
echo "   - Usa el navegador para controlar el bot"
echo "   - Presiona Ctrl+C aquí para cerrar todo"
echo ""
echo "====================================="

python3 frontend_control.py

echo ""
echo "Frontend cerrado"
read -p "Presiona Enter para continuar..."