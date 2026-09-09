param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$workbenchRoot = Split-Path -Parent $PSScriptRoot
$workbenchPython = Join-Path $workbenchRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $workbenchPython)) {
    throw '请先按 Product KB README 安装 .venv，再启动工作台。'
}
& $workbenchPython (Join-Path $PSScriptRoot 'app.py') --port $Port
