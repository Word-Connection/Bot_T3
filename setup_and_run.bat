@echo off
setlocal enabledelayedexpansion

echo =====================================
echo   Setup y Ejecutor Bot T3
echo =====================================

REM --- Hacer pull del repositorio ---
echo Actualizando repositorio desde GitHub...
git pull https://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@github.com/Word-Connection/Bot_T3.git
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo hacer pull del repositorio
    echo Verificando si git esta configurado...
    git status
    if %ERRORLEVEL% neq 0 (
        echo Inicializando repositorio git...
        git init
        git remote add origin https://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@github.com/Word-Connection/Bot_T3.git
        git pull origin main
    )
    echo.
    echo Si el error persiste, verifica tu conexion a internet
    pause
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

REM --- Verificar/crear directorio Workers-T3 ---
set "REPO_NAME=Workers-T3"
if not exist "%REPO_NAME%" (
    echo Creando directorio Workers-T3...
    mkdir "%REPO_NAME%"
)

cd "%REPO_NAME%"

REM --- Crear/verificar archivo .env ---
if not exist ".env" (
    echo.
    echo No se encontro archivo .env, creando configuracion...
    echo.
    echo Ingresa la siguiente informacion:
    echo.
    
    set /p "PC_ID=ID de esta PC (ej: PC-001): "
    if "!PC_ID!"=="" set "PC_ID=PC-001"
    
    echo.
    echo Tipos de worker disponibles:
    echo 1. deudas
    echo 2. movimientos
    echo 3. otro
    set /p "WORKER_CHOICE=Selecciona tipo (1-3): "
    
    if "!WORKER_CHOICE!"=="1" set "WORKER_TYPE=deudas"
    if "!WORKER_CHOICE!"=="2" set "WORKER_TYPE=movimientos"
    if "!WORKER_CHOICE!"=="3" (
        set /p "WORKER_TYPE=Ingresa tipo personalizado: "
    )
    if "!WORKER_TYPE!"=="" set "WORKER_TYPE=deudas"
    
    set /p "BACKEND_URL=URL del backend (ej: http://localhost:8000): "
    if "!BACKEND_URL!"=="" set "BACKEND_URL=http://localhost:8000"
    
    set /p "API_KEY=API Key: "
    if "!API_KEY!"=="" set "API_KEY=tu_api_key_aqui"
    
    echo.
    echo Creando archivo .env...
    (
        echo PC_ID=!PC_ID!
        echo WORKER_TYPE=!WORKER_TYPE!
        echo BACKEND_URL=!BACKEND_URL!
        echo API_KEY=!API_KEY!
        echo.
        echo # Configuracion adicional
        echo LOG_LEVEL=INFO
        echo MAX_RETRIES=3
        echo TIMEOUT=30
    ) > .env
    
    echo Archivo .env creado exitosamente
)

REM --- Verificar/crear entorno virtual del worker ---
if not exist "venv" (
    echo Creando entorno virtual para el worker...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: No se pudo crear el entorno virtual del worker
        pause
        exit /b 1
    )
)

REM --- Activar entorno virtual del worker ---
echo Activando entorno virtual del worker...
call venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo ERROR: No se pudo activar el entorno virtual del worker
    pause
    exit /b 1
)

REM --- Instalar dependencias del worker ---
echo Instalando dependencias del worker...
pip install requests pyautogui opencv-python pillow numpy python-dotenv

REM --- Crear worker.py basico si no existe ---
if not exist "worker.py" (
    echo Creando worker.py basico...
    (
        echo import os
        echo import sys
        echo import argparse
        echo from dotenv import load_dotenv
        echo.
        echo # Cargar variables de entorno
        echo load_dotenv^(^)
        echo.
        echo def main^(^):
        echo     parser = argparse.ArgumentParser^(description='Worker T3'^)
        echo     parser.add_argument^('--tipo', required=True, help='Tipo de worker'^)
        echo     parser.add_argument^('--api_key', required=True, help='API Key'^)
        echo     parser.add_argument^('--pc_id', required=True, help='PC ID'^)
        echo     parser.add_argument^('--backend', required=True, help='Backend URL'^)
        echo.
        echo     args = parser.parse_args^(^)
        echo.
        echo     print^(f"Worker iniciado - Tipo: {args.tipo}, PC: {args.pc_id}"^)
        echo     print^(f"Backend: {args.backend}"^)
        echo     
        echo     # Aqui iria la logica del worker
        echo     print^("Worker funcionando... ^(Ctrl+C para detener^)"^)
        echo     
        echo     try:
        echo         while True:
        echo             pass  # Logica del worker aqui
        echo     except KeyboardInterrupt:
        echo         print^("Worker detenido por el usuario"^)
        echo.
        echo if __name__ == '__main__':
        echo     main^(^)
    ) > worker.py
    echo worker.py creado
)

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
for /f "tokens=1,2 delims==" %%a in (.env) do (
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

REM --- Verificar worker.py ---
if not exist "worker.py" (
    echo ERROR: worker.py no encontrado
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
if not exist "logs" mkdir logs

REM --- Ejecutar worker ---
echo Iniciando Worker T3...
echo (Presiona Ctrl+C para detener)
echo.

python worker.py --tipo !WORKER_TYPE! --api_key !API_KEY! --pc_id !PC_ID! --backend !BACKEND_URL!

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