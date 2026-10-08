#!/bin/sh
# Escolhe o Python e roda a trava. No Windows (Git Bash) usa o Python portátil do plugin;
# no Mac, o python3 do sistema. Sem Python, bloqueia (exit 2): a trava nunca falha aberta.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PY="$DIR/runtime/windows/python.exe" ;;
  *) PY="$(command -v python3 || command -v python)" ;;
esac
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  echo "[AUVP Criativos] Bloqueado: não achei o Python para rodar a trava. Veja o MANUAL." >&2
  exit 2
fi
"$PY" "$DIR/hooks/guarda.py" || exit 2
