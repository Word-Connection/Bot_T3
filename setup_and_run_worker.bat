@echo off
setlocal enabledelayedexpansion
REM =====================================
REM  Ejecutar Worker T3 automáticamente
REM =====================================

REM --- Directorio del repo ---
set REPO_DIR=Workers-T3

REM --- Verificar que Git está instalado ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no esta instalado. Instalalo desde https://git-scm.com/
    pause
    exit /b 1
)

REM --- Verificar que Python está instalado ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado. Instalalo desde https://www.python.org/
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
    git clone https://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@github.com/Word-Connection/Workers-T3.git %REPO_DIR% || (
        echo ERROR: No se pudo clonar el repositorio
        pause
        exit /b 1
    )
    cd %REPO_DIR%
)

REM --- Cambiar a directorio del repo ---
cd %REPO_DIR%

REM --- Crear entorno virtual si no existe ---
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv || (
        echo ERROR: No se pudo crear el entorno virtual
        pause
        exit /b 1
    )
)

REM --- Activar entorno virtual ---
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

REM --- Ejecutar Worker ---
REM --- Cambia los valores de PC_ID y TIPO según tu configuración ---
set "PC_ID=%COMPUTERNAME%"
set "TIPO=deudas"

echo Iniciando Worker T3: pc_id=%PC_ID% tipo=%TIPO%
python worker.py --pc_id %PC_ID% --tipo %TIPO%

echo Worker finalizado
pause
