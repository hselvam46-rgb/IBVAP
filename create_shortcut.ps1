$desktop = [Environment]::GetFolderPath('Desktop')
$wsh = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path $desktop "IBVAP Tactical Console.lnk"
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -WindowStyle Hidden -File ""d:\IBVAP\open_console.ps1"""
$shortcut.WorkingDirectory = "d:\IBVAP"
$shortcut.Description = "Launch IBVAP Tactical C4I Console Website"
$shortcut.Save()
Write-Host "Desktop shortcut created at: $shortcutPath"
