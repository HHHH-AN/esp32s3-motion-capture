[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BodySlot,
    [string]$Port,
    [string]$Environment = "esp32-s3-devkitm-1",
    [string]$ProjectDirectory = (Join-Path $PSScriptRoot "..\firmware"),
    [string]$PlatformIO = (Join-Path $env:USERPROFILE ".platformio\penv\Scripts\platformio.exe"),
    [string]$LegacyAliasVersion,
    [switch]$Upload,
    [switch]$DryRun,
    [switch]$ReplaceExistingConfiguration
)
$ErrorActionPreference = "Stop"
if ($Upload -and [string]::IsNullOrWhiteSpace($Port)) {
    throw "-Upload requires -Port with the port confirmed for the current physical board."
}
$taskFirmware = (Resolve-Path -LiteralPath $ProjectDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $taskFirmware "platformio.ini"))) {
    throw "ProjectDirectory must be the firmware project containing platformio.ini."
}
$taskPython = Join-Path $PSScriptRoot "..\host\.venv\Scripts\python.exe"
$taskPythonArgs = @()
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPython = "py"
    $taskPythonArgs = @("-3")
}
$taskConfigArgs = @((Join-Path $PSScriptRoot "configure_node.py"), "--body-slot", $BodySlot,
                    "--firmware-dir", $taskFirmware)
if ($LegacyAliasVersion) { $taskConfigArgs += @("--legacy-alias-version", $LegacyAliasVersion) }
if ($DryRun) { $taskConfigArgs += "--dry-run" }
if ($ReplaceExistingConfiguration) { $taskConfigArgs += "--replace-existing" }
$taskConfigOutput = & $taskPython @taskPythonArgs @taskConfigArgs
if ($LASTEXITCODE -ne 0) { throw "Node configuration failed; no PlatformIO command was run." }
$taskConfiguration = ($taskConfigOutput -join "`n") | ConvertFrom-Json
$taskConfigOutput | Write-Output
$taskPioArgs = @("run", "--project-dir", $taskFirmware, "--environment", $Environment)
$taskCleanArgs = $taskPioArgs + @("--target", "clean")
if ($Upload) { $taskPioArgs += @("--target", "upload", "--upload-port", $Port) }
Write-Host "Body role: $BodySlot; environment: $Environment; upload: $Upload"
Write-Host "Device identity will still be derived from the board MAC. Network configuration is preserved."
if ($DryRun) {
    if ($taskConfiguration.changed) {
        Write-Host ("Dry run (changed role/config): " + $PlatformIO + " " + ($taskCleanArgs -join " "))
    }
    Write-Host ("Dry run: " + $PlatformIO + " " + ($taskPioArgs -join " "))
    return
}
if (-not (Test-Path -LiteralPath $PlatformIO)) { throw "PlatformIO executable not found: $PlatformIO" }
if ($taskConfiguration.changed) {
    # Includes are ordinary compiler dependencies. Cleaning just the selected
    # environment also covers the first switch from the optional fallback header.
    & $PlatformIO @taskCleanArgs
    if ($LASTEXITCODE -ne 0) { throw "PlatformIO environment clean failed with exit code $LASTEXITCODE" }
}
& $PlatformIO @taskPioArgs
if ($LASTEXITCODE -ne 0) { throw "PlatformIO failed with exit code $LASTEXITCODE" }
