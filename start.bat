@echo off
REM ============================================================
REM 税务风险研判系统 - Windows 统一启动脚本
REM ============================================================
REM 使用方式：
REM   开发模式：  start.bat dev
REM   生产模式：  start.bat prod
REM   仅后端：    start.bat backend
REM   仅前端：    start.bat frontend
REM ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=dev"

echo.
echo ==========================================
echo   税务风险研判系统 - 启动脚本
echo   模式: %MODE%
echo ==========================================
echo.

REM ============================================================
REM 检查依赖
REM ============================================================
echo [INFO] 检查环境依赖...

where python >nul 2>nul
if %errorlevel% neq 0 (
    where python3 >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] 未找到 Python，请先安装 Python 3.10+
        pause
        exit /b 1
    )
    set "PYTHON=python3"
) else (
    set "PYTHON=python"
)

%PYTHON% --version
echo.

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)
node --version
echo.

REM ============================================================
REM 安装依赖
REM ============================================================
if "%MODE%"=="dev" goto :install_all
if "%MODE%"=="prod" goto :install_all
if "%MODE%"=="backend" goto :install_backend
if "%MODE%"=="frontend" goto :install_frontend
goto :help

:install_all
call :install_backend
call :install_frontend
goto :start_%MODE%

:install_backend
echo [INFO] 安装后端 Python 依赖...
cd /d "%SCRIPT_DIR%backend"
%PYTHON% -m pip install -r requirements.txt -q
cd /d "%SCRIPT_DIR%"
goto :eof

:install_frontend
echo [INFO] 安装前端 Node.js 依赖...
cd /d "%SCRIPT_DIR%"
if not exist "node_modules" (
    call npm install
) else (
    echo [INFO] node_modules 已存在，跳过安装
)
goto :eof

REM ============================================================
REM 开发模式
REM ============================================================
:start_dev
echo.
echo [INFO] 启动后端服务...
cd /d "%SCRIPT_DIR%backend"

if not exist ".env" (
    if exist ".env.example" (
        echo [WARN] .env 不存在，复制 .env.example
        copy .env.example .env >nul
    )
)

start "后端服务 - FastAPI" cmd /c "%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo [INFO] 后端服务已启动 - http://localhost:8000
echo [INFO] Swagger 文档 - http://localhost:8000/docs

timeout /t 3 /nobreak >nul

cd /d "%SCRIPT_DIR%"
echo [INFO] 启动前端开发服务器...
start "前端服务 - Vite" cmd /c "npx vite --port 3000"
echo [INFO] 前端开发服务器已启动 - http://localhost:3000

echo.
echo ==========================================
echo   前端: http://localhost:3000
echo   后端: http://localhost:8000
echo   Swagger: http://localhost:8000/docs
echo ==========================================
echo.
echo 关闭此窗口不会停止服务
echo 请手动关闭 "后端服务" 和 "前端服务" 窗口
pause
goto :end

REM ============================================================
REM 生产模式
REM ============================================================
:start_prod
echo.
echo [INFO] 构建前端生产版本...
cd /d "%SCRIPT_DIR%"
call npx tsc -b && call npx vite build
echo [INFO] 前端构建完成

echo [INFO] 复制静态文件到后端...
if exist "backend\static" rmdir /s /q "backend\static"
xcopy /E /I /Q "dist" "backend\static" >nul

echo.
echo [INFO] 启动后端服务（托管静态文件）...
cd /d "%SCRIPT_DIR%backend"
start "后端服务 - FastAPI" cmd /c "%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo.
echo ==========================================
echo   应用: http://localhost:8000
echo   Swagger: http://localhost:8000/docs
echo ==========================================
echo.
pause
goto :end

REM ============================================================
REM 仅后端
REM ============================================================
:start_backend
echo.
echo [INFO] 启动后端服务...
cd /d "%SCRIPT_DIR%backend"

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
    )
)

start "后端服务 - FastAPI" cmd /c "%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo [INFO] 后端服务已启动 - http://localhost:8000
echo [INFO] Swagger 文档 - http://localhost:8000/docs
echo.
pause
goto :end

REM ============================================================
REM 仅前端
REM ============================================================
:start_frontend
echo.
echo [INFO] 启动前端开发服务器...
cd /d "%SCRIPT_DIR%"
start "前端服务 - Vite" cmd /c "npx vite --port 3000"
echo [INFO] 前端开发服务器已启动 - http://localhost:3000
echo.
pause
goto :end

REM ============================================================
REM 帮助
REM ============================================================
:help
echo 用法: start.bat [模式]
echo.
echo   dev       开发模式（同时启动前后端）
echo   prod      生产模式（构建前端 + 启动后端）
echo   backend   仅启动后端
echo   frontend  仅启动前端
echo.
pause

:end
endlocal
