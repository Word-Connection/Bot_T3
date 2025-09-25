@echo off
REM =====================================
REM  Configurador Worker T3 con Git
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
set CREATE_ENV=1
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
        set CREATE_ENV=0
    )
)

REM --- Solicitar nueva configuración si se requiere o si no existe .env ---
if "%CREATE_ENV%"=="1" (
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

    REM --- Crear .env dentro de Workers-T3 ---
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
)

echo.
echo ✓ Configuración creada/actualizada exitosamente
echo Ahora ejecuta run_worker.bat
pause