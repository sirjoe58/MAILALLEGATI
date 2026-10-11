@echo off
REM Crea MailAllegati.exe (serve Python 3.10+ installato da python.org)
REM Se e' installato Inno Setup 6 (jrsoftware.org) crea anche MailAllegati-Setup.exe
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name MailAllegati --collect-submodules keyring.backends --add-data "LEGGIMI_AVVERTENZE.txt;." mail_allegati.py
copy /Y LEGGIMI_AVVERTENZE.txt dist\ >nul
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% installer.iss
  echo Installazione creata: %~dp0dist\MailAllegati-Setup.exe
) else (
  echo Inno Setup non trovato: creato solo il programma portatile.
)
echo.
echo Programma: %~dp0dist\MailAllegati.exe
pause
