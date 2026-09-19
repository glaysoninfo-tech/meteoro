<#
.SYNOPSIS
    Sobe a API do Eco-Gestao / Meteoro e o portal em http://127.0.0.1:8000/portal/

.DESCRIPTION
    Usa a .venv do projeto se existir; caso contrario, o Python do sistema
    (o mesmo que ja roda "uvicorn app.main:app" hoje). Nao instala nada e
    nao aplica migracoes por padrao.

.EXAMPLE
    .\start-portal.ps1
    .\start-portal.ps1 -Port 8001
    .\start-portal.ps1 -Migrate
    .\start-portal.ps1 -NoReload
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1",
    [switch]$Migrate,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$BackendDir  = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "    $Text" -ForegroundColor Green }
function Write-Note { param([string]$Text) Write-Host "    $Text" -ForegroundColor Yellow }

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments, [switch]$Quiet)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) { & $Exe @Arguments 2>&1 | Out-Null }
        else        { & $Exe @Arguments | Out-Host }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

if (-not (Test-Path $BackendDir))  { throw "Pasta 'backend' nao encontrada em $Root." }
if (-not (Test-Path $FrontendDir)) { Write-Note "Pasta 'frontend' nao encontrada; /portal nao sera servido." }

# ------------------------------------------------------------------ Python
Write-Step "Interpretador Python"

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $Py = $VenvPy
    Write-Ok "usando a .venv do projeto"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Py = (Get-Command python).Source
    Write-Ok "usando o Python do sistema: $Py"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Py = (Get-Command py).Source
    Write-Ok "usando o launcher py"
} else {
    throw "Python nao encontrado no PATH."
}

$check = & $Py -c "import fastapi, uvicorn; print('ok')" 2>&1
if ($check -notmatch "ok") {
    Write-Note "Este Python nao tem fastapi/uvicorn instalados."
    Write-Note "Instale com:  $Py -m pip install -r backend\requirements.txt"
    throw "Dependencias ausentes."
}
Write-Ok "fastapi e uvicorn disponiveis"

# -------------------------------------------------------------- Porta livre
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($inUse) {
        $owner = (Get-Process -Id $inUse[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
        throw "A porta $Port ja esta em uso pelo processo '$owner' (PID $($inUse[0].OwningProcess)). Feche aquela janela ou use -Port 8001."
    }
}

Push-Location $BackendDir
try {
    if ($Migrate) {
        Write-Step "Aplicando migracoes (alembic upgrade head)"
        $code = Invoke-Native -Exe $Py -Arguments @("-m", "alembic", "upgrade", "head")
        if ($code -ne 0) { throw "Falha nas migracoes." }
        Write-Ok "Schema atualizado."
    }

    $BaseUrl = "http://${BindHost}:${Port}"
    Write-Step "Subindo a API + portal"
    Write-Host ""
    Write-Host "    PORTAL ....... $BaseUrl/portal/"          -ForegroundColor White
    Write-Host "    API .......... $BaseUrl/api/v1"           -ForegroundColor White
    Write-Host "    Swagger UI ... $BaseUrl/docs"             -ForegroundColor White
    Write-Host "    Health ....... $BaseUrl/health"           -ForegroundColor White
    Write-Host "    Readiness .... $BaseUrl/health/ready"     -ForegroundColor White
    Write-Host ""
    Write-Note "O portal mostra o que ja foi coletado. Para coletar dado novo,"
    Write-Note "ligue tambem o Redis (docker start meteoro-redis) e o worker"
    Write-Note "(python -m app.modules.ingestion.worker) em outra janela."
    Write-Host ""
    Write-Host "    (Ctrl+C para parar)" -ForegroundColor DarkGray
    Write-Host ""

    $UvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$Port")
    if (-not $NoReload) { $UvicornArgs += "--reload" }

    $ErrorActionPreference = "Continue"
    & $Py @UvicornArgs
} finally {
    Pop-Location
}
