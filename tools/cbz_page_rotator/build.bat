@echo off
call "%~dp0build.cmd"
set "ROTATOR_BUILD_EXIT=%errorlevel%"
if not "%ROTATOR_BUILD_EXIT%"=="0" (
    echo Build failed.
) else (
    echo Built: %~dp0CBZPageRotator.exe
)
pause
exit /b %ROTATOR_BUILD_EXIT%
