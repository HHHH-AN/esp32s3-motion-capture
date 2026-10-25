param(
    [string[]]$Nodes = @('A=192.168.4.1:9000', 'B=192.168.4.201:9000'),
    [ValidateRange(1,65535)][int]$Port = 8010
)
$ErrorActionPreference = 'Stop'
$hostRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'host'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$runtime = Get-HostPython -HostRoot $hostRoot
$launchArgs = @($runtime.Prefix) + @('-B', '-X', 'utf8', 'run_wifi_monitor.py', '--port', "$Port")
foreach ($endpoint in $Nodes) { $launchArgs += @('--node', $endpoint) }
Push-Location -LiteralPath $hostRoot
try {
    & $runtime.File @launchArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Wi-Fi monitor stopped with an error. Inspect the message above; if the web port is occupied, choose another -Port.'
    }
}
finally { Pop-Location }
