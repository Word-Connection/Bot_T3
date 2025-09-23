@echo off
REM =====================================
REM  Script de instalación y ejecución Worker T3
REM =====================================

REM --- Habilitar ejecución de scripts en PowerShell (si no está habilitado) ---
powershell -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"

REM --- Configuración ---
set SERVER_URL=http://192.168.9.142:8000
set PC_ID=%COMPUTERNAME%
set WORKER_TYPE=deudas
set PROCESS_DELAY=5

echo =====================================
echo Iniciando setup para Worker %PC_ID% tipo %WORKER_TYPE%
echo =====================================

REM --- Crear entorno virtual si no existe ---
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
)

REM --- Activar entorno virtual ---
call venv\Scripts\activate

REM --- Actualizar pip ---
python -m pip install --upgrade pip

REM --- Instalar dependencias ---
if exist requirements.txt (
    echo Instalando dependencias desde requirements.txt...
    pip install -r requirements.txt
) else (
    echo No se encontro requirements.txt, instalando dependencias basicas...
    pip install requests
)

REM --- Arrancar worker principal ---
start cmd /k "python worker.py --pc_id %PC_ID% --tipo %WORKER_TYPE% --backend %SERVER_URL% --delay %PROCESS_DELAY%"

echo =====================================
echo Worker %PC_ID% inicializado
echo =====================================
pause
