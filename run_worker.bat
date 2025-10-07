@echo off
setlocal enabledelayedexpansion

echo =====================================
echo   Ejecutor Worker T3
echo =====================================

REM --- Verificar que existe el directorio del worker ---
set "REPO_NAME=Workers-T3"
if not exist "%REPO_NAME%" (
    echo ERROR: No se encuentra el directorio %REPO_NAME%
    echo Ejecuta primero setup_worker.bat para configurar el worker
    pause
    exit /b 1
)

REM --- Entrar al directorio del worker ---
cd "%REPO_NAME%"

REM --- Verificar archivo .env ---
if not exist ".env" (
    echo ERROR: No se encuentra archivo .env
    echo Ejecuta primero setup_worker.bat para configurar el worker
    pause
    exit /b 1
)

REM --- Leer configuración del .env ---
echo Leyendo configuracion...
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if "%%a"=="PC_ID" set "PC_ID=%%b"
    if "%%a"=="WORKER_TYPE" set "WORKER_TYPE=%%b"
    if "%%a"=="BACKEND_URL" set "BACKEND_URL=%%b"
    if "%%a"=="API_KEY" set "API_KEY=%%b"
)

REM --- Verificar variables requeridas ---
if "!PC_ID!"=="" (
    echo ERROR: PC_ID no encontrado en .env
    pause
    exit /b 1
)
if "!WORKER_TYPE!"=="" (
    echo ERROR: WORKER_TYPE no encontrado en .env
    pause
    exit /b 1
)
if "!BACKEND_URL!"=="" (
    echo ERROR: BACKEND_URL no encontrado en .env
    pause
    exit /b 1
)
if "!API_KEY!"=="" (
    echo ERROR: API_KEY no encontrado en .env
    pause
    exit /b 1
)

REM --- Verificar entorno virtual ---
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Entorno virtual no encontrado
    echo Ejecuta setup_worker.bat para configurar el entorno
    pause
    exit /b 1
)

REM --- Activar entorno virtual ---
echo Activando entorno virtual...
call venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo activar el entorno virtual
    pause
    exit /b 1
)

REM --- Verificar worker.py ---
if not exist "worker.py" (
    echo ERROR: worker.py no encontrado
    pause
    exit /b 1
)

REM --- Mostrar configuración ---
echo.
echo =====================================
echo   CONFIGURACION ACTUAL
echo =====================================
echo PC_ID: !PC_ID!
echo Tipo: !WORKER_TYPE!
echo Backend: !BACKEND_URL!
echo API Key: !API_KEY!
echo =====================================
echo.
echo Otros parametros se cargan desde .env automaticamente
echo.

REM --- Crear directorio de logs si no existe ---
if not exist "logs" mkdir logs

REM --- Ejecutar worker ---
echo Iniciando Worker T3...
echo (Presiona Ctrl+C para detener)
echo.

REM --- Solo pasar los argumentos esenciales, el resto desde .env ---
python worker.py --tipo !WORKER_TYPE! --api_key !API_KEY! --pc_id !PC_ID! --backend !BACKEND_URL!

echo.
echo =====================================
echo Worker finalizado
echo =====================================
echo.
echo Para reiniciar el worker, ejecuta este archivo nuevamente
echo Para cambiar configuracion, ejecuta setup_worker.bat
echo.
pause