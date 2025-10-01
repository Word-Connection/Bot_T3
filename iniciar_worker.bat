@echo off
chcp 65001 >nul
title Configurador de Worker T3
color 0A

echo ================================================
echo    WORKER T3 - CONFIGURADOR INTERACTIVO
echo ================================================
echo.

REM ===== CONFIGURACIÓN DE RUTAS Y TOKEN =====
REM IMPORTANTE: Reemplaza con tu nuevo token regenerado
set "GIT_TOKEN=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"
set "GIT_REPO_URL=https://%GIT_TOKEN%@github.com/Word-Connection/Workers-T3.git"
set "REPO_DIR=Workers-T3"

REM ===== CLONAR O ACTUALIZAR REPOSITORIO =====
echo [1/6] Verificando repositorio...
echo.

if exist "%REPO_DIR%" (
    echo Repositorio ya existe, actualizando...
    cd "%REPO_DIR%"
    git pull 2>nul
    if %errorlevel% neq 0 (
        echo [ADVERTENCIA] No se pudo hacer pull. Continuando...
    ) else (
        echo [OK] Código actualizado correctamente
    )
) else (
    echo Clonando repositorio...
    git clone %GIT_REPO_URL% 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo clonar el repositorio
        echo Verifica tu token y conexión a internet
        pause
        exit /b 1
    )
    cd "%REPO_DIR%"
    echo [OK] Repositorio clonado correctamente
)
echo.

REM ===== VERIFICAR ARCHIVOS NECESARIOS =====
if not exist "worker.py" (
    echo [ERROR] No se encontró worker.py en el repositorio
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo [ADVERTENCIA] No se encontró requirements.txt
)

echo [INFO] Directorio actual: %CD%
echo.

REM ===== CREAR ENTORNO VIRTUAL =====
echo [2/6] Configurando entorno virtual...
echo.

if exist "venv" (
    echo Entorno virtual ya existe
) else (
    echo Creando entorno virtual...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual
        echo Verifica que Python esté instalado: python --version
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado
)
echo.

REM ===== ACTIVAR ENTORNO VIRTUAL =====
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo activar el entorno virtual
    pause
    exit /b 1
)

REM ===== INSTALAR DEPENDENCIAS =====
echo [3/6] Instalando dependencias...
echo.

if exist "requirements.txt" (
    echo Actualizando pip...
    python -m pip install --upgrade pip --quiet
    echo Instalando paquetes...
    pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [ADVERTENCIA] Hubo problemas instalando algunas dependencias
    ) else (
        echo [OK] Dependencias instaladas correctamente
    )
) else (
    echo [ADVERTENCIA] No se encontró requirements.txt, saltando instalación
)
echo.

REM ===== CONFIGURACIÓN PC_ID =====
echo [4/6] ID de esta PC
set /p "PC_ID_INPUT=Ingresa PC_ID [predeterminado: pc1]: "
if "%PC_ID_INPUT%"=="" (
    set "PC_ID=pc1"
    echo Usando predeterminado: pc1
) else (
    set "PC_ID=%PC_ID_INPUT%"
)
echo.

REM ===== CONFIGURACIÓN TIPO =====
echo [5/6] Tipo de Worker
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
echo [6/6] Configuración del servidor
set /p "BACKEND_INPUT=IP del backend [predeterminado: http://192.168.9.160:8000]: "
if "%BACKEND_INPUT%"=="" (
    set "BACKEND_URL=http://192.168.9.160:8000"
    echo Usando predeterminado: http://192.168.9.160:8000
) else (
    REM Agregar http:// si no lo tiene
    echo %BACKEND_INPUT% | find "http" >nul
    if %errorlevel% neq 0 (
        set "BACKEND_URL=http://%BACKEND_INPUT%"
    ) else (
        set "BACKEND_URL=%BACKEND_INPUT%"
    )
)
echo.

REM ===== CONFIGURACIÓN API KEY =====
set /p "API_KEY_INPUT=API Key [predeterminado: default_key_123]: "
if "%API_KEY_INPUT%"=="" (
    set "API_KEY=default_key_123"
    echo Usando predeterminado: default_key_123
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

echo [OK] Archivo .env creado:
echo.
type .env
echo.

REM ===== CREAR DIRECTORIO DE LOGS =====
if not exist "logs" (
    mkdir logs
    echo [OK] Directorio logs/ creado
)

REM ===== VERIFICAR CARPETA SCRIPTS =====
if not exist "scripts\%WORKER_TYPE%.py" (
    echo [ADVERTENCIA] No se encontró scripts\%WORKER_TYPE%.py
    echo El worker puede fallar si este script no existe
)

REM ===== RESUMEN DE CONFIGURACIÓN =====
echo ================================================
echo RESUMEN DE CONFIGURACIÓN
echo ================================================
echo PC_ID:       %PC_ID%
echo TIPO:        %WORKER_TYPE%
echo BACKEND:     %BACKEND_URL%
echo API_KEY:     %API_KEY%
echo DIRECTORIO:  %CD%
echo SCRIPT:      scripts\%WORKER_TYPE%.py
echo ================================================
echo.

REM ===== CONFIRMAR E INICIAR =====
set /p "CONFIRMAR=¿Iniciar worker? (S/N) [S]: "
if /i "%CONFIRMAR%"=="N" (
    echo Operación cancelada.
    echo Para reiniciar ejecuta: venv\Scripts\activate.bat ^&^& python worker.py
    pause
    exit /b
)

echo.
echo ================================================
echo    INICIANDO WORKER T3
echo ================================================
echo.
echo Logs en tiempo real:
echo   - Consola: aquí mismo
echo   - Archivo: logs\worker_%PC_ID%.log
echo.
echo Presiona CTRL+C para detener el worker
echo ================================================
echo.

REM Iniciar worker (el venv ya está activado)
python worker.py

pause