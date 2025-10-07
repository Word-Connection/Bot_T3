@echo off
setlocal enabledelayedexpansion

echo =====================================
echo   Configurador Worker T3
echo =====================================

REM --- Configuracion ---
set "REPO_NAME=Workers-T3"
set "GITHUB_TOKEN=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"
set "REPO_URL=https://%GITHUB_TOKEN%@github.com/Word-Connection/Workers-T3.git"

REM --- Verificar Git y Python ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no instalado. Descarga desde: https://git-scm.com/
    pause
    exit /b 1
)

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    where py >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Python no instalado. Descarga desde: https://www.python.org/
        pause
        exit /b 1
    ) else (
        set "PYTHON_CMD=py"
    )
) else (
    set "PYTHON_CMD=python"
)

echo Usando comando Python: %PYTHON_CMD%

REM --- Clonar o actualizar repositorio ---
if exist "%REPO_NAME%" (
    echo Actualizando repositorio...
    cd "%REPO_NAME%"
    git pull
    if %ERRORLEVEL% neq 0 (
        echo ADVERTENCIA: No se pudo actualizar, continuando...
    )
    cd ..
) else (
    echo Clonando repositorio...
    git clone "%REPO_URL%"
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudo clonar el repositorio
        pause
        exit /b 1
    )
)

REM --- Entrar al directorio del worker ---
cd "%REPO_NAME%"

REM --- Verificar configuracion existente ---
if exist ".env" (
    echo.
    echo Configuracion actual:
    echo =====================================
    type .env
    echo =====================================
    echo.
    set /p CHANGE="Quieres cambiar la configuracion? (s/N): "
    if /i not "!CHANGE!"=="s" goto :setup_env
)

REM --- Configuracion nueva ---
echo.
echo --- NUEVA CONFIGURACION ---

set /p PC_ID="ID de esta PC [%COMPUTERNAME%]: "
if "!PC_ID!"=="" set "PC_ID=%COMPUTERNAME%"

echo.
echo Tipos de worker:
echo   1. deudas
echo   2. movimientos
set /p TYPE_NUM="Tipo (1/2) [1]: "
if "!TYPE_NUM!"=="2" (
    set "WORKER_TYPE=movimientos"
) else (
    set "WORKER_TYPE=deudas"
)

set /p BACKEND_URL="URL del backend [http://192.168.9.160:8000]: "
if "!BACKEND_URL!"=="" set "BACKEND_URL=http://192.168.9.160:8000"

set /p API_KEY="Clave API [lucas123]: "
if "!API_KEY!"=="" set "API_KEY=lucas123"

REM --- Crear archivo .env ---
echo PC_ID=!PC_ID!> .env
echo WORKER_TYPE=!WORKER_TYPE!>> .env
echo BACKEND_URL=!BACKEND_URL!>> .env
echo API_KEY=!API_KEY!>> .env
echo POLL_INTERVAL=5>> .env
echo CONNECTION_TIMEOUT=300>> .env
echo LOG_LEVEL=INFO>> .env

echo.
echo Configuracion guardada en .env

:setup_env
REM --- Limpiar entorno virtual existente ---
if exist "venv" (
    echo Limpiando entorno virtual anterior...
    rmdir /s /q venv
)

REM --- Crear entorno virtual ---
echo Creando entorno virtual...
%PYTHON_CMD% -m venv venv
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo crear el entorno virtual
    pause
    exit /b 1
)

REM --- Activar entorno virtual ---
echo Activando entorno virtual...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo ERROR: No se encuentra activate.bat
    pause
    exit /b 1
)

REM --- Verificar activación ---
python -c "import sys; print('Entorno virtual activo:', sys.prefix)"

REM --- Actualizar pip ---
echo Actualizando pip...
python -m pip install --upgrade pip --quiet

REM --- Instalar dependencias básicas ---
echo Instalando dependencias básicas...
python -m pip install --quiet requests python-dotenv tenacity pytz websocket-client pillow

REM --- Instalar desde requirements.txt si existe ---
if exist "requirements.txt" (
    echo Instalando desde requirements.txt...
    python -m pip install -r requirements.txt --quiet
) else (
    echo No se encontro requirements.txt, usando dependencias básicas
)

REM --- Verificar dependencias críticas ---
echo Verificando dependencias...
python -c "import requests, dotenv, tenacity, pytz; print('✓ Todas las dependencias instaladas correctamente')"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Falló la verificación de dependencias
    pause
    exit /b 1
)

REM --- Verificar worker.py ---
if not exist "worker.py" (
    echo ERROR: No se encontro worker.py en el directorio Workers-T3
    pause
    exit /b 1
)

echo.
echo =====================================
echo   CONFIGURACION COMPLETADA
echo =====================================
echo.
echo ✓ Repositorio actualizado
echo ✓ Configuracion guardada en .env
echo ✓ Entorno virtual creado
echo ✓ Dependencias instaladas
echo ✓ Worker verificado
echo.
echo Para ejecutar el worker, usa: run_worker.bat
echo.
pause