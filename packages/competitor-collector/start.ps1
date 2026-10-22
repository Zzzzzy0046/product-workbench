param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskVenvPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskVenvPython)) {
    $taskCandidates = @((Join-Path (Split-Path (Split-Path $taskRoot -Parent) -Parent) '.venv\Scripts\python.exe'))
    $taskPythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($taskPythonCommand) { $taskCandidates += $taskPythonCommand.Source }
    $taskBasePython = $taskCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (!$taskBasePython) { throw 'Install Python 3.11-3.13, then run this launcher again.' }
    Write-Host 'Creating an isolated Python environment...'
    & $taskBasePython -m venv (Join-Path $taskRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $taskVenvPython -X utf8 -c 'import google_play_scraper, requests, PIL, deep_translator'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing collector dependencies into its own .venv...'
    & $taskVenvPython -m pip install -e ($taskRoot + '[translation]')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }
}
Push-Location -LiteralPath $taskRoot
try {
    & $taskVenvPython -X utf8 -c 'from pathlib import Path; from competitor_collector.auth import AuthStore; import sys; sys.exit(0 if AuthStore(Path(''data'')/''auth.sqlite3'').has_users() else 2)'
    if ($LASTEXITCODE -eq 2) {
        Write-Host 'First use: create your administrator. There is no default password.'
        & $taskVenvPython -X utf8 -m competitor_collector init-admin
        if ($LASTEXITCODE -ne 0) { throw 'Administrator setup was not completed.' }
    } elseif ($LASTEXITCODE -ne 0) { throw 'Could not check account configuration.' }
    $taskUrl = 'http://127.0.0.1:' + $Port + '/'
    $taskHealth = $null
    try { $taskHealth = Invoke-RestMethod -Uri ($taskUrl + 'health') -TimeoutSec 2 } catch { }
    if ($taskHealth -and $taskHealth.service -eq 'competitor-collector') {
        Write-Host 'The collector is already running. Opening its page...'
        Start-Process -FilePath $taskUrl
    } else {
        & $taskVenvPython -X utf8 -m competitor_collector serve --port $Port --open
    }
} finally { Pop-Location }
