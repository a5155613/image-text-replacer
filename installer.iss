; ============================================================
; 批量图片文字替换工具 - Inno Setup 安装脚本 (修复版 v2)
; 修复:
;   - 改用 Source: "dist\ImageTextReplacer\*" 整行打包，避免漏 _internal
;   - 增加 [Code] 安装后验证关键 DLL 是否存在
;   - 增加 Flags: restartreplace 解决 DLL 被占用时替换失败
;
; 编译方法:
;   1. 先运行 build_all.bat (会先 PyInstaller 再编译本文件)
;   2. 或安装 Inno Setup 后，双击 build_installer.bat
;   3. 或命令行: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; 产物: Output\ImageTextReplacer_Setup.exe
; ============================================================

#define MyAppName      "批量图片文字替换工具"
#define MyAppShortName "ImageTextReplacer"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "image-text-replacer"
#define MyAppExeName   "ImageTextReplacer.exe"

[Setup]
AppId={{B8E9F7A1-2C3D-4E5F-9A6B-7C8D0E1F2A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/a5155613/image-text-replacer
AppSupportURL=https://github.com/a5155613/image-text-replacer/issues
AppUpdatesURL=https://github.com/a5155613/image-text-replacer/releases
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; ----- 安装包属性 -----
OutputDir=Output
OutputBaseFilename=ImageTextReplacer_Setup
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
PrivilegesRequired=lowest   ; 普通用户也能安装，无需管理员
UninstallDisplayIcon={app}\{#MyAppExeName}
AppCopyright=Copyright (C) 2026
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
ChangesAssociations=no
; 允许卸载时清空残留 DLL
UninstallDeleteFilesAndSubdirsForAllUsers=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; ----- FIX v2: 一次性包含整个 dist\ImageTextReplacer 目录 (exe + _internal) -----
; 之前分两行写会漏 _internal 下的部分 DLL，导致 python314.dll LoadLibrary 失败
; restartreplace: 文件被占用时重启替换；createallsubdirs: 创建所有子目录
Source: "dist\{#MyAppShortName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs restartreplace; Excludes: "\_internal\__pycache__\*,\_internal\*.pyc"
; 附加文件
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:ProgramOnTheWeb,{#MyAppName}}"; Filename: "https://github.com/a5155613/image-text-replacer"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ============================================================================
; [Code] 安装后验证：确保 python314.dll 及所有关键依赖都已正确安装
; ============================================================================
[Code]
function IsX64: Boolean;
begin
  Result := True;  { 本安装包仅限 x64，在 Setup 段已限制 }
end;

{ 检查单个文件是否存在，不存在则累积到错误信息 }
procedure CheckFile(const FilePath, DisplayName: String; var MissingList: String);
begin
  if not FileExists(FilePath) then
  begin
    if MissingList <> '' then MissingList := MissingList + #13#10;
    MissingList := MissingList + '  - ' + DisplayName + ' (缺少: ' + FilePath + ')';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  InternalDir, MissingList: String;
  Msg: TMsgDlgType;
begin
  { 安装完成后 (PostInstall) 校验关键 DLL }
  if CurStep = ssPostInstall then
  begin
    InternalDir := ExpandConstant('{app}\_internal');
    MissingList := '';

    { ==== python314.dll (最关键) ==== }
    CheckFile(InternalDir + '\python314.dll',         'Python 3.14 核心运行时 (python314.dll)', MissingList);
    CheckFile(ExpandConstant('{app}') + '\python314.dll', '顶层 python314.dll (fallback)',   MissingList);

    { ==== VC++ Runtime ==== }
    CheckFile(InternalDir + '\vcruntime140.dll',        'VC++ Runtime (vcruntime140.dll)',        MissingList);
    CheckFile(InternalDir + '\vcruntime140_1.dll',      'VC++ Runtime (vcruntime140_1.dll)',      MissingList);
    CheckFile(InternalDir + '\vcruntime140_threads.dll','VC++ Runtime (vcruntime140_threads.dll)',MissingList);
    CheckFile(InternalDir + '\msvcp140.dll',            'VC++ CRT (msvcp140.dll)',                 MissingList);
    CheckFile(InternalDir + '\msvcp140_1.dll',          'VC++ CRT (msvcp140_1.dll)',               MissingList);
    CheckFile(InternalDir + '\msvcp140_2.dll',          'VC++ CRT (msvcp140_2.dll)',               MissingList);
    CheckFile(InternalDir + '\msvcp140_atomic_wait.dll','VC++ CRT (msvcp140_atomic_wait.dll)',     MissingList);
    CheckFile(InternalDir + '\concrt140.dll',           'VC++ ConcRT (concrt140.dll)',             MissingList);

    { ==== UCRT (Universal C Runtime) ==== }
    CheckFile(InternalDir + '\ucrtbase.dll',            'UCRT 核心 (ucrtbase.dll)',                 MissingList);
    CheckFile(InternalDir + '\api-ms-win-crt-runtime-l1-1-0.dll','UCRT api-ms-win-crt-runtime',      MissingList);
    CheckFile(InternalDir + '\api-ms-win-crt-stdio-l1-1-0.dll',  'UCRT api-ms-win-crt-stdio',        MissingList);
    CheckFile(InternalDir + '\api-ms-win-crt-heap-l1-1-0.dll',   'UCRT api-ms-win-crt-heap',         MissingList);
    CheckFile(InternalDir + '\api-ms-win-crt-string-l1-1-0.dll', 'UCRT api-ms-win-crt-string',       MissingList);

    { ==== Python/SSL ==== }
    CheckFile(InternalDir + '\libcrypto-3-x64.dll',     'OpenSSL crypto (libcrypto-3-x64.dll)',    MissingList);
    CheckFile(InternalDir + '\libssl-3-x64.dll',        'OpenSSL ssl (libssl-3-x64.dll)',          MissingList);
    CheckFile(InternalDir + '\libffi-8.dll',            'libffi (libffi-8.dll)',                    MissingList);

    if MissingList <> '' then
    begin
      Msg := mtError;
      SuppressibleMsgBox(
        '安装后完整性检查失败！以下关键 DLL 缺失，将导致启动时报错：' + #13#10#13#10 +
        MissingList + #13#10#13#10 +
        '建议：' + #13#10 +
        '  1. 以管理员身份重新运行安装包' + #13#10 +
        '  2. 安装前先关闭杀毒软件（避免 DLL 被隔离）' + #13#10 +
        '  3. 或在目标电脑安装 VC++ 2015-2022 Redistributable x64：' + #13#10 +
        '     https://aka.ms/vs/17/release/vc_redist.x64.exe',
        Msg, mbOK, IDOK, 0);
    end
    else
    begin
      { 所有 DLL 都齐，仅在第一次安装时提示 }
      if not RegKeyExists(HKCU, 'Software\ImageTextReplacer\Installed') then
      begin
        RegWriteDWordValue(HKCU, 'Software\ImageTextReplacer\Installed', 'VersionOK', 1);
        SuppressibleMsgBox(
          '安装完成！关键 DLL 已全部就位。' + #13#10 +
          'Python 3.14 官方要求 Windows 10 1809+ 系统。' + #13#10#13#10 +
          '如果启动时仍提示「找不到指定的模块」，请先安装：' + #13#10 +
          '  Visual C++ 2015-2022 Redistributable (x64)' + #13#10 +
          '  下载: https://aka.ms/vs/17/release/vc_redist.x64.exe',
          mtInformation, mbOK, IDOK, 0);
      end;
    end;
  end;
end;
