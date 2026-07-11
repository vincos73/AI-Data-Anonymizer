Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir

function Test-CompatiblePython {
    param([string]$Command, [string[]]$Arguments = @())
    try {
        & $Command @Arguments -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$PythonCommand = $null
$PythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($minor in @("13", "12", "11", "10")) {
        if (Test-CompatiblePython -Command "py" -Arguments @("-3.$minor")) {
            $PythonCommand = "py"
            $PythonArgs = @("-3.$minor")
            break
        }
    }
}

if (-not $PythonCommand) {
    foreach ($candidate in @("python3.13", "python3.12", "python3.11", "python3.10", "python")) {
        if ((Get-Command $candidate -ErrorAction SilentlyContinue) -and (Test-CompatiblePython -Command $candidate)) {
            $PythonCommand = $candidate
            break
        }
    }
}

if (-not $PythonCommand) {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($UvCommand) {
        uv python install 3.12
        $PythonCommand = (uv python find 3.12)
    }
    else {
        Write-Host "Serve Python 3.10, 3.11, 3.12 o 3.13 per la build (PySide6 e PyInstaller non supportano ancora versioni piu recenti come 3.14), ma non e stato trovato nessun interprete compatibile e uv non e installato."
        Write-Host ""
        Write-Host "Per risolvere:"
        Write-Host ""
        Write-Host "  1. Installa uv (non tocca il Python di sistema):"
        Write-Host "     powershell -ExecutionPolicy Bypass -Command `"irm https://astral.sh/uv/install.ps1 | iex`""
        Write-Host ""
        Write-Host "  2. Riapri il terminale PowerShell in modo che il comando uv sia disponibile nel PATH."
        Write-Host ""
        Write-Host "  3. Rilancia questo script:"
        Write-Host "     .\scripts\build_windows_app.ps1"
        Write-Host ""
        Write-Host "     Lo script usera automaticamente uv per installare Python 3.12 in locale"
        Write-Host "     e creare l'ambiente virtuale della build, senza modificare o sostituire"
        Write-Host "     il Python gia presente sul sistema."
        exit 1
    }
}

if (-not (Test-Path ".venv")) {
    if ($PythonArgs.Count -gt 0) {
        & $PythonCommand @PythonArgs -m venv .venv
    }
    else {
        & $PythonCommand -m venv .venv
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
    --name "OMISSIS" `
    --windowed `
    --clean `
    --icon assets\app_icon.ico `
    --collect-data privacy_guardian `
    --collect-all docx `
    --collect-all pypdf `
    --collect-all pypdfium2 `
    --collect-all reportlab `
    --collect-all cryptography `
    src\privacy_guardian\app.py

Compress-Archive `
    -Path "dist\OMISSIS" `
    -DestinationPath "dist\OMISSIS-Windows.zip" `
    -Force

Write-Host "Build completata in: $ProjectDir\dist"
