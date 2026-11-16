$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$processFile = Join-Path $projectRoot 'runtime\local-processes.json'
if (Test-Path -LiteralPath $processFile) {
    $owned = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($record in $owned) {
        $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
        if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq [long]$record.startedTicks) {
            # The Windows virtual-environment launcher can own a Python child.
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not stop owned process tree $($process.Id)" }
        }
    }
    Remove-Item -LiteralPath $processFile
}
