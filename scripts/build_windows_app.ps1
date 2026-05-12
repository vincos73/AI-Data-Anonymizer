Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir

if (-not (Test-Path ".venv")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
    }
    else {
        python -m venv .venv
    }
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[windows-build]"

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

& .\.venv\Scripts\python.exe scripts\create_app_icon.py

& .\.venv\Scripts\pyinstaller.exe `
    --name "AI Data Anonymizer" `
    --windowed `
    --clean `
    --icon assets\app_icon.ico `
    --collect-all docx `
    --collect-all pypdf `
    --collect-all reportlab `
    src\privacy_guardian\app.py

Compress-Archive `
    -Path "dist\AI Data Anonymizer" `
    -DestinationPath "dist\AI-Data-Anonymizer-Windows.zip" `
    -Force

Write-Host "Build completata in: $ProjectDir\dist"
