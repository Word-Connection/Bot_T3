@echo off
setlocal enabledelayedexpansion

echo =====================================
echo   Setup y Ejecutor Bot T3
echo =====================================

REM --- Verificar dependencias requeridas ---
echo Verificando dependencias del sistema...

REM --- Verificar Python ---
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python no esta instalado o no esta en el PATH
    echo.
    echo Instala Python desde: https://www.python.org/downloads/
    echo Asegurate de marcar "Add Python to PATH" durante la instalacion
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo Python !PYTHON_VERSION! detectado
)

REM --- Verificar Git ---
git --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git no esta instalado o no esta en el PATH
    echo.
    echo Instala Git desde: https://git-scm.com/downloads
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=3" %%i in ('git --version') do set "GIT_VERSION=%%i"
    echo Git !GIT_VERSION! detectado
)

echo Todas las dependencias estan disponibles
echo.

REM --- Configurar politica de ejecucion de PowerShell ---
echo Configurando permisos de ejecucion de scripts...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser -Force" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Permisos de PowerShell configurados correctamente
) else (
    echo ADVERTENCIA: No se pudieron configurar los permisos de PowerShell
    echo El script continuara, pero podrian haber problemas con algunos comandos
)
echo.

REM --- Hacer pull del repositorio forzado ---
echo Actualizando repositorio desde GitHub forzando cambios...

REM --- Verificar si estamos en un repositorio git ---
git status >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Inicializando repositorio git...
    git init
    git remote add origin https://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@github.com/Word-Connection/Bot_T3.git
    git fetch origin main
    git checkout -B main origin/main
) else (
    echo Descartando todos los cambios locales...
    
    REM --- Configurar remote temporal con token para el pull ---
    git remote set-url origin https://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@github.com/Word-Connection/Bot_T3.git
    
    REM --- Descartar todos los cambios locales ---
    git reset --hard HEAD >nul 2>&1
    git clean -fd >nul 2>&1
    
    REM --- Cambiar a main branch forzadamente ---
    git checkout main >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo Creando branch main local...
        git checkout -b main >nul 2>&1
    )
    
    REM --- Hacer fetch y reset forzado a main ---
    echo Descargando ultimos cambios de main...
    git fetch origin main
    git reset --hard origin/main
    git clean -fd
    
    REM --- Restaurar URL del remote sin token ---
    git remote set-url origin https://github.com/Word-Connection/Bot_T3.git
)

if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo actualizar el repositorio
    echo Verifica tu conexion a internet
    pause
    exit /b 1
) else (
    echo Repositorio actualizado exitosamente
)

echo =====================================
echo   Configurando Entorno Virtual
echo =====================================

REM --- Crear entorno virtual si no existe ---
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudo crear el entorno virtual
        echo Verifica que Python este instalado
        pause
        exit /b 1
    )
) else (
    echo Entorno virtual ya existe
)

REM --- Activar entorno virtual ---
echo Activando entorno virtual...
call venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo activar el entorno virtual
    pause
    exit /b 1
)

REM --- Actualizar pip ---
echo Actualizando pip...
python -m pip install --upgrade pip

REM --- Instalar/actualizar requerimientos ---
if exist "requirements.txt" (
    echo Instalando/actualizando requerimientos desde requirements.txt...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudieron instalar los requerimientos
        pause
        exit /b 1
    )
) else (
    echo ADVERTENCIA: No se encontro requirements.txt
    echo Instalando dependencias basicas...
    pip install requests pyautogui opencv-python pillow numpy
)

echo =====================================
echo   Setup completado exitosamente
echo =====================================
echo.

echo =====================================
echo   Configurando Worker
echo =====================================

REM --- Verificar directorio Workers-T3 ---
set "REPO_NAME=Workers-T3"
if not exist "%REPO_NAME%" (
    echo ERROR: No se encuentra el directorio Workers-T3
    echo Asegurate de que el pull del repositorio haya funcionado correctamente
    pause
    exit /b 1
)

