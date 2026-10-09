; HaruMimi 설치 마법사 (Inno Setup 6). 빌드: build.bat  (ISCC /DAppVersion=... /DAppVersionNum=... installer\HaruMimi.iss)
#define AppName "HaruMimi"
#ifndef AppVersion
  #define AppVersion "1.0.0-beta.1"
#endif
#ifndef AppVersionNum
  #define AppVersionNum "1.0.0.0"
#endif
#define AppPublisher "RabbitHaru"
#define AppURL "https://github.com/RabbitHaru/HaruMimi"
#define AppExe "HaruMimi.exe"

[Setup]
; AppId 는 앱을 식별하는 고유 값입니다. 절대 바꾸지 마세요 (바꾸면 업데이트가 아니라 별도 설치로 인식됨).
AppId={{6B0F3A52-9D47-4E1C-8A63-2F7C51D9B0E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersionNum}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
; 관리자 권한 없이 내 계정에 설치 (원하면 설치 중에 '모든 사용자'를 고를 수 있음)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=HaruMimi.ico
DisableWelcomePage=no
; 둥근 보라색 카드 이미지(밝은/어두운 테마, 배율별) + Windows 11 스타일(둥근 버튼/입력창)
WizardStyle=modern dynamic windows11 excludelightbuttons
WizardImageFile=wiz_side_light_100.bmp,wiz_side_light_125.bmp,wiz_side_light_150.bmp,wiz_side_light_200.bmp
WizardImageFileDynamicDark=wiz_side_dark_100.bmp,wiz_side_dark_125.bmp,wiz_side_dark_150.bmp,wiz_side_dark_200.bmp
WizardSmallImageFile=wiz_small_light_100.bmp,wiz_small_light_125.bmp,wiz_small_light_150.bmp,wiz_small_light_200.bmp
WizardSmallImageFileDynamicDark=wiz_small_dark_100.bmp,wiz_small_dark_125.bmp,wiz_small_dark_150.bmp,wiz_small_dark_200.bmp
OutputDir=..\dist
OutputBaseFilename=HaruMimi-Setup-v{#AppVersion}-win64
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
; 실행 중이면 닫고 업데이트 (설정은 %APPDATA%\RabbitHaru 에 있어서 그대로 유지됨)
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"; InfoBeforeFile: "info.ko.txt"
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "info.en.txt"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"; InfoBeforeFile: "info.ja.txt"

[CustomMessages]
english.DeleteUserData=Also delete your HaruMimi settings and downloaded models stored in your user folder?%n%nChoose No to keep them for a future reinstall.
korean.DeleteUserData=내 PC에 저장된 HaruMimi 설정과 다운로드한 모델도 함께 삭제할까요?%n%n"아니오"를 누르면 나중에 다시 설치할 때 쓸 수 있도록 남겨 둬요.
japanese.DeleteUserData=ユーザーフォルダに保存されているHaruMimiの設定とダウンロードしたモデルも一緒に削除しますか?%n%n「いいえ」を選ぶと、再インストール時に使えるよう残します。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\HaruMimi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; 앱 안의 '업데이트'가 조용히(/SILENT /LAUNCH=1) 설치할 때는 끝난 뒤 앱을 다시 시작
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: LaunchAfterSilent

[Code]
function LaunchAfterSilent: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:LAUNCH|0}') = '1');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\RabbitHaru');
    if DirExists(DataDir) then
      if MsgBox(CustomMessage('DeleteUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
