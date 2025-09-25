

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

REM --- Activar entorno virtual ---
call venv\Scripts\activate.bat

REM --- Leer PC_ID desde .env ---
for /f "tokens=1,* delims==" %%a in (.env) do (
    if "%%a"=="PC_ID" set PC_ID=%%b
)

if not defined PC_ID (
    echo ERROR: PC_ID no definido en .env. Ejecuta config_worker.bat para configurar.
    pause
    exit /b 1
)

:run_worker
REM --- Iniciar worker en segundo plano ---
echo Iniciando worker %PC_ID%...
start /b python worker.py > worker_%PC_ID%.log 2>&1

REM --- Bucle para verificar actualizaciones cada 5 minutos ---
:check_updates
timeout /t 300 /nobreak >nul
echo Verificando actualizaciones...
git fetch
for /f %%i in ('git rev-parse HEAD') do set CURRENT_HASH=%%i
for /f %%i in ('git rev-parse origin/main') do set REMOTE_HASH=%%i
if "%CURRENT_HASH%" neq "%REMOTE_HASH%" (
    echo Nuevos cambios detectados, actualizando...
    git pull
    call venv\Scripts\activate.bat
    pip install requests python-dotenv
    echo Reiniciando worker...
    taskkill /im python.exe /f >nul 2>&1
    start /b python worker.py > worker_%PC_ID%.log 2>&1
)
goto :check_updates
```
