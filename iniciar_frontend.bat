@echo off
setlocal enabledelayedexpansion

echo =====================================
echo   Iniciador Frontend Control Bot T3
echo =====================================

REM --- Verificar Python ---
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado
    pause
    exit /b 1
)

REM --- Verificar que existe el proyecto configurado ---
if not exist "Workers-T3" (
    echo ERROR: No se encuentra Workers-T3
    echo Ejecuta primero setup_and_run.bat para configurar el proyecto
    pause
    exit /b 1
)

REM --- Activar entorno virtual si existe ---
if exist "venv\Scripts\activate.bat" (
    echo Activando entorno virtual...
    call venv\Scripts\activate.bat
) else (
    echo ADVERTENCIA: No se encuentra entorno virtual
    echo Se intentara usar Python del sistema
)

REM --- Instalar Flask si no esta ---
echo Verificando dependencias...
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Instalando Flask...
    pip install flask
)

REM --- Iniciar frontend ---
echo.
echo =====================================
echo   Iniciando Frontend de Control
echo =====================================
echo.
echo 🚀 El navegador se abrira automaticamente en:
echo 📱 http://localhost:5555
echo.
echo ⚠️  IMPORTANTE:
echo    - NO cierres esta ventana
echo    - Usa el navegador para controlar el bot
echo    - Presiona Ctrl+C aqui para cerrar todo
echo.
echo =====================================

python frontend_control.py

echo.
echo Frontend cerrado
pause