# Shared Python selection for the checked-in host launchers.
function Get-HostPython {
    param([Parameter(Mandatory = $true)][string]$HostRoot)

    $venvPython = Join-Path $HostRoot '.venv\Scripts\python.exe'
    $candidates = @()
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $candidates += [pscustomobject]@{ File = $venvPython; Prefix = @() }
    }
    else {
        foreach ($name in @('python', 'py')) {
            $application = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -eq $application) { continue }
            if ($application.Source -match '\\WindowsApps\\python(?:3(?:\.\d+)?)?\.exe$') { continue }
            $prefix = @()
            if ($name -eq 'py') { $prefix = @('-3') }
            $candidates += [pscustomobject]@{ File = $application.Source; Prefix = $prefix }
        }
    }

    foreach ($candidate in $candidates) {
        try {
            $versionOutput = & $candidate.File @($candidate.Prefix) -I -c 'import sys; print(sys.version.split()[0])' 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]([string]$versionOutput) -ge [version]'3.10') {
                return $candidate
            }
        }
        catch { }
    }

    throw 'Python 3.10 or newer is required. Install a supported Python and enable its PATH/py launcher, or recreate host/.venv with that interpreter. The WindowsApps Python placeholder is skipped.'
}
