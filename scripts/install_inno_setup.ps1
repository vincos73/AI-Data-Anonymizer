[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$InnoVersion = "6.7.3"
$ExpectedSha256 = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
$DownloadUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
$CompilerPath = Join-Path $InstallDir "ISCC.exe"

if (Test-Path $CompilerPath) {
    Write-Host "Inno Setup $InnoVersion è già disponibile in $InstallDir"
    exit 0
}

$DownloadDir = Join-Path $env:TEMP "omissis-inno-setup"
$InstallerPath = Join-Path $DownloadDir "innosetup-$InnoVersion.exe"
New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

try {
    Write-Host "Scarico Inno Setup $InnoVersion dalla release ufficiale..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath

    $ActualSha256 = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Hash SHA-256 inatteso per Inno Setup: $ActualSha256"
    }

    Write-Host "Hash verificato. Installo Inno Setup in $InstallDir"
    $InstallProcess = Start-Process `
        -FilePath $InstallerPath `
        -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=`"$InstallDir`"" `
        -Wait `
        -PassThru
    if ($InstallProcess.ExitCode -ne 0) {
        throw "Installazione di Inno Setup non riuscita ($($InstallProcess.ExitCode))."
    }

    if (-not (Test-Path $CompilerPath)) {
        throw "ISCC.exe non è stato trovato dopo l'installazione."
    }
}
finally {
    if (Test-Path $InstallerPath) {
        Remove-Item -Path $InstallerPath -Force
    }
}

Write-Host "Inno Setup pronto: $CompilerPath"
