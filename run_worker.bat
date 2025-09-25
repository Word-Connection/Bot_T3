@echo off
REM =====================================
REM  Ejecutor Worker T3
REM =====================================

REM --- Verificar si el directorio Workers-T3 existe ---
if not exist Workers-T3 (
    echo ERROR: Directorio Workers-T3 no encontrado. Ejecuta config_worker.bat primero.
    pause
    exit /b 1
)

REM --- Cambiar al directorio del repositorio ---
cd Workers-T3

REM --- Verificar si el entorno virtual existe ---
if not exist venv (
    echo ERROR: Entorno virtual no encontrado. Ejecuta config_worker.bat primero.
    pause
    exit /b 1
)

REM --- Verificar si el archivo .env existe ---
if not exist .env (
    echo ERROR: Archivo .env no encontrado. Ejecuta config_worker.bat para configurar.
    pause
    exit /b 1
)

REM --- Activar entorno virtual ---
call venv\Scripts\activate.bat

REM --- Ejecutar worker en primer plano ---
echo Iniciando worker...
python worker.py
pause