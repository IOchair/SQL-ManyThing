@echo off
setlocal EnableExtensions

REM SQL-ManyThing Phase 1 rebuild for an installed Unreal Engine tree.
REM Copy this BAT, manything_build_db.py, and .gitignore into the same run directory.

set "RUN_DIR=%~dp0"
set "ENGINE_ROOT=D:\Path\To\Engine"
set "SCRIPT=%RUN_DIR%manything_build_db.py"
set "GITIGNORE=%RUN_DIR%.gitignore"
set "PROFILE=unreal-installed-core"

if not exist "%SCRIPT%" (
  echo Missing script: %SCRIPT%
  exit /b 1
)
if not exist "%GITIGNORE%" (
  echo Missing gitignore: %GITIGNORE%
  exit /b 1
)
if not exist "%ENGINE_ROOT%" (
  echo Missing ENGINE_ROOT: %ENGINE_ROOT%
  exit /b 1
)

echo SQL-ManyThing Phase 1 Unreal rebuild
echo ENGINE_ROOT=%ENGINE_ROOT%
echo SCRIPT=%SCRIPT%
echo GITIGNORE=%GITIGNORE%
echo PROFILE=%PROFILE%

py -3 "%SCRIPT%" "%ENGINE_ROOT%" --gitignore "%GITIGNORE%" --profile "%PROFILE%"
set "STATUS=%ERRORLEVEL%"
echo Exit code: %STATUS%
exit /b %STATUS%
