[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildScript = Join-Path $PSScriptRoot "build-windows-installer.bat"
$executable = Join-Path $projectRoot "dist\Ledgerly\Ledgerly.exe"
$shortcutPath = Join-Path $projectRoot "dist\Ledgerly.lnk"

Push-Location $projectRoot
try {
    Write-Host "Building Ledgerly after commit..."
    & $buildScript
    if ($LASTEXITCODE -ne 0) {
        throw "Ledgerly build failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "The build completed without creating $executable."
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $executable
    $shortcut.WorkingDirectory = Split-Path -Parent $executable
    $shortcut.IconLocation = "$executable,0"
    $shortcut.Description = "Launch Ledgerly"
    $shortcut.Save()

    Write-Host "Ledgerly was rebuilt and dist\Ledgerly.lnk was updated."
} finally {
    Pop-Location
}
