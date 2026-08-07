; Inno Setup script for the Michigan SPC Zone Converter.
;
; Compiled by tools/build_release.py, which passes the version and the paths in
; rather than letting this file guess at them:
;
;   ISCC.exe /DAppVersion=0.1.0 /DSourceDir=<repo>\dist\mcx ^
;            /DOutputDir=<repo>\dist\installer installer\michspc.iss
;
; Compiling it by hand works too and is useful for checking a change, but a
; build that skipped a gate is not a release (docs/method/METHOD.md section 6).
;
; TWO THINGS IN HERE MUST NEVER CHANGE.
;
; 1. AppId. It is the identity Windows files this program under, and it is what
;    lets an upgrade replace an installation instead of standing a second one
;    beside it. It was generated once, on 2026-08-06, and is frozen as a literal
;    below (docs/method/TOOLING.md). A new GUID in a later release would leave
;    every earlier installation orphaned in Add/Remove Programs.
;
; 2. Root: HKA on any registry work. This installer offers both a per-user and
;    an administrative install (PrivilegesRequiredOverridesAllowed), and HKA
;    resolves to HKLM or HKCU to match whichever one is running. A hardcoded
;    HKLM write fails outright in a per-user install; a hardcoded HKCU write in
;    an administrative install lands in the installing administrator's hive and
;    is invisible to the user who actually runs the program.
;
; There are no file associations today. The program takes its input through a
; file dialog, and a PNEZD file is a .txt or .csv that belongs to the user's
; editor and CAD package, not to this tool. If one is ever added, the command
; must quote its argument - "%1", never bare %1, or every path with a space in
; it arrives split.

#ifndef AppVersion
  #error AppVersion must be passed in: ISCC /DAppVersion=x.y.z
#endif

#ifndef SourceDir
  #error SourceDir must be passed in: the PyInstaller one-folder bundle
#endif

#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "MCX"
#define AppPublisher "DMARTIN"
#define ExeName "mcx.exe"

[Setup]
AppId={{9D0F57AB-4394-41F2-8164-D40015E7A8B4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

DefaultDirName={autopf}\MCX
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#ExeName}

; Per-user by default, administrative if the user asks for it. autopf, autopf64
; and HKA all follow this choice.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir={#OutputDir}
OutputBaseFilename=mcx-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; The bundle carries a 4.7 MB geoid grid and the whole of Qt; refusing to
; install rather than half-installing is the same rule the exporter follows.
DiskSpanning=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
; The product was renamed to MCX at 0.2.0. The AppId is deliberately unchanged,
; so Windows treats this as an upgrade of the same product rather than a second
; entry in Installed apps - which means an existing install is reused, old exe
; and all. These entries remove what the old name left behind. Harmless on a
; clean machine, where there is nothing to delete.
Type: files; Name: "{app}\michspc-spc-converter.exe"
Type: files; Name: "{autoprograms}\Michigan SPC Zone Converter.lnk"
Type: files; Name: "{autodesktop}\Michigan SPC Zone Converter.lnk"

[Files]
; The whole PyInstaller one-folder bundle, including _internal\data\ (the
; GEOID18 and GEOID12B tiles and the VERTCON 3.0 transformation and error
; grids) and _internal\assets\icon\coord-convert.ico. recursesubdirs
; and createallsubdirs together keep the bundle's layout exactly as the frozen
; program expects to find it - the program locates its grid relative to the
; executable, so a flattened install would break every elevation factor.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#ExeName}"; IconFilename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; IconFilename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Open {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller leaves nothing behind, but a run of the program may have written
; __pycache__ directories inside the install folder. Remove the folder itself so
; an uninstall leaves no orphaned directory in Program Files.
Type: filesandordirs; Name: "{app}"
