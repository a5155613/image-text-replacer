@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "ISCC_EXES=C:\Program Files (x86)\Inno Setup 6\ISCC.exe|C:\Program Files\Inno Setup 6\ISCC.exe|%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

echo === ImageTextReplacer 安装包编译脚本 ===
echo.

REM ---- 检查 ISCC ----
set "ISCC="
for %%I in (%ISCC_EXES:|= %) do (
    if exist "%%~I" set "ISCC=%%~I"
)
if not defined ISCC (
    echo [ERROR] 未找到 Inno Setup 的 ISCC.exe
    echo 请先安装 Inno Setup 6:
    echo   下载: https://jrsoftware.org/isdl.php
    echo   或: winget install --id JRSoftware.InnoSetup -e -s winget
    pause
    exit /b 1
)
echo [OK] ISCC: %ISCC%

REM ---- 检查 dist 目录完整性 ----
echo.
echo [检查] dist 目录完整性...
if not exist "%~dp0dist\ImageTextReplacer\ImageTextReplacer.exe" (
    echo [ERROR] 未找到 dist\ImageTextReplacer\ImageTextReplacer.exe
    echo 请先运行: pyinstaller image_text_replacer.spec
    echo 或运行: build_all.bat
    pause
    exit /b 1
)
if not exist "%~dp0dist\ImageTextReplacer\_internal\python314.dll" (
    echo [ERROR] 未找到 dist\ImageTextReplacer\_internal\python314.dll
    echo _internal 目录不完整，请重新运行 pyinstaller image_text_replacer.spec
    pause
    exit /b 1
)

REM 统计文件数
set FILE_COUNT=0
for /f %%A in ('dir /s /b /a-d "%~dp0dist\ImageTextReplacer" 2^>nul ^| find /c /v ""') do set FILE_COUNT=%%A
echo [OK] dist 包含 %FILE_COUNT% 个文件

REM 检查关键文件
echo [OK] ImageTextReplacer.exe 存在
echo [OK] _internal\python314.dll 存在

REM ---- 编译 ----
echo.
echo [编译] 使用 Inno Setup 编译安装包...
"%ISCC%" "%~dp0installer.iss"
if errorlevel 1 (
    echo.
    echo [ERROR] 编译失败，请检查上面的错误信息
    pause
    exit /b 1
)

REM ---- 验证产物 ----
echo.
echo [验证] 安装包产物...
set SETUP=%~dp0Output\ImageTextReplacer_Setup.exe
if not exist "%SETUP%" (
    echo [ERROR] 未找到安装包产物 Output\ImageTextReplacer_Setup.exe
    pause
    exit /b 1
)

for %%A in ("%SETUP%") do set SIZE_MB=%%~zA
set /a SIZE_MB=%SIZE_MB% / 1048576
echo [OK] 安装包: %~dp0Output\ImageTextReplacer_Setup.exe
echo [OK] 大小: %SIZE_MB% MB

if %SIZE_MB% LSS 200 (
    echo.
    echo [WARNING] 安装包大小只有 %SIZE_MB% MB，正常应该 300+ MB
    echo           这可能意味着 _internal 目录没被正确打包！
    echo           请检查 installer.iss 的 Source 路径是否正确。
) else (
    echo.
    echo [SUCCESS] 安装包大小正常（%SIZE_MB% MB），包含完整依赖
)

echo.
echo 完成！安装包路径: Output\ImageTextReplacer_Setup.exe
pause
endlocal
