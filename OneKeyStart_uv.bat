@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /D "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HF_ENDPOINT=https://hf-mirror.com"

set "CHECK_ONLY="
if /I "%~1"=="--check-only" set "CHECK_ONLY=1"
set "EXIT_CODE=0"

if not exist "logs" mkdir "logs"
for /F %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TIMESTAMP=%%I"
if not defined RUN_TIMESTAMP set "RUN_TIMESTAMP=unknown"
set "LOGFILE=logs\videolingo_%RUN_TIMESTAMP%.log"

echo [%date% %time%] VideoLingo launcher starting... > "%LOGFILE%"
echo Log file: %LOGFILE%

if not exist "st.py" (
    echo ERROR: st.py was not found in %CD%.
    set "EXIT_CODE=1"
    goto finish
)

set "VENV_LABEL="
set "VENV_PY="

set "LOCAL_VENV=%~dp0.venv"
if exist "%LOCAL_VENV%\Scripts\python.exe" (
    set "VENV_LABEL=project .venv"
    set "VENV_PY=%LOCAL_VENV%\Scripts\python.exe"
    goto venv_found
)

set "SHARED_VENV=%USERPROFILE%\.venvs\videolingo"
if exist "%SHARED_VENV%\Scripts\python.exe" (
    set "VENV_LABEL=shared venv"
    set "VENV_PY=%SHARED_VENV%\Scripts\python.exe"
    goto venv_found
)

set "LEGACY_VENV=%~dp0..\VideoLingo\.venv"
if exist "%LEGACY_VENV%\Scripts\python.exe" (
    set "VENV_LABEL=legacy VideoLingo .venv"
    set "VENV_PY=%LEGACY_VENV%\Scripts\python.exe"
    goto venv_found
)

echo ERROR: No usable VideoLingo environment was found.
echo Checked:
echo   %LOCAL_VENV%
echo   %SHARED_VENV%
echo   %LEGACY_VENV%
echo Run one of these commands from this folder first:
echo   python setup_env.py
echo   python setup_env.py --shared
set "EXIT_CODE=1"
goto finish

:venv_found
echo Detected %VENV_LABEL%: %VENV_PY%
"%VENV_PY%" -c "import streamlit" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Streamlit is unavailable in the selected environment.
    echo Run: "%VENV_PY%" installer.py --yes
    set "EXIT_CODE=1"
    goto finish
)

if defined CHECK_ONLY (
    "%VENV_PY%" --version
    echo Environment check passed. Streamlit was not started.
    goto finish
)

echo Starting VideoLingo with %VENV_LABEL%...
"%VENV_PY%" -m streamlit run st.py 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%LOGFILE%' -Append"
if errorlevel 1 (
    echo ERROR: VideoLingo exited with an error. Check %LOGFILE%.
    set "EXIT_CODE=1"
)

:finish
if defined CHECK_ONLY (
    endlocal & exit /B %EXIT_CODE%
)
pause
endlocal & exit /B %EXIT_CODE%
