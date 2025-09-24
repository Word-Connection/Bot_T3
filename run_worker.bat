@echo off
REM =====================================
REM  Worker T3 - Ejecutor Simple
REM =====================================

echo =====================================
echo   WORKER T3 - INICIANDO
echo =====================================

REM --- Habilitar PowerShell scripts ---
powershell -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force" >nul 2>&1

REM --- Verificar que Python existe ---
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ❌ ERROR: Python no está instalado
    echo Instala Python desde https://python.org y vuelve a intentar
    pause
    exit /b 1
)

echo ✓ Python encontrado:
python --version

REM --- Verificar que existe .env ---
if not exist .env (
    echo ❌ ERROR: No se encontró archivo .env
    echo Ejecuta config.bat primero para crear la configuración
    pause
    exit /b 1
)

REM --- Mostrar configuración actual ---
echo.
echo =====================================
echo CONFIGURACION ACTUAL (.env):
echo =====================================
type .env
echo =====================================
echo.
set /p CONTINUE="¿La configuración es correcta? (s/n): "
if /i "%CONTINUE%"=="n" (
    echo Ejecuta config.bat para cambiar la configuración
    pause
    exit /b 0
)

REM --- Verificar que existe worker.py ---
if not exist worker.py (
    echo ❌ ERROR: No se encontró worker.py
    echo Copia worker.py a esta carpeta
    pause
    exit /b 1
)

REM --- Setup entorno virtual ---
echo Configurando entorno virtual...
if not exist venv (
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ ERROR: No se pudo crear entorno virtual
        pause
        exit /b 1
    )
    echo ✓ Entorno virtual creado
) else (
    echo ✓ Usando entorno virtual existente
)

REM --- Activar entorno ---
call venv\Scripts\activate
if %ERRORLEVEL% NEQ 0 (
    echo ❌ ERROR: No se pudo activar entorno virtual
    pause
    exit /b 1
)

REM --- Instalar/actualizar dependencias ---
echo Instalando dependencias...
python -m pip install --upgrade pip --quiet
pip install requests>=2.31.0 python-dotenv>=1.0.0 --quiet
if %ERRORLEVEL% NEQ 0 (
    echo ❌ ERROR: No se pudieron instalar dependencias
    pause
    exit /b 1
)
echo ✓ Dependencias instaladas

REM --- Ejecutar worker ---
echo.
echo =====================================
echo   INICIANDO WORKER...
echo =====================================
python worker.py

REM --- Worker terminado ---
echo.
echo =====================================
echo Worker finalizado
echo =====================================
pause