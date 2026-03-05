<#
.SYNOPSIS
    Launch the vault-mcp server on startup

.EXAMPLE
    .\bridge-inject.ps1 "run the daily review"
#>

$ScriptDir  = $PSScriptRoot
$ServerPy   = Join-Path (Join-Path $ScriptDir "src") "server.py"

Start-Process -FilePath "python.exe" -ArgumentList "`"$ServerPy`"" -WorkingDirectory $ScriptDir -WindowStyle Hidden
