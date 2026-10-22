@echo off
setlocal
cd /d "%~dp0"
set "ROTATOR_CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%ROTATOR_CSC%" set "ROTATOR_CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
"%ROTATOR_CSC%" /nologo /target:winexe /optimize+ /out:CBZPageRotator.exe /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll CBZPageRotator.cs
exit /b %errorlevel%
