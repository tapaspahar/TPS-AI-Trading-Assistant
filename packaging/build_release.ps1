$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Version = "1.4"
$AppFolder = "TPS AI Trading Assistant"
$ReleaseDir = Join-Path $ProjectRoot "release"
$SetupPath = Join-Path $ReleaseDir "TPS-AI-Trading-Assistant-Setup-$Version.exe"
$PortablePath = Join-Path $ReleaseDir "TPS-AI-Trading-Assistant-Portable-$Version.zip"
$ChecksumPath = Join-Path $ReleaseDir "SHA256SUMS-$Version.txt"

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

if (Test-Path -LiteralPath $PortablePath) { Remove-Item -LiteralPath $PortablePath -Force }
$Tar = Get-Command "tar.exe" -ErrorAction SilentlyContinue
if ($Tar) {
    & $Tar.Source -a -cf $PortablePath -C (Join-Path $ProjectRoot "dist") $AppFolder
    if ($LASTEXITCODE -ne 0) { throw "Portable ZIP build failed." }
} else {
    Compress-Archive -Path (Join-Path $ProjectRoot "dist\$AppFolder\*") -DestinationPath $PortablePath -CompressionLevel Optimal
}

$Hashes = Get-FileHash -LiteralPath $SetupPath, $PortablePath -Algorithm SHA256
$Hashes | ForEach-Object { "{0}  {1}" -f $_.Hash.ToLowerInvariant(), (Split-Path $_.Path -Leaf) } |
    Set-Content -LiteralPath $ChecksumPath -Encoding ascii
$Hashes | Format-Table Algorithm, Hash, Path -AutoSize
Write-Host "Release files created in $ReleaseDir"
