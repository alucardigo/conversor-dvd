@echo off
rem Abre a janela do Conversor de DVD (duplo clique).
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw -m conversor_dvd & exit /b 0)
where pyw >nul 2>nul && (start "" pyw -3 -m conversor_dvd & exit /b 0)
echo Python 3.10+ nao encontrado. Instale com: winget install Python.Python.3.13
pause
