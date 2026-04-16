@echo off
setlocal enabledelayedexpansion
title Bot T3 — Panel de Control

REM =============================================
REM  iniciar.bat — Setup + Panel de Control Bot T3
REM  Ejecutar como usuario normal (no admin)
REM =============================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

REM --- Verificar Python ---
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado o no esta en el PATH.
    echo Descargalo desde https://www.python.org/downloads/
    echo Marcale "Add Python to PATH" al instalarlo.
    pause & exit /b 1
)

REM =============================================
REM  Entorno virtual
REM =============================================
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudo crear el entorno virtual.
        pause & exit /b 1
    )
    echo Entorno virtual creado.
)

call venv\Scripts\activate.bat >nul 2>&1

REM --- Instalar/actualizar deps ---
if exist "requirements.txt" (
    echo Verificando dependencias...
    pip install -r requirements.txt -q --disable-pip-version-check
) else (
    pip install flask pyautogui requests -q --disable-pip-version-check
)

REM --- Flask es requerido para el panel ---
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Instalando Flask...
    pip install flask -q
)

REM =============================================
REM  Verificar directorio del worker
REM =============================================
if not exist "Workers-T3\worker.py" (
    echo ADVERTENCIA: No se encuentra Workers-T3\worker.py
    echo El panel se abrira en modo configuracion.
)

REM =============================================
REM  Lanzar panel de control
REM =============================================
echo.
echo ============================================
echo   Abriendo panel de control en el navegador
echo   http://localhost:5555
echo ============================================
echo.
echo Presiona Ctrl+C en esta ventana para cerrar todo.
echo.

python frontend_control.py

echo.
echo Panel cerrado.
pause
