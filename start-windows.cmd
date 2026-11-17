@echo off
setlocal
pushd "%~dp0" || exit /b 1
where py >nul 2>&1
if errorlevel 1 goto path_python
py -3.12 -c "import sys" >nul 2>&1
if errorlevel 1 goto path_python
py -3.12 start.py %*
goto done
:path_python
where python >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.12 from https://www.python.org/downloads/ first.
  exit /b 1
)
python start.py %*
:done
set "result=%errorlevel%"
popd
if not "%result%"=="0" pause
exit /b %result%
