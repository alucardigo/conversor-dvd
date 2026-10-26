; Instalador do Conversor de DVD (Inno Setup 6). Compilado por packaging\build.ps1,
; que passa a versão em /DVersao=... e copia o ffmpeg para dist\ConversorDVD\ffmpeg\bin.
; Instala só para o usuário atual: não pede administrador.

#ifndef Versao
  #define Versao "1.0.0"
#endif

[Setup]
AppId={{B7E2C0A1-5D3F-4E8B-9A61-CD0F2D4E7A10}
AppName=Conversor de DVD
AppVersion={#Versao}
AppPublisher=alucardigo
AppPublisherURL=https://github.com/alucardigo/conversor-dvd
DefaultDirName={autopf}\ConversorDVD
DefaultGroupName=Conversor de DVD
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer\out
OutputBaseFilename=ConversorDVD-Setup-{#Versao}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ConversorDVD.exe
SetupIconFile=icone.ico
LicenseFile=..\LICENSE

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho_area"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\ConversorDVD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Conversor de DVD"; Filename: "{app}\ConversorDVD.exe"
Name: "{group}\Desinstalar Conversor de DVD"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Conversor de DVD"; Filename: "{app}\ConversorDVD.exe"; Tasks: atalho_area

[Run]
Filename: "{app}\ConversorDVD.exe"; Description: "Abrir o Conversor de DVD"; Flags: nowait postinstall skipifsilent
