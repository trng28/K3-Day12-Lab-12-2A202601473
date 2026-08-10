@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_research_workflow.ps1" %*
exit /b %ERRORLEVEL%
