@echo off
REM =====================================================
REM 一键重新打包 + 生成安装包（如果 Inno Setup 已安装）
REM 产物:
REM   dist/ImageTextReplacer/ImageTextReplacer.exe  （直接运行的 onedir 版本）
REM   Output/ImageTextReplacer_Setup.exe            （安装包，需 Inno Setup）
REM =====================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PY_EXE=%~dp0venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo ===============================================
echo  批量图片文字替换工具 - 全量打包
echo ===============================================
echo.

REM 清理旧产物
echo [Step 1/3] 清理旧 PyInstaller 产物...
if exist "%~dp0build" rmdir /s /q "%~dp0build" 2>nul
if exist "%~dp0dist\ImageTextReplacer" rmdir /s /q "%~dp0dist\ImageTextReplacer" 2>nul

echo [Step 2/3] 运行 PyInstaller 打包（约 3-8 分钟）...
"%PY_EXE%" -m PyInstaller --clean image_text_replacer.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller 打包失败，请检查上面的日志
    pause
    exit /b 1
)

if not exist "%~dp0dist\ImageTextReplacer\ImageTextReplacer.exe" (
    echo [ERROR] 未找到 dist\ImageTextReplacer\ImageTextReplacer.exe
    pause
    exit /b 1
)

echo.
echo [Step 3/3] 检查 Inno Setup 并编译安装包...
set "ISCC="
for %%I in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do (
    if exist "%%~I" set "ISCC=%%~I"
)

if defined ISCC (
    call "%ISCC%" "%~dp0installer.iss"
    echo.
    echo [DONE] onedir + 安装包 全部完成
    echo   - onedir:    dist\ImageTextReplacer\ImageTextReplacer.exe
    echo   - 安装包:    Output\ImageTextReplacer_Setup.exe
) else (
    echo [SKIP] 未检测到 Inno Setup，跳过安装包编译
    echo        如需安装包，请先安装 Inno Setup 后运行 build_installer.bat
    echo        下载: https://jrsoftware.org/isdl.php
    echo.
    echo [DONE] onedir 版本已完成: dist\ImageTextReplacer\ImageTextReplacer.exe
    echo        可直接双击运行，或用 7zip 压缩后分享
)

echo.
pause
endlocal
