param([string]$Python = 'python', [string]$VenvPath = '.venv', [switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path 'runtime' | Out-Null

function Assert-Success([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

foreach ($port in @(8000, 3000)) {
    $probe = [Net.Sockets.TcpClient]::new()
    try {
        $probe.Connect('127.0.0.1', $port)
        throw "Port $port is already in use. Stop the existing service before starting this app."
    } catch [Net.Sockets.SocketException] {
        # No listener: this port is available.
    } finally {
        $probe.Dispose()
    }
}
$venvPython = Join-Path $VenvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($SkipInstall) { throw 'SkipInstall requires an existing virtual environment.' }
    & $Python -m venv $VenvPath
    Assert-Success 'Virtual environment setup'
}
$runtimePython = (Resolve-Path $venvPython).Path
if (-not $SkipInstall) {
    & $runtimePython -m pip install -r requirements.lock
    Assert-Success 'Python dependencies'
    Push-Location 'apps\web'
    try {
        npm.cmd ci --no-fund --no-audit
        Assert-Success 'Web dependencies'
        npm.cmd run build
        Assert-Success 'Web production build'
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath 'apps\web\.next\BUILD_ID')) { throw 'Build the web application before using SkipInstall.' }
& $runtimePython -m scripts.initialize
Assert-Success 'Database initialization'
$started = @()
try {
    $apiProcess = Start-Process -FilePath $runtimePython -ArgumentList '-m','uvicorn','services.api.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'runtime\api.log' -RedirectStandardError 'runtime\api-error.log'
    $started += $apiProcess
    $webRoot = Join-Path $projectRoot 'apps\web'
    $webProcess = Start-Process -FilePath 'node' -ArgumentList 'node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3000' -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'runtime\web.log') -RedirectStandardError (Join-Path $projectRoot 'runtime\web-error.log')
    $started += $webProcess
    foreach ($url in @('http://127.0.0.1:8000/ready', 'http://127.0.0.1:3000')) {
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            foreach ($process in $started) {
                if ($process.HasExited) { throw 'A local service exited. Check runtime/*-error.log.' }
            }
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
                if ($response.StatusCode -eq 200) { $ready = $true; break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw "Service readiness failed for $url. Check runtime logs." }
    }
    @($started | ForEach-Object { @{ id = $_.Id; startedTicks = $_.StartTime.ToUniversalTime().Ticks.ToString() } }) |
        ConvertTo-Json | Set-Content -LiteralPath 'runtime\local-processes.json'
    Write-Host 'Local app is ready at http://127.0.0.1:3000. Logs are in runtime/.'
} catch {
    foreach ($process in $started) {
        if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
    throw
}
