@echo off
curl --silent --output NUL --max-time 2 http://127.0.0.1:9400/mcp
if %ERRORLEVEL%==7 (
    start "" C:\Users\ghoop\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe "C:\Users\ghoop\Desktop\claudecode\my-vault\vault-mcp\src\server.py"
)
