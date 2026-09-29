' Pokrece nadzor.ps1 bez treptanja crnog prozora (poziva ga zadatak "RCK Nadzor" pri prijavi).
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "\nadzor.ps1""", 0, False
