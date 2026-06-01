@echo off
setlocal EnableExtensions

REM SQL-ManyThing Universal Phase 2 -- UE 5.8 overload test
REM Scripts pre-patched for UE shader extensions (.usf .ush .hlsl)

set "RUN_DIR=%~dp0"
set "ENGINE_ROOT=D:\Path\To\Engine"
set "DB=%ENGINE_ROOT%\.srcidx\source.db"
set "BATCH=500"

echo ========================================
echo SQL-ManyThing Universal Phase 2
echo UE 5.8 overload test
echo ========================================
echo ENGINE_ROOT=%ENGINE_ROOT%
echo DB=%DB%
echo BATCH=%BATCH%
echo.

REM -- validate ---------------------------------------------------------
if not exist "%DB%" (
  echo [FAIL] Missing DB: %DB%
  exit /b 1
)

for %%f in (
  "enrich_depth_segments.py"
  "enrich_file_refs.py"
  "flatten_file_deps.py"
  "create_enriched_view.py"
) do (
  if not exist "%RUN_DIR%%%f" (
    echo [FAIL] Missing script: %RUN_DIR%%%f
    exit /b 1
  )
)

REM -- step 1/4: depth segments ----------------------------------------
echo [%time%] Step 1/4 -- enrich_depth_segments
echo ----------------------------------------
py -3 "%RUN_DIR%enrich_depth_segments.py" "%ENGINE_ROOT%" --batch %BATCH%
if %ERRORLEVEL% neq 0 (
  echo [FAIL] enrich_depth_segments rc=%ERRORLEVEL%
  exit /b 1
)

REM -- step 2/4: file refs ---------------------------------------------
echo.
echo [%time%] Step 2/4 -- enrich_file_refs
echo ----------------------------------------
py -3 "%RUN_DIR%enrich_file_refs.py" "%ENGINE_ROOT%" --batch %BATCH%
if %ERRORLEVEL% neq 0 (
  echo [FAIL] enrich_file_refs rc=%ERRORLEVEL%
  exit /b 1
)

REM -- step 3/4: flatten deps ------------------------------------------
echo.
echo [%time%] Step 3/4 -- flatten_file_deps
echo ----------------------------------------
py -3 "%RUN_DIR%flatten_file_deps.py" "%ENGINE_ROOT%"
if %ERRORLEVEL% neq 0 (
  echo [FAIL] flatten_file_deps rc=%ERRORLEVEL%
  exit /b 1
)

REM -- step 4/4: create view -------------------------------------------
echo.
echo [%time%] Step 4/4 -- create_enriched_view
echo ----------------------------------------
py -3 "%RUN_DIR%create_enriched_view.py" "%ENGINE_ROOT%"
if %ERRORLEVEL% neq 0 (
  echo [FAIL] create_enriched_view rc=%ERRORLEVEL%
  exit /b 1
)

echo.
echo [%time%] All 4 universal Phase 2 steps passed.
echo ========================================
exit /b 0
