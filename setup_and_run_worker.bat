@echo off
setlocal enabledelayedexpansion
REM =====================================
REM  Configurador y Ejecutor Worker T3
REM =====================================

REM --- Verificar si Git está instalado ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no esta instalado. Instalalo desde https://git-scm.com/
    pause
    exit /b 1
)

REM --- Verificar si Python está instalado ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado. Instalalo desde https://www.python.org/
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
    if !ERRORLEVEL! neq 0 (
        echo ERROR: No se pudo clonar el repositorio. Verifica el token o la conexion.
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

REM --- Instalar dependencias desde requirements.txt ---
if not exist requirements.txt (
    echo ERROR: No se encontro requirements.txt en el directorio Workers-T3
    pause
    exit /b 1
)
echo Instalando dependencias desde requirements.txt...
pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo ERROR: No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

REM --- Mostrar configuración actual si existe ---
if exist .env (
    echo.
    echo Configuracion actual:
    echo =====================================
    type .env
    echo =====================================
    echo.
    set /p CHANGE="Cambiar configuracion? (s/n): "
    if /i "!CHANGE!"=="n" (
        echo Configuracion mantenida
        goto :run_worker
    )
)

REM --- Solicitar nueva configuración ---
echo.
echo --- NUEVA CONFIGURACION ---

REM PC_ID
set "DEFAULT_PC_ID=%COMPUTERNAME%"
set /p PC_ID="ID de esta PC [!DEFAULT_PC_ID!]: "
if "!PC_ID!"=="" set "PC_ID=!DEFAULT_PC_ID!"

echo.
echo Tipos de worker:
echo   1. deudas
echo   2. movimientos
set /p TYPE_NUM="Selecciona tipo (1-2) [1]: "
if "!TYPE_NUM!"=="2" (
    set "WORKER_TYPE=movimientos"
) else (
    set "WORKER_TYPE=deudas"
)

REM Backend URL
set "DEFAULT_BACKEND=http://192.168.9.160:8000"
set /p BACKEND_URL="URL del servidor [!DEFAULT_BACKEND!]: "
if "!BACKEND_URL!"=="" set "BACKEND_URL=!DEFAULT_BACKEND!"

REM API Key (contraseña)
set /p API_KEY="Clave API (lucas123): "
if "!API_KEY!"=="" (
    echo ERROR: La clave API es obligatoria.
    pause
    exit /b 1
)

REM Process Delay
set "DEFAULT_DELAY=30"
set /p PROCESS_DELAY="Tiempo de procesamiento [!DEFAULT_DELAY!]: "
if "!PROCESS_DELAY!"=="" set "PROCESS_DELAY=!DEFAULT_DELAY!"

REM --- Mostrar resumen antes de guardar ---
echo.
echo =====================================
echo RESUMEN DE CONFIGURACION:
echo =====================================
echo PC_ID=!PC_ID!
echo WORKER_TYPE=!WORKER_TYPE!
echo BACKEND_URL=!BACKEND_URL!
echo API_KEY=!API_KEY!
echo PROCESS_DELAY=!PROCESS_DELAY!
echo =====================================
echo.
set /p CONFIRM="Es correcta la configuracion? (s/n): "
if /i "!CONFIRM!"=="n" (
    echo Configuracion cancelada. Ejecuta el script nuevamente.
    pause
    exit /b 0
)

REM --- Crear archivo .env ---
echo.
echo Guardando configuracion...
echo PC_ID=!PC_ID!> .env
echo WORKER_TYPE=!WORKER_TYPE!>> .env
echo BACKEND_URL=!BACKEND_URL!>> .env
echo API_KEY=!API_KEY!>> .env
echo PROCESS_DELAY=!PROCESS_DELAY!>> .env
echo POLL_INTERVAL=5>> .env
echo CONNECTION_TIMEOUT=300>> .env
echo LOG_LEVEL=INFO>> .env
echo TIMEZONE=America/Argentina/Buenos_Aires>> .env
echo OPERATING_START=09:00>> .env
echo OPERATING_END=21:00>> .env

REM --- Verificar que se creó correctamente ---
if exist .env (
    echo.
    echo =====================================
    echo CONFIGURACION GUARDADA EXITOSAMENTE:
    echo =====================================
    type .env
    echo =====================================
) else (
    echo ERROR: No se pudo crear el archivo .env
    pause
    exit /b 1
)

:run_worker
REM --- Verificar que existe worker.py ---
if not exist worker.py (
    echo ERROR: No se encontro worker.py en el directorio Workers-T3
    echo Verifica que el repositorio se clono correctamente
    pause
    exit /b 1
)

REM --- Ejecutar worker ---
echo.
echo Iniciando worker en 3 segundos...
timeout /t 3 /nobreak >nul
echo =====================================
python worker.py

echo.
echo =====================================
echo Worker finalizado
echo =====================================
pause
