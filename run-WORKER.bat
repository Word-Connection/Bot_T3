@echo off
setlocal enabledelayedexpansion
REM =====================================
REM  Ejecutar Worker T3 con configuracion interactiva
REM =====================================

REM --- Directorio del repo ---
set REPO_DIR=Workers-T3

REM --- Verificar Git y Python ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no esta instalado
    pause
    exit /b 1
)
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado
    pause
    exit /b 1
)

REM --- Clonar o actualizar repositorio ---
if exist %REPO_DIR% (
    echo Actualizando repositorio...
    cd %REPO_DIR%
    git pull || (
        echo ERROR: No se pudo actualizar el repositorio
        pause
        exit /b 1
    )
) else (
    echo Clonando repositorio...
    git clone https://github.com/Word-Connection/Workers-T3.git %REPO_DIR% || (
        echo ERROR: No se pudo clonar el repositorio
        pause
        exit /b 1
    )
    cd %REPO_DIR%
)

REM --- Cambiar a directorio del repo ---
cd %REPO_DIR%

REM --- Crear y activar entorno virtual ---
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv || (
        echo ERROR: No se pudo crear el entorno virtual
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat || (
    echo ERROR: No se pudo activar el entorno virtual
    pause
    exit /b 1
)

REM --- Instalar dependencias ---
pip install -r requirements.txt || (
    echo ERROR: Fallo instalando dependencias
    pause
    exit /b 1
)

REM --- Configuracion interactiva ---
set "DEFAULT_PC_ID=%COMPUTERNAME%"
set "DEFAULT_TIPO=deudas"
set "DEFAULT_BACKEND=http://192.168.9.160:8000"

echo.
set /p PC_ID="ID del PC [%DEFAULT_PC_ID%]: "
if "!PC_ID!"=="" set "PC_ID=!DEFAULT_PC_ID!"

echo.
echo Tipos de worker:
echo   1. deudas
echo   2. movimientos
set /p TYPE_NUM="Selecciona tipo (1-2) [%DEFAULT_TIPO%]: "
if "!TYPE_NUM!"=="2" (
    set "TIPO=movimientos"
) else if "!TYPE_NUM!"=="1" (
    set "TIPO=deudas"
) else (
    set "TIPO=!DEFAULT_TIPO!"
)

echo.
set /p BACKEND_URL="IP/URL del servidor [%DEFAULT_BACKEND%]: "
if "!BACKEND_URL!"=="" set "BACKEND_URL=!DEFAULT_BACKEND!"

REM --- Ejecutar Worker ---
echo.
echo Iniciando Worker T3...
echo PC_ID=!PC_ID! | Tipo=!TIPO! | Backend=!BACKEND_URL!
echo =====================================
python worker.py --pc_id !PC_ID! --tipo !TIPO! --backend !BACKEND_URL!

echo =====================================
echo Worker finalizado
pause
