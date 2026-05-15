@echo off
REM Start HelperLearner Django dev server in a new terminal window (uses venv python if available)
pushd "%~dp0"

REM Prefer the venv python executable if present
if exist venv\Scripts\python.exe (
  start "HelperLearner" cmd /k "venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000"
) else (
  REM Fallback to activating venv or using system python
  if exist venv\Scripts\activate.bat (
    start "HelperLearner" cmd /k "call venv\Scripts\activate.bat && python manage.py runserver 0.0.0.0:8000"
  ) else (
    start "HelperLearner" cmd /k "python manage.py runserver 0.0.0.0:8000"
  )
)

popd
exit /b 0
