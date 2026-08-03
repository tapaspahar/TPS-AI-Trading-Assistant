$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name "TPS AI Trading Assistant" `
    --version-file "packaging\windows_version_info.txt" `
    --collect-all matplotlib `
    --collect-all keyring `
    --hidden-import keyring.backends.Windows `
    "main.py"
if ($LASTEXITCODE -ne 0) { throw "Application build failed." }

$CompilerCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Compiler) { throw "Inno Setup 6 is required to build the installer." }

& $Compiler "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

Get-FileHash "release\TPS-AI-Trading-Assistant-Setup-1.0.0.exe" -Algorithm SHA256
