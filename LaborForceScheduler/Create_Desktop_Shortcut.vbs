
Set WshShell = CreateObject("WScript.Shell")
DesktopPath = WshShell.SpecialFolders("Desktop")
Set oShellLink = WshShell.CreateShortcut(DesktopPath & "\LaborForceScheduler.lnk")
oShellLink.TargetPath = WScript.ScriptFullName
' Point shortcut to Run_Scheduler.bat
oShellLink.TargetPath = Replace(WScript.ScriptFullName, "Create_Desktop_Shortcut.vbs", "Run_Scheduler.bat")
oShellLink.WorkingDirectory = Replace(WScript.ScriptFullName, "Create_Desktop_Shortcut.vbs", "")
oShellLink.IconLocation = Replace(WScript.ScriptFullName, "Create_Desktop_Shortcut.vbs", "assets\scheduler.ico")
oShellLink.Description = "LaborForceScheduler"
oShellLink.Save
WScript.Echo "Desktop shortcut created: LaborForceScheduler"
