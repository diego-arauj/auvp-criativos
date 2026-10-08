:; # Lançador da trava. Este arquivo roda como script de shell (Mac, Git Bash) e como .cmd (Windows).
:; # Shell: escolhe o Python e roda guarda.py. Sem Python, bloqueia (exit 2): a trava nunca falha aberta.
:; DIR="$(cd "$(dirname "$0")/.." && pwd)"; case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) PY="$DIR/runtime/windows/python.exe" ;; *) PY="$(command -v python3 || command -v python)" ;; esac
:; if [ -z "$PY" ] || [ ! -x "$PY" ]; then echo "[AUVP Criativos] Bloqueado: não achei o Python para rodar a trava. Veja o MANUAL." >&2; exit 2; fi
:; "$PY" "$DIR/hooks/guarda.py" || exit 2; exit 0
@echo off
rem Windows (PowerShell ou cmd): usa o Python portátil que vem no plugin.
"%~dp0..\runtime\windows\python.exe" "%~dp0guarda.py"
if errorlevel 1 exit /b 2
exit /b 0