REM --- Verificar worker.py ---
if not exist "Workers-T3\worker.py" (
    echo ERROR: No se encuentra Workers-T3\worker.py
    echo Asegurate de que el repositorio este completo
    pause
    exit /b 1
)

REM --- Verificar/configurar archivo .env ---
if exist "Workers-T3\.env" (
    echo.
    echo =====================================
    echo   CONFIGURACION ACTUAL (.env)
    echo =====================================
    
    REM --- Leer configuración actual ---
    for /f "tokens=1,2 delims==" %%a in (Workers-T3\.env) do (
        if "%%a"=="PC_ID" (
            set "CURRENT_PC_ID=%%b"
            echo PC_ID: %%b
        )
        if "%%a"=="WORKER_TYPE" (
            set "CURRENT_WORKER_TYPE=%%b"
            echo WORKER_TYPE: %%b
        )
        if "%%a"=="BACKEND_URL" (
            set "CURRENT_BACKEND_URL=%%b"
            echo BACKEND_URL: %%b
        )
        if "%%a"=="API_KEY" (
            set "CURRENT_API_KEY=%%b"
            echo API_KEY: %%b
        )
        if "%%a"=="PROCESS_DELAY" echo PROCESS_DELAY: %%b
        if "%%a"=="CONNECTION_TIMEOUT" echo CONNECTION_TIMEOUT: %%b
        if "%%a"=="LOG_LEVEL" echo LOG_LEVEL: %%b
        if "%%a"=="TIMEZONE" echo TIMEZONE: %%b
    )
    
    echo =====================================
    echo.
    echo ¿Deseas modificar la configuracion? (S/N)
    set /p "MODIFICAR_CONFIG="
    
    if /i "!MODIFICAR_CONFIG!"=="S" (
        goto :configurar_env
    ) else (
        echo Manteniendo configuracion actual
        goto :preguntar_ejecutar
    )
    
) else (
    echo.
    echo No se encontro archivo .env en Workers-T3
    echo Creando nueva configuracion...
    
    REM --- Valores por defecto para nueva configuracion ---
    set "CURRENT_PC_ID=%COMPUTERNAME%"
    set "CURRENT_WORKER_TYPE=deudas"
    set "CURRENT_BACKEND_URL=http://192.168.9.160:8000"
    set "CURRENT_API_KEY=lucas123"
    
    goto :configurar_env
)

:configurar_env
echo.
echo =====================================
echo   CONFIGURACION DEL WORKER
echo =====================================
echo Presiona ENTER para mantener el valor por defecto
echo.

REM --- Configurar PC_ID ---
echo PC_ID actual: !CURRENT_PC_ID!
set /p "NEW_PC_ID=Nuevo PC_ID [!CURRENT_PC_ID!]: "
if "!NEW_PC_ID!"=="" set "NEW_PC_ID=!CURRENT_PC_ID!"

REM --- Configurar WORKER_TYPE ---
echo.
echo WORKER_TYPE actual: !CURRENT_WORKER_TYPE!
echo Tipos disponibles: deudas, movimientos, pin
set /p "NEW_WORKER_TYPE=Nuevo tipo [!CURRENT_WORKER_TYPE!]: "
if "!NEW_WORKER_TYPE!"=="" set "NEW_WORKER_TYPE=!CURRENT_WORKER_TYPE!"

REM --- Configurar BACKEND_URL ---
echo.
echo BACKEND_URL actual: !CURRENT_BACKEND_URL!
set /p "NEW_BACKEND_URL=Nueva URL [!CURRENT_BACKEND_URL!]: "
if "!NEW_BACKEND_URL!"=="" set "NEW_BACKEND_URL=!CURRENT_BACKEND_URL!"

REM --- Configurar API_KEY ---
echo.
echo API_KEY actual: !CURRENT_API_KEY!
set /p "NEW_API_KEY=Nueva API Key [!CURRENT_API_KEY!]: "
if "!NEW_API_KEY!"=="" set "NEW_API_KEY=!CURRENT_API_KEY!"

