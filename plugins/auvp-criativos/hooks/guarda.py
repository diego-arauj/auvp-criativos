"""Trava do plugin AUVP Criativos (hook PreToolUse e UserPromptSubmit).

Roda antes de toda ferramenta do Claude, em qualquer modo de permissão, e falha fechado: qualquer
erro aqui bloqueia. Barra o caminho fácil para usar as chaves por fora dos scripts da skill:
ler a pasta de credenciais, editar o plugin, desligar os hooks e rodar os scripts num formato que
permita encadear outro comando. Não é uma barreira contra uma pessoa com acesso ao computador;
é uma barreira contra o Claude, inclusive quando alguém pede.
"""
import json
import os
import re
import shlex
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(RAIZ, "skills", "subir-criativos", "scripts")
CASA = os.path.expanduser("~")
DADOS = os.path.join(CASA, ".auvp-criativos")
SCRIPTS_PERMITIDOS = ("configurar.py", "meta.py", "gads.py")
PYTHON_PORTATIL = os.path.join(RAIZ, "runtime", "windows", "python.exe")

# Termos que só aparecem para chegar nas chaves, no plugin ou na chave-mestra dos hooks.
PROIBIDO = (
    ".auvp", "auvp-criativos", "chaves.enc", "credenciais.json", "contas-permitidas",
    ".claude/plugins", "plugins/cache", "plugins/marketplaces", "disableallhooks",
    "claude_code_plugin", "claude_plugin_root", "claude_config_dir",
)
SENHA = re.compile(r"\b[0-9A-F]{6}(?:-[0-9A-F]{6}){4}\b", re.I)


def normal(texto):
    """Minúsculo e com barras normais: macOS e Windows não diferenciam maiúscula no caminho."""
    return str(texto).replace("\\", "/").lower()


def colado(texto):
    """Tira aspas e barras de escape, que o shell some e serviriam para picotar um termo."""
    return re.sub(r"[\"'\\]", "", str(texto)).lower()


def negar(motivo):
    print(f"[AUVP Criativos] Bloqueado: {motivo}", file=sys.stderr)
    sys.exit(2)


def termo_proibido(texto):
    versoes = (colado(texto), normal(texto))
    return next((p for p in PROIBIDO if any(p in t for t in versoes)), "")


def caminho_real(caminho):
    return normal(os.path.realpath(os.path.expanduser(str(caminho))))


def dentro(caminho, pasta):
    if not caminho:
        return False
    alvo, base = caminho_real(caminho), caminho_real(pasta)
    return alvo == base or alvo.startswith(base + "/")


def acima_dos_dados(caminho):
    """Busca a partir da pasta pessoal (ou acima dela) alcança as credenciais."""
    if not caminho:
        return False
    return dentro(DADOS, caminho)


def interpretador_aceito(primeiro):
    if primeiro in ("python3", "python"):
        return True
    return caminho_real(primeiro) == caminho_real(PYTHON_PORTATIL)


def comando_da_skill(comando):
    """Aceita só: <python> "<pasta da skill>/scripts/<script>.py" [argumentos], sem encadear nada.

    <python> é python3/python ou o Python portátil do plugin (Windows); no PowerShell, com & na frente.
    """
    if any(c in comando for c in "$`\n\r"):
        return False
    try:
        lex = shlex.shlex(comando.replace("\\", "/"), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        partes = list(lex)
    except ValueError:
        return False
    if partes[:1] == ["&"]:
        partes = partes[1:]
    if len(partes) < 2 or not interpretador_aceito(partes[0]):
        return False
    if any(p and all(ch in "();<>|&" for ch in p) for p in partes):
        return False
    script = caminho_real(partes[1])
    return any(script == caminho_real(os.path.join(SCRIPTS, s)) for s in SCRIPTS_PERMITIDOS)


def checar_ferramenta(evento):
    ferramenta = evento.get("tool_name", "")
    entrada = evento.get("tool_input") or {}
    if not isinstance(entrada, dict):
        negar("entrada de ferramenta inesperada.")
    if ferramenta == "Skill":
        return

    comando = entrada.get("command")
    if isinstance(comando, str) and comando_da_skill(comando):
        return

    termo = termo_proibido(json.dumps(entrada, ensure_ascii=False))
    if termo:
        if comando is not None:
            negar("rode os scripts da skill só no formato python3 \"<pasta da skill>/scripts/<script>.py\" "
                  "<argumentos>, um por vez, sem cd, &&, ; ou |. As credenciais e o plugin não podem ser acessados.")
        negar("as credenciais e os arquivos do plugin não podem ser lidos, copiados nem alterados.")

    for chave in ("file_path", "path", "notebook_path"):
        alvo = entrada.get(chave)
        if not alvo:
            continue
        if dentro(alvo, DADOS) or dentro(alvo, RAIZ):
            negar("as credenciais e os arquivos do plugin não podem ser lidos nem alterados.")
        if ferramenta in ("Grep", "Glob") and acima_dos_dados(alvo):
            negar("busca a partir da pasta pessoal não é permitida com este plugin; busque numa pasta específica.")
        if ferramenta in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            nome = os.path.basename(normal(alvo))
            if "/.claude/" in normal(alvo) and nome.startswith("settings"):
                negar("as configurações do Claude Code não podem ser alteradas com este plugin ativo.")
    if ferramenta == "Glob" and not entrada.get("path") and acima_dos_dados(evento.get("cwd") or ""):
        if normal(entrada.get("pattern", "")).startswith(("**", ".")):
            negar("busca a partir da pasta pessoal não é permitida com este plugin; busque numa pasta específica.")


def checar_mensagem(evento):
    if SENHA.search(evento.get("prompt") or ""):
        negar("não cole a senha mestra no chat. Diga só \"configurar\": a senha é digitada numa janela própria.")


def main():
    evento = json.load(sys.stdin)
    if evento.get("hook_event_name") == "UserPromptSubmit" or "prompt" in evento and "tool_name" not in evento:
        checar_mensagem(evento)
    else:
        checar_ferramenta(evento)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as erro:  # falha fechado
        negar(f"a trava não conseguiu conferir esta ação ({type(erro).__name__}).")
