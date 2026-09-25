@echo off
rem Nomentrace : lancement local par double-clic.
chcp 65001 >nul
title Nomentrace
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
rem Port : NOMENTRACE_PORT s'il est défini, 8000 sinon.
if not defined NOMENTRACE_PORT set "NOMENTRACE_PORT=8000"
set "PORT=%NOMENTRACE_PORT%"
rem Mode local : sans connexion, administrateur implicite, poste local seulement.
rem Sans cette variable, Nomentrace exige un compte (voir docs/EXPLOITATION.md).
set "NOMENTRACE_MODE_LOCAL=1"
set "NOMENTRACE_HOTE=127.0.0.1"

rem 1. Environnement virtuel
if exist "%PY%" goto venv_ok
echo Création de l'environnement Python .venv ...
py -3.14 -m venv .venv >nul 2>&1
if exist "%PY%" goto venv_ok
python -m venv .venv >nul 2>&1
if exist "%PY%" goto venv_ok
echo.
echo ERREUR : Python 3.14 est introuvable.
echo Installer Python 3.14 depuis https://www.python.org/downloads/ puis relancer.
goto erreur

:venv_ok
rem 2. Dépendances, réinstallées seulement si requirements.txt a changé
fc /b requirements.txt .venv\requirements.installe >nul 2>&1
if not errorlevel 1 goto deps_ok
echo Installation des dépendances ...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERREUR : l'installation des dépendances a échoué.
  goto erreur
)
copy /y requirements.txt .venv\requirements.installe >nul

:deps_ok
rem 3. Port déjà occupé ?
"%PY%" -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1',%PORT%))==0 else 0)"
if errorlevel 1 (
  echo.
  echo ERREUR : le port %PORT% est déjà occupé.
  echo Nomentrace est peut-être déjà lancé dans une autre fenêtre : http://127.0.0.1:%PORT%
  echo Sinon, fermer le programme qui utilise ce port, puis relancer.
  goto erreur
)

rem 4. Ouverture du navigateur dès que le serveur répond
start "" /b "%PY%" -c "import socket,time,webbrowser; [time.sleep(0.5) for _ in range(60) if socket.socket().connect_ex(('127.0.0.1',%PORT%))!=0]; webbrowser.open('http://127.0.0.1:%PORT%')"

rem 5. Serveur
echo Nomentrace démarre sur http://127.0.0.1:%PORT%  (fermer cette fenêtre pour l'arrêter)
"%PY%" -m backend
if errorlevel 1 goto erreur
goto fin

:erreur
echo.
pause
exit /b 1

:fin
endlocal