REM --- Mostrar resumen de la configuracion ---
echo.
echo =====================================
echo   RESUMEN DE CONFIGURACION
echo =====================================
echo PC_ID: !NEW_PC_ID!
echo WORKER_TYPE: !NEW_WORKER_TYPE!
echo BACKEND_URL: !NEW_BACKEND_URL!
echo API_KEY: !NEW_API_KEY!
echo =====================================
echo.
echo ¿Confirmas esta configuracion? (S/N)
set /p "CONFIRMAR_CONFIG="

if /i "!CONFIRMAR_CONFIG!"=="S" (
    echo.
    echo Guardando configuracion...
    (
        echo PC_ID=!NEW_PC_ID!
        echo WORKER_TYPE=!NEW_WORKER_TYPE!
        echo BACKEND_URL=!NEW_BACKEND_URL!
        echo API_KEY=!NEW_API_KEY!
        echo PROCESS_DELAY=30
        echo CONNECTION_TIMEOUT=300
        echo LOG_LEVEL=INFO
        echo TIMEZONE=America/Argentina/Buenos_Aires
    ) > Workers-T3\.env
    
    echo Archivo .env guardado exitosamente
) else (
    echo Configuracion cancelada
    if not exist "Workers-T3\.env" (
        echo ADVERTENCIA: No hay archivo .env configurado
        pause
        exit /b 1
    )
)

:preguntar_ejecutar

echo.
echo ¿Deseas ejecutar el worker ahora? (S/N)
set /p "EJECUTAR_WORKER="
if /i "!EJECUTAR_WORKER!"=="S" (
    goto :ejecutar_worker
) else (
    echo.
    echo Setup completado. Para ejecutar el worker mas tarde, ejecuta este archivo nuevamente.
    goto :fin
)

:ejecutar_worker
REM --- Leer configuración del .env ---
echo Leyendo configuracion del worker...
for /f "tokens=1,2 delims==" %%a in (Workers-T3\.env) do (
    if "%%a"=="PC_ID" set "PC_ID=%%b"
    if "%%a"=="WORKER_TYPE" set "WORKER_TYPE=%%b"
    if "%%a"=="BACKEND_URL" set "BACKEND_URL=%%b"
    if "%%a"=="API_KEY" set "API_KEY=%%b"
)

REM --- Verificar variables requeridas ---
if "!PC_ID!"=="" (
    echo ERROR: PC_ID no encontrado en .env
    pause
    exit /b 1
)
if "!WORKER_TYPE!"=="" (
    echo ERROR: WORKER_TYPE no encontrado en .env
    pause
    exit /b 1
)
if "!BACKEND_URL!"=="" (
    echo ERROR: BACKEND_URL no encontrado en .env
    pause
    exit /b 1
)
if "!API_KEY!"=="" (
    echo ERROR: API_KEY no encontrado en .env
    pause
    exit /b 1
)

REM --- Mostrar configuración ---
echo.
echo =====================================
echo   CONFIGURACION WORKER
echo =====================================
echo PC_ID: !PC_ID!
echo Tipo: !WORKER_TYPE!
echo Backend: !BACKEND_URL!
echo API Key: !API_KEY!
echo =====================================
echo.

REM --- Crear directorio de logs si no existe ---
if not exist "Workers-T3\logs" mkdir "Workers-T3\logs"

REM --- Ejecutar worker ---
echo Iniciando Worker T3...
echo (Presiona Ctrl+C para detener)
echo.

python Workers-T3\worker.py --tipo !WORKER_TYPE! --api_key !API_KEY! --pc_id !PC_ID!

echo.
echo =====================================
echo Worker finalizado
echo =====================================

:fin
echo.
echo =====================================
echo   SETUP COMPLETADO
echo =====================================
echo Todos los componentes han sido configurados:
echo - Repositorio actualizado
echo - Entorno virtual creado y configurado  
echo - Dependencias instaladas
echo - Worker configurado en Workers-T3/
echo.
echo Para ejecutar el worker nuevamente, ejecuta este archivo
echo =====================================
echo.
pause