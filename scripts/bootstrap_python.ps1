[CmdletBinding()]
param(
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"

$pythonVersion = "3.11.9"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"
$lockFile = Join-Path $projectRoot "requirements.lock.txt"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install uv first: https://docs.astral.sh/uv/"
}

if (-not (Test-Path -LiteralPath $lockFile)) {
    throw "Missing dependency lock file: $lockFile"
}

$env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot ".python-runtime"

if ($Proxy) {
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
}

Push-Location $projectRoot
try {
    uv python install --no-registry $pythonVersion

    $installedVersion = $null
    if (Test-Path -LiteralPath $pythonPath) {
        $installedVersion = & $pythonPath -c "import platform; print(platform.python_version())" 2>$null
        if ($LASTEXITCODE -ne 0) {
            $installedVersion = $null
        }
    }

    if ($installedVersion -ne $pythonVersion) {
        uv venv --clear $venvPath --python $pythonVersion
    }

    uv pip sync $lockFile --python $pythonPath
    uv pip check --python $pythonPath
    & $pythonPath --version
}
finally {
    Pop-Location
}
