@echo off
chcp 65001 >nul
title Configurador de Worker T3
color 0A

echo ================================================
echo    WORKER T3 - CONFIGURADOR INTERACTIVO
echo ================================================
echo.

REM ===== GIT PULL CON TOKEN =====
echo [1/5] Actualizando código desde GitHub...
echo.

REM IMPORTANTE: Reemplaza NUEVO_TOKEN con tu token regenerado
set "GIT_TOKEN=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"
set "GIT_REPO=https://%GIT_TOKEN%@github.com/tu-usuario/tu-repositorio.git"

git pull %GIT_REPO% 2>nul
if %errorlevel% neq 0 (
    echo [ADVERTENCIA] No se pudo hacer pull. Continuando...
) else (
    echo [OK] Código actualizado correctamente
)
echo.

REM ===== CONFIGURACIÓN PC_ID =====
echo [2/5] ID de esta PC
set /p "PC_ID_INPUT=Ingresa PC_ID [predeterminado: pc1]: "
if "%PC_ID_INPUT%"=="" (
    set "PC_ID=pc1"
    echo Usando predeterminado: pc1
) else (
    set "PC_ID=%PC_ID_INPUT%"
)
echo.

REM ===== CONFIGURACIÓN TIPO =====
echo [3/5] Tipo de Worker
echo     1 = deudas
echo     2 = movimientos
set /p "TIPO_INPUT=Selecciona tipo [predeterminado: 1-deudas]: "
if "%TIPO_INPUT%"=="" (
    set "WORKER_TYPE=deudas"
    echo Usando predeterminado: deudas
) else if "%TIPO_INPUT%"=="1" (
    set "WORKER_TYPE=deudas"
) else if "%TIPO_INPUT%"=="2" (
    set "WORKER_TYPE=movimientos"
) else (
    set "WORKER_TYPE=deudas"
    echo Opción inválida, usando: deudas
)
echo.

REM ===== CONFIGURACIÓN BACKEND =====
echo [4/5] IP del servidor backend
set /p "BACKEND_INPUT=Ingresa IP [predeterminado: http://192.168.9.160:8000]: "
if "%BACKEND_INPUT%"=="" (
    set "BACKEND_URL=http://192.168.9.160:8000"
    echo Usando predeterminado: http://192.168.9.160:8000
) else (
    set "BACKEND_URL=%BACKEND_INPUT%"
)
echo.

REM ===== CONFIGURACIÓN API KEY =====
echo [5/5] API Key
set /p "API_KEY_INPUT=Ingresa API Key [predeterminado: lucas123]: "
if "%API_KEY_INPUT%"=="" (
    set "API_KEY=lucas123"
    echo Usando predeterminado: lucas123
) else (
    set "API_KEY=%API_KEY_INPUT%"
)
echo.

REM ===== GENERAR ARCHIVO .ENV =====
echo ================================================
echo Generando archivo .env...
echo ================================================
(
echo PC_ID=%PC_ID%
echo WORKER_TYPE=%WORKER_TYPE%
echo BACKEND_URL=%BACKEND_URL%
echo API_KEY=%API_KEY%
echo POLL_INTERVAL=5
echo PROCESS_DELAY=30
echo LOG_LEVEL=INFO
echo TIMEZONE=America/Argentina/Buenos_Aires
echo OPERATING_START=09:00
echo OPERATING_END=21:00
) > .env

echo [OK] Archivo .env creado con la siguiente configuración:
echo.
type .env
echo.

REM ===== CONFIRMAR E INICIAR =====
echo ================================================
set /p "CONFIRMAR=¿Iniciar worker con esta configuración? (S/N) [S]: "
if /i "%CONFIRMAR%"=="N" (
    echo Operación cancelada.
    pause
    exit /b
)

echo.
echo ================================================
echo    INICIANDO WORKER T3
echo ================================================
echo PC_ID: %PC_ID%
echo TIPO: %WORKER_TYPE%
echo BACKEND: %BACKEND_URL%
echo ================================================
echo.
echo Presiona CTRL+C para detener el worker
echo.

REM Verificar si existe el entorno virtual
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activando entorno virtual...
    call venv\Scripts\activate.bat
)

REM Instalar dependencias si es necesario
pip install -q -r requirements.txt 2>nul

REM Iniciar worker
python worker.py

pause