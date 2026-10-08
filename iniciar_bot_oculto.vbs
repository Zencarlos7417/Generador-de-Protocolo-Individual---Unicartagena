Set WshShell = CreateObject("WScript.Shell")
' Arranca el bot de Telegram en segundo plano, sin ventana alguna.
' pythonw.exe no abre consola, así que no hay PowerShell que cerrar.
WshShell.Run """C:\Users\User\Downloads\protocolo-app\venv\Scripts\pythonw.exe"" ""C:\Users\User\Downloads\protocolo-app\bot_telegram.py""", 0, False
