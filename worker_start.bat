@echo off
REM -----------------------------------
REM Script para inicializar el worker T3
REM -----------------------------------

REM CONFIGURACIÓN
SET PC_ID=pc1   
SET TIPO=deudas
SET BACKEND=http://192.168.9.65:8000
SET DELAY=10

REM Ruta donde está el worker (ajustar si es otra)
SET WORKER_DIR=%~dp0

REM -----------------------------------
REM 1️⃣ Ir al directorio del worker
cd /d "%WORKER_DIR%"

REM 2️⃣ Crear entorno virtual si no existe
if not exist venv (
    echo [INFO] Creando entorno virtual...
    python -m venv venv
)

REM 3️⃣ Activar entorno virtual
call venv\Scripts\activate

REM 4️⃣ Instalar dependencias
echo [INFO] Instalando dependencias...
pip install --upgrade pip
pip install -r requirements.txt

REM 5️⃣ Ejecutar el cliente
echo [INFO] Iniciando el worker...
python pc_client.py --pc_id %PC_ID% --tipo %TIPO% --backend %BACKEND% --delay %DELAY%

pause
