```bat
@echo off
REM =====================================
REM  Configurador y Ejecutor Worker T3
REM =====================================

REM --- Verificar si Git está instalado ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no está instalado. Instálalo desde https://git-scm.com/
    pause
    exit /b 1
)

REM --- Verificar si Python está instalado ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no está instalado. Instálalo desde https://www.python.org/
    pause
    exit /b 1
)

REM --- Clonar o actualizar el repositorio ---
if exist Workers-T3 (
    echo Actualizando repositorio...
    cd Workers-T3
    git pull
    cd ..
) else (
    echo Clonando repositorio...
    git clone https://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@github.com/Word-Connection/Workers-T3.git
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudo clonar el repositorio. Verifica el token o la conexión.
        pause
        exit /b 1
    )
)

REM --- Cambiar al directorio del repositorio ---
cd Workers-T3

REM --- Crear entorno virtual si no existe ---
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
)

REM --- Activar entorno virtual ---
call venv\Scripts\activate.bat

REM --- Instalar dependencias ---
echo Instalando dependencias...
pip install requests python-dotenv
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

REM --- Mostrar configuración actual si existe ---
if exist .env (
    echo.
    echo Configuración actual:
    echo =====================================
    type .env
    echo =====================================
    echo.
    set /p CHANGE="¿Cambiar configuración? (s/n): "
    if /i "!CHANGE!"=="n" (
        echo Configuración mantenida
        goto :run_worker
    )
)

REM --- Solicitar nueva configuración ---
echo.
echo --- NUEVA CONFIGURACION ---
set "PC_ID=%COMPUTERNAME%"
set /p INPUT_PC_ID="ID de esta PC [%PC_ID%]: "
if not "!INPUT_PC_ID!"=="" set "PC_ID=%INPUT_PC_ID: =%"

echo.
echo Tipos de worker:
echo   1. deudas
echo   2. movimientos
set "WORKER_TYPE=deudas"
set /p TYPE_NUM="Selecciona tipo (1-2) [1]: "
if "!TYPE_NUM!"=="1" (
    set "WORKER_TYPE=deudas"
) else if "!TYPE_NUM!"=="2" (
    set "WORKER_TYPE=movimientos"
) else if not "!TYPE_NUM!"=="" (
    echo Tipo inválido, usando 'deudas'
    set "WORKER_TYPE=deudas"
)
set "WORKER_TYPE=%WORKER_TYPE: =%"

set "BACKEND_URL=http://192.168.9.160:8000"
set /p INPUT_BACKEND_URL="URL del servidor [%BACKEND_URL%]: "
if not "!INPUT_BACKEND_URL!"=="" set "BACKEND_URL=%INPUT_BACKEND_URL: =%"

set "PROCESS_DELAY=5"
set /p INPUT_PROCESS_DELAY="Tiempo de procesamiento [%PROCESS_DELAY%]: "
if not "!INPUT_PROCESS_DELAY!"=="" set "PROCESS_DELAY=%INPUT_PROCESS_DELAY: =%"

REM --- Verificar variables antes de escribir ---
echo.
echo Verificando configuración...
echo PC_ID=%PC_ID%
echo WORKER_TYPE=%WORKER_TYPE%
echo BACKEND_URL=%BACKEND_URL%
echo PROCESS_DELAY=%PROCESS_DELAY%

REM --- Crear .env dentro de Workers-T3 ---
echo.
echo Guardando configuración...
(
    echo PC_ID=%PC_ID%
    echo WORKER_TYPE=%WORKER_TYPE%
    echo BACKEND_URL=%BACKEND_URL%
    echo PROCESS_DELAY=%PROCESS_DELAY%
    echo POLL_INTERVAL=2
    echo CONNECTION_TIMEOUT=10
    echo LOG_LEVEL=INFO
) > .env

echo.
echo =====================================
echo CONFIGURACION GUARDADA:
echo =====================================
type .env
echo =====================================

:run_worker
REM --- Ejecutar worker en primer plano ---
echo.
echo Iniciando worker...
python worker.py
pause
