<#
 One-command demo launcher.   .\start-demo.ps1            (start API + Workbench, reset data)
                              .\start-demo.ps1 -Stop      (stop both)
#>
param([switch]$Stop, [switch]$KeepData)
$root = $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

function Stop-Demo {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn clearview|next dev|next-server|next\\dist' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Stop-Demo
if ($Stop) { "Demo stopped."; return }

Push-Location "$root\backend"
if (-not $KeepData) { python -m clearview.seed --reset } else { python -m clearview.seed }
Start-Process python -ArgumentList '-m','uvicorn','clearview.api:app','--port','8000' -WindowStyle Hidden -RedirectStandardError "$env:TEMP\clearview-api.err.log" -RedirectStandardOutput "$env:TEMP\clearview-api.out.log"
Pop-Location

Push-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm.cmd install --no-audit --no-fund }
Start-Process npm.cmd -ArgumentList 'run','dev' -WindowStyle Hidden -RedirectStandardError "$env:TEMP\clearview-fe.err.log" -RedirectStandardOutput "$env:TEMP\clearview-fe.out.log"
Pop-Location

foreach ($u in 'http://127.0.0.1:8000/api/health','http://localhost:3000') {
  $ok = $false
  for ($i = 0; $i -lt 40 -and -not $ok; $i++) {
    try { Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 3 | Out-Null; $ok = $true } catch { Start-Sleep 1 }
  }
  "{0,-40} {1}" -f $u, $(if ($ok) { 'UP' } else { 'FAILED - see logs in ' + $env:TEMP })
}
"`nWorkbench: http://localhost:3000   API docs: http://127.0.0.1:8000/docs   Stop: .\start-demo.ps1 -Stop"
