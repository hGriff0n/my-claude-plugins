Populate with spec for the startup.bat script to auto run on login

What schtasks settings are

Add check for server already running
- `curl http://127.0.0.1:9400/mcp` and then check the return error
	- If it's complaining about "Unable to connect", then the server isn't running, otherwise it is