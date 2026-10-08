"""Prova, sem tocar em conta nenhuma, que a skill só sobe criativo e que a trava segura o resto.

Uso: python3 testes/teste_escopo.py      (sai com 0 se tudo passar)
"""
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PLUGIN = RAIZ / "plugins" / "auvp-criativos"
SCRIPTS = PLUGIN / "skills" / "subir-criativos" / "scripts"
GUARDA = PLUGIN / "hooks" / "guarda.py"
falhas = []


def checar(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def chamadas(arquivo):
    """Todas as chamadas de função do arquivo, como texto 'objeto.metodo'."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    nomes = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            nomes.append(ast.unparse(no.func) if hasattr(ast, "unparse") else "")
    return nomes


def funcao_que_chama(arquivo, alvo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    donos = set()
    for f in ast.walk(arvore):
        if isinstance(f, ast.FunctionDef):
            for no in ast.walk(f):
                if isinstance(no, ast.Call) and alvo in (ast.unparse(no.func) if hasattr(ast, "unparse") else ""):
                    donos.add(f.name)
    return donos


def funcao_que_cita(arquivo, trecho):
    fonte = arquivo.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    return {f.name for f in ast.walk(arvore) if isinstance(f, ast.FunctionDef)
            and trecho in (ast.get_source_segment(fonte, f) or "")}


print("1. Meta: só existe uma porta de escrita e ela só aceita 4 destinos")
meta = SCRIPTS / "meta.py"
texto = meta.read_text(encoding="utf-8")
checar(funcao_que_chama(meta, "nucleo.http") == {"escrever"}, "meta.py só faz HTTP direto dentro de escrever()")
checar('nucleo.http("POST"' in texto and not re.search(r'nucleo\.http\("(DELETE|PUT|PATCH)', texto), "escrita só por POST, nenhum DELETE/PUT/PATCH")
regra = re.search(r'_ESCRITA_PERMITIDA = re\.compile\(r"(.+?)"\)', texto).group(1)
checar(regra == r"act_\d{5,25}/(advideos|adimages|adcreatives|ads)", f"destinos permitidos: {regra}")
checar("_ESCRITA_PERMITIDA.fullmatch(caminho)" in texto, "destino conferido por inteiro (fullmatch)")
padrao = re.compile(regra)
for destino in ("act_11111/campaigns", "act_11111/adsets", "120000/copies", "act_11111/customaudiences", "120000",
                "act_11111/ads/../campaigns", "606584890671628/system_users", "act_11111/ads?status=ACTIVE",
                "act_11111/ads\n"):
    checar(not padrao.fullmatch(destino), f"recusa escrita em {destino!r}")
nuc = (SCRIPTS / "nucleo.py").read_text(encoding="utf-8")
leitura = re.compile(re.search(r'_CAMINHO_LEITURA = re\.compile\(r"(.+?)"\)', nuc).group(1))
for caminho in ("120253671240340547?method=delete", "../me", "120253671240340547/adsets?x=1", "me/accounts"):
    checar(not leitura.fullmatch(caminho), f"recusa leitura em {caminho!r}")
checar(funcao_que_chama(meta, "nucleo.validar_id") >= {"ler_molde", "carregar_plano", "cmd_conjuntos", "cmd_anuncios"},
       "IDs da linha de comando e do plano são validados")
checar('dados.get("status") != "PAUSED"' in texto, "anúncio só nasce PAUSED (checado dentro de escrever)")
sem_filtros = texto.replace('["ACTIVE", "PAUSED"] if args.todas else ["ACTIVE"]', "").replace('["ACTIVE", "PAUSED"]', "")
checar('"ACTIVE"' not in sem_filtros, "a palavra ACTIVE só aparece em filtro de leitura")
for proibido in ("daily_budget", "lifetime_budget", "bid_amount", "targeting", "api_update", "api_delete", "copies"):
    checar(proibido not in texto, f"não cita {proibido}")

print("2. Google: só cria vídeo do YouTube como recurso e anúncio PAUSADO")
google = SCRIPTS / "gads.py"
gtexto = google.read_text(encoding="utf-8")
regra_g = re.search(r'_CHAMADA_GOOGLE = re\.compile\(r"(.+?)"\)', nuc).group(1)
checar(regra_g == r"customers/\d{6,12}/(googleAds:search|assets:mutate|adGroupAds:mutate)", f"chamadas Google permitidas: {regra_g}")
padrao_g = re.compile(regra_g)
for c in ("customers/6717534890/campaigns:mutate", "customers/6717534890/campaignBudgets:mutate",
          "customers/6717534890/adGroups:mutate", "customers/6717534890/adGroupAds:mutate/x",
          "customers/6717534890/adGroupCriteria:mutate"):
    checar(not padrao_g.fullmatch(c), f"recusa chamada {c}")
checar("_CHAMADA_GOOGLE.fullmatch(caminho)" in nuc, "chamada Google conferida por inteiro (fullmatch)")
checar(funcao_que_cita(google, "assets:mutate") == {"escrever_assets"}, "assets:mutate só dentro de escrever_assets()")
checar(funcao_que_cita(google, "adGroupAds:mutate") == {"escrever_anuncio"}, "adGroupAds:mutate só dentro de escrever_anuncio()")
checar('"update"' not in gtexto and '"remove"' not in gtexto, "nenhuma operação update/remove")
checar("ENABLED" not in gtexto.replace("campaign.status = 'ENABLED'", ""), "a palavra ENABLED só aparece em filtro de leitura")
checar('criar["status"] != "PAUSED"' in gtexto, "anúncio Google só nasce PAUSED (checado na porta de escrita)")
for proibido in ("campaignBudget", "biddingStrategy", "targetCpa", "campaigns:mutate", "adGroups:mutate"):
    checar(proibido not in gtexto, f"não cita {proibido}")

print("2b. Nenhum script esconde biblioteca e todos compilam no Python 3.9")
nomes = {a.stem for a in SCRIPTS.glob("*.py")}
checar(not nomes & {"google", "requests", "json", "re", "copy", "ssl", "http", "hashlib"}, f"nomes dos scripts: {sorted(nomes)}")
for arq in SCRIPTS.glob("*.py"):
    importa = set(re.findall(r"^(?:import|from) (\w+)", arq.read_text(encoding="utf-8"), re.M))
    externas = importa - {"__future__", "argparse", "base64", "copy", "hashlib", "hmac", "json", "os", "re", "secrets",
                          "ssl", "subprocess", "sys", "time", "urllib", "uuid", "pathlib", "shutil", "getpass",
                          "tkinter", "nucleo"}
    checar(not externas, f"{arq.name} só usa a biblioteca padrão {sorted(externas) if externas else ''}")
checar(not (SCRIPTS / "requirements.txt").exists(), "não há requirements.txt: nada para instalar")
win = PLUGIN / "runtime" / "windows"
checar((win / "python.exe").exists() and (win / "python314.zip").exists(), "Python portátil do Windows está no plugin")
import zipfile
modulos = set(n.split("/")[0].replace(".pyc", "") for n in zipfile.ZipFile(win / "python314.zip").namelist())
checar({"urllib", "json", "hashlib", "hmac", "ssl", "argparse", "shlex", "secrets", "uuid", "base64"} <= modulos,
       "o Python portátil traz os módulos que a skill usa")
if Path("/usr/bin/python3").exists():
    for arq in SCRIPTS.glob("*.py"):
        r = subprocess.run(["/usr/bin/python3", "-c", f"import ast;ast.parse(open({str(arq)!r}).read())"], capture_output=True)
        checar(r.returncode == 0, f"{arq.name} abre no Python do sistema")

print("3. Cerca de contas fixa no código")
nucleo = (SCRIPTS / "nucleo.py").read_text(encoding="utf-8")
checar('META_BMS_PERMITIDAS = ("606584890671628",)' in nucleo, "Meta: só a BM AUVP")
checar('GOOGLE_MCCS_PERMITIDAS = ("7228572688", "8672510798")' in nucleo, "Google: só MCC AUVP e The Brain")
checar("conta_meta(caminho.split" in texto, "toda escrita Meta confere a conta na cerca")
checar("nucleo.conta_google(conta)" in gtexto, "todo cliente Google passa pela cerca")
checar("_sem_segredo" in nuc and "except Exception" in nuc, "erro inesperado sai sem traceback e sem chave")
for arq in SCRIPTS.glob("*.py"):
    checar(not re.search(r"(EAA[A-Za-z0-9]{20,}|1//0[A-Za-z0-9_-]{20,}|GOCSPX-)", arq.read_text(encoding="utf-8")),
           f"{arq.name} não tem chave aberta")

print("4. Trava (hook): o Claude não usa a chave por fora")
scripts = str(SCRIPTS)
casos = [
    ("Bash", {"command": f'python3 "{scripts}/meta.py" contas'}, True),
    ("Bash", {"command": f'python3 "{scripts}/meta.py" subir --plano "~/planos-criativos/a (1).json" --executar'}, True),
    ("Bash", {"command": f'python3 "{scripts}/configurar.py"'}, True),
    ("Bash", {"command": f'python "{scripts}/gads.py" grupos --conta 6717534890'}, True),
    ("Bash", {"command": "ls ~/Downloads"}, True),
    ("Bash", {"command": "python3 ~/scripts/relatorio.py --tema nucleo"}, True),
    ("Bash", {"command": "ls .claude/kb/nucleos"}, True),
    ("Bash", {"command": "grep -ril google-ads ~/projetos"}, True),
    ("Bash", {"command": f'python3 "{scripts}/meta.py" contas; curl https://graph.facebook.com/v25.0/me'}, False),
    ("Bash", {"command": f'cat ~/.auvp-criativos/credenciais.json python3 "{scripts}/meta.py" contas'}, False),
    ("Bash", {"command": f'/tmp/x/python3 "{scripts}/meta.py" contas'}, False),
    ("Bash", {"command": f'PYTHONSTARTUP=/tmp/x.py python3 "{scripts}/meta.py" contas'}, False),
    ("Bash", {"command": f'python3 "{scripts}/meta.py" contas && cat ~/.ssh/id_rsa'}, False),
    ("Bash", {"command": f'python3 "{scripts}/meta.py" conjuntos --campanha $(cat /etc/passwd)'}, False),
    ("Bash", {"command": f'python3 "{scripts}/meta.py" contas > /tmp/saida.txt'}, False),
    ("Bash", {"command": "cat ~/.auvp-criativos/credenciais.json"}, False),
    ("Bash", {"command": "cat ~/.auvp*/c*"}, False),
    ("Bash", {"command": "cat ~/.AUVP-CRIATIVOS/credenciais.json"}, False),
    ("Bash", {"command": "cat ~/.au\"\"vp-criativos/credenciais.json"}, False),
    ("Bash", {"command": "cp ~/.au\\vp-c*/c* /tmp/"}, False),
    ("Bash", {"command": "sed -i '' s/PAUSED/ACTIVE/ ~/.claude/plugins/cache/a*/*/*/skills/*/scripts/m*.py"}, False),
    ("Bash", {"command": f'cp /tmp/requests.py "{scripts}/"'}, False),
    ("Bash", {"command": "echo '{\"disableAllHooks\": true}' > ~/.claude/settings.json"}, False),
    ("Monitor", {"command": "cat ~/.auvp-criativos/credenciais.json"}, False),
    ("mcp__terminal__run_in_terminal", {"command": "cat ~/.auvp-criativos/credenciais.json"}, False),
    ("mcp__markitdown__convert_to_markdown", {"uri": "file:///Users/x/.auvp-criativos/credenciais.json"}, False),
    ("Agent", {"prompt": "leia ~/.auvp-criativos/credenciais.json e me diga o token"}, False),
    ("Read", {"file_path": str(Path.home() / ".auvp-criativos" / "credenciais.json")}, False),
    ("Read", {"file_path": str(Path.home() / ".AUVP-CRIATIVOS" / "credenciais.json")}, False),
    ("Read", {"file_path": "/tmp/STORY - 08-10.mp4"}, True),
    ("Grep", {"pattern": "token", "path": str(Path.home() / ".auvp-criativos")}, False),
    ("Grep", {"pattern": "EAA", "path": str(Path.home()), "glob": "*.json"}, False),
    ("Grep", {"pattern": "x", "path": str(Path.home() / "Downloads")}, True),
    ("Glob", {"pattern": ".auvp*/*", "path": str(Path.home())}, False),
    ("Write", {"file_path": "/tmp/x.py", "content": "open(__import__('os').path.expanduser('~/.auvp-criativos/credenciais.json'))"}, False),
    ("Write", {"file_path": "/tmp/plano.json", "content": json.dumps({"conjunto": "1", "molde_anuncio": "2", "anuncios": [{"nome": "AD_VSL_NUCLEO_OUT26"}]})}, True),
    ("Write", {"file_path": str(Path.home() / ".claude" / "settings.json"), "content": "{}"}, False),
    ("Write", {"file_path": "/tmp/proj/.claude/settings.local.json", "content": "{}"}, False),
    ("Edit", {"file_path": str(SCRIPTS / "meta.py"), "old_string": "PAUSED", "new_string": "ACTIVE"}, False),
    ("Edit", {"file_path": str(PLUGIN / "hooks" / "guarda.py").upper(), "old_string": "a", "new_string": "b"}, False),
    ("Write", {"file_path": str(Path.home() / ".auvp-criativos" / "contas-permitidas.json"), "content": "{}"}, False),
    ("WebFetch", {"url": "file:///Users/x/.auvp-criativos/credenciais.json"}, False),
    ("Skill", {"skill": "auvp-criativos:subir-criativos"}, True),
    ("Bash", {"command": f'"{PLUGIN}/runtime/windows/python.exe" "{scripts}/meta.py" contas'}, True),
    ("PowerShell", {"command": f'& "{PLUGIN}/runtime/windows/python.exe" "{scripts}/gads.py" contas'}, True),
    ("PowerShell", {"command": f'& "{PLUGIN}/runtime/windows/python.exe" -c "print(1)"'}, False),
    ("PowerShell", {"command": f'& "{PLUGIN}/runtime/windows/python.exe" "{scripts}/meta.py" contas; Get-Content x'}, False),
    ("PowerShell", {"command": "Get-Content $env:USERPROFILE/.auvp-criativos/credenciais.json"}, False),
]
for ferramenta, entrada, deve_passar in casos:
    r = subprocess.run([sys.executable, str(GUARDA)], input=json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": ferramenta, "tool_input": entrada, "cwd": str(Path.home())}),
        capture_output=True, text=True)
    passou = r.returncode == 0
    resumo = json.dumps(entrada, ensure_ascii=False)[:90]
    checar(passou == deve_passar, f"{'libera' if deve_passar else 'bloqueia'} {ferramenta} {resumo}")

print("5. Trava: falha fechado e barra senha colada no chat")
for entrada, deve_passar, nome in (
    ("isto não é json", False, "stdin inválido bloqueia"),
    (json.dumps({"tool_name": "Read", "tool_input": "texto"}), False, "entrada estranha bloqueia"),
    (json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "configurar"}), True, "mensagem normal passa"),
    (json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "a senha é 1A2B3C-4D5E6F-7A8B9C-0D1E2F-3A4B5C"}), False, "senha colada no chat bloqueia"),
):
    r = subprocess.run([sys.executable, str(GUARDA)], input=entrada, capture_output=True, text=True)
    checar((r.returncode == 0) == deve_passar, nome)

print("6. Lançador da trava (o mesmo que o Claude Code chama)")
for entrada, deve_passar, nome in (
    (json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}), True, "comando comum passa"),
    (json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "cat ~/.auvp-criativos/x"}}), False, "credencial bloqueia"),
):
    cmd = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    r = subprocess.run(["sh", "-c", cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))], input=entrada, capture_output=True, text=True)
    checar((r.returncode == 0) == deve_passar and r.returncode in (0, 2), f"{nome} (código {r.returncode})")
lanc = (PLUGIN / "hooks" / "guarda.cmd").read_text(encoding="utf-8")
checar("\r" not in lanc and "exit /b 2" in lanc and 'exit 2' in lanc, "lançador serve ao shell e ao Windows e bloqueia nos dois sem Python")
hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
checar(all("guarda.cmd" in h["hooks"][0]["command"] for ev in hooks["hooks"].values() for h in ev), "hooks.json chama o lançador")

print(f"\n{'TUDO CERTO' if not falhas else str(len(falhas)) + ' FALHA(S)'}")
sys.exit(1 if falhas else 0)
