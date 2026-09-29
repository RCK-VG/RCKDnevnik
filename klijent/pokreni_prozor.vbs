' Pokrece prozor za prijavu (prozor.ps1) bez treptanja crnog prozora.
' Poziva ga zadatak "RCK Nadzor prozor" pri prijavi ucenickog racuna.
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "\prozor.ps1""", 0, False
