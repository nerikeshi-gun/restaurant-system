@echo off
setlocal
fltmc >nul 2>&1
if errorlevel 1 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="Greit Restaurant HTTPS 8443 LAN" >nul 2>&1
netsh advfirewall firewall add rule name="Greit Restaurant HTTPS 8443 LAN" dir=in action=allow protocol=TCP localport=8443 localip=192.168.137.1 remoteip=192.168.137.0/24 profile=any

if errorlevel 1 (
  echo Failed to add the firewall rule.
) else (
  echo Tablet access rule added for TCP 8443 on the local subnet.
)
pause
endlocal
