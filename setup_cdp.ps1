# Browser Omnibox – CDP Setup
# Adds --remote-debugging-port=9222 to your Chrome desktop shortcut.
# Run once as a regular user (no admin required for user shortcuts).

param(
    [int]$Port = 9222,
    [string]$Browser = "Chrome"
)

$shortcuts = @(
    "$env:USERPROFILE\Desktop\Google Chrome.lnk",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk"
)

$flag = "--remote-debugging-port=$Port"

$patched = 0
foreach ($path in $shortcuts) {
    if (-not (Test-Path $path)) { continue }

    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($path)

    if ($lnk.Arguments -like "*$flag*") {
        Write-Host "Already patched: $path"
        $patched++
        continue
    }

    $lnk.Arguments = ($lnk.Arguments + " $flag").Trim()
    $lnk.Save()
    Write-Host "Patched: $path"
    $patched++
}

if ($patched -eq 0) {
    Write-Host ""
    Write-Host "No Chrome shortcuts found at the default locations." -ForegroundColor Yellow
    Write-Host "Add the following flag manually to your Chrome shortcut's Target field:" -ForegroundColor Yellow
    Write-Host "  $flag" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Done! Restart Chrome fully (close all windows) for the change to take effect." -ForegroundColor Green
    Write-Host "Then set Tab Switching Mode to 'CDP' in Flow Launcher plugin settings." -ForegroundColor Green
}
