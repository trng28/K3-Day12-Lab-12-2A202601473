@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_research_chat.ps1" %*
exit /b %ERRORLEVEL%
