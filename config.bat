@echo off
REM =====================================
REM  Configurador Worker T3
REM =====================================

REM --- Mostrar configuración actual si existe ---
if exist .env (
    echo.
    echo Configuración actual:
    echo =====================================
    type .env
    echo =====================================
    echo.
    set /p CHANGE="¿Cambiar configuración? (s/n): "
    if /i "%CHANGE%"=="n" (
        echo Configuración mantenida
        pause
        exit /b 0
    )
)

REM --- Solicitar nueva configuración ---
echo.
echo --- NUEVA CONFIGURACION ---

set /p PC_ID="ID de esta PC [%COMPUTERNAME%]: "
if "%PC_ID%"=="" set PC_ID=%COMPUTERNAME%

echo.
echo Tipos de worker:
echo   1. deudas
echo   2. movimientos
set /p TYPE_NUM="Selecciona tipo (1-2): "
if "%TYPE_NUM%"=="1" (
    set WORKER_TYPE=deudas
) else if "%TYPE_NUM%"=="2" (
    set WORKER_TYPE=movimientos
) else (
    echo Tipo inválido, usando 'deudas'
    set WORKER_TYPE=deudas
)

set /p BACKEND_URL="URL del servidor [http://192.168.9.160:8000]: "
if "%BACKEND_URL%"=="" set BACKEND_URL=http://192.168.9.160:8000

set /p PROCESS_DELAY="Tiempo de procesamiento [5]: "
if "%PROCESS_DELAY%"=="" set PROCESS_DELAY=5

REM --- Crear .env ---
echo.
echo Guardando configuración...
echo PC_ID=%PC_ID% > .env
echo WORKER_TYPE=%WORKER_TYPE% >> .env
echo BACKEND_URL=%BACKEND_URL% >> .env
echo PROCESS_DELAY=%PROCESS_DELAY% >> .env
echo POLL_INTERVAL=2 >> .env
echo CONNECTION_TIMEOUT=10 >> .env
echo LOG_LEVEL=INFO >> .env

echo.
echo =====================================
echo CONFIGURACION GUARDADA:
echo =====================================
type .env
echo =====================================
echo.
echo ✓ Configuración creada exitosamente
echo Ahora ejecuta run_worker.bat
pause