@echo off
REM Glossary Suggester - Windows launcher (double-click or run from cmd).
REM Forwards any args to run.ps1, e.g.:  run.bat -Port 8080
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
