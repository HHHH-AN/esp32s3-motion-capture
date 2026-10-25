param(
    [ValidateSet('rigid_check','upper_limb','lower_limb','bilateral')][string]$Preset = 'upper_limb',
    [ValidateSet('Demo','Live')][string]$Mode = 'Demo',
    [ValidateRange(8,120)][double]$Duration = 20,
    [string]$Endpoints = 'presets/endpoints.local.json'
)
$ErrorActionPreference = 'Stop'
$hostRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'host'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$runtime = Get-HostPython -HostRoot $hostRoot
$durationText = $Duration.ToString([Globalization.CultureInfo]::InvariantCulture)
$launchArgs = @($runtime.Prefix) + @('-B', '-X', 'utf8', 'run_motion_presets.py', '--preset', $Preset, '--duration', $durationText)
if ($Mode -eq 'Live') { $launchArgs += @('--live', '--endpoints', $Endpoints) }
else { $launchArgs += '--demo' }
Push-Location -LiteralPath $hostRoot
try {
    & $runtime.File @launchArgs
    if ($LASTEXITCODE -ne 0) { throw 'Experiment stopped. Inspect the message above and any partial host/preset_runs/*/raw.csv.' }
}
finally { Pop-Location }
