@echo off
REM Run the Michigan SPC Zone Converter from source, without installing it.
REM Takes the same entry point as the frozen .exe (see launch.py).
py "%~dp0launch.py" %*
