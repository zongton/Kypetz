Set ws = CreateObject("Wscript.Shell")
ws.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
If CreateObject("Scripting.FileSystemObject").FileExists("E:\AI\venv\Scripts\pythonw.exe") Then
    ws.Run """E:\AI\venv\Scripts\pythonw.exe"" main.py", 0, False
Else
    ws.Run "pythonw main.py", 0, False
End If
