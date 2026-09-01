$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Version = "1.5.2"
$AppFolder = "TPS AI Trading Assistant"
$ReleaseDir = Join-Path $ProjectRoot "release"
$SetupPath = Join-Path $ReleaseDir "TPS-AI-Trading-Assistant-Setup-$Version.exe"
$PortablePath = Join-Path $ReleaseDir "TPS-AI-Trading-Assistant-Portable-$Version.zip"
$ChecksumPath = Join-Path $ReleaseDir "SHA256SUMS-$Version.txt"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$TestPython = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
$BuildPython = "python"

# Stamp release metadata from the computer's actual local clock immediately
# before validation/build. The footer is build time, not a live application clock.
$BuildNow = Get-Date
$UpdatedAt = $BuildNow.ToString("dd-MM-yyyy HH:mm:ss") + " IST"
$FooterTime = $BuildNow.ToString("dd-MM-yyyy HH:mm") + " IST"
$ReleaseInfoPath = Join-Path $ProjectRoot "release_info.py"
$ReleaseInfo = Get-Content -LiteralPath $ReleaseInfoPath -Raw
$ReleaseInfo = [regex]::Replace($ReleaseInfo, '(?m)^LAST_UPDATED_AT = .+$', 'LAST_UPDATED_AT = "' + $UpdatedAt + '"')
$ReleaseInfo = [regex]::Replace($ReleaseInfo, '(?m)^FOOTER_UPDATE_TEXT = .+$', 'FOOTER_UPDATE_TEXT = "Software Build v' + $Version + ' - ' + $FooterTime + '"')
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ReleaseInfoPath, ($ReleaseInfo.TrimEnd() + [Environment]::NewLine), $Utf8NoBom)
Write-Host "Release metadata stamped at $UpdatedAt"

& $TestPython -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

& $BuildPython -m PyInstaller --noconfirm --clean --windowed --onedir `
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
