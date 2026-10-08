"""Base comum da skill: ambiente Python, cofre de chaves e a cerca de contas da AUVP.

Toda chamada às APIs passa por aqui. A cerca é fixa no código: só a BM da AUVP na Meta e
só as MCCs AUVP e The Brain no Google. Nada fora delas é lido nem escrito, mesmo que a chave
enxergue mais no futuro.
"""
from __future__ import annotations

import base64
import json
import warnings

warnings.filterwarnings("ignore")  # avisos de versão das bibliotecas só confundem quem usa
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

# ---------------------------------------------------------------------------
# Cerca (não mexer sem o dono da skill)
# ---------------------------------------------------------------------------
META_BMS_PERMITIDAS = ("606584890671628",)          # BM AUVP
GOOGLE_MCCS_PERMITIDAS = ("7228572688", "8672510798")  # MCC AUVP, MCC The Brain
META_API = "v25.0"

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
PASTA_SCRIPTS = Path(__file__).resolve().parent
PASTA_PLUGIN = PASTA_SCRIPTS.parent.parent.parent
COFRE = PASTA_PLUGIN / "segredos" / "chaves.enc"
REQUISITOS = PASTA_SCRIPTS / "requirements.txt"
DADOS = Path.home() / ".auvp-criativos"
CREDENCIAIS = DADOS / "credenciais.json"
CERCA = DADOS / "contas-permitidas.json"
VENV = DADOS / "venv"


class Erro(Exception):
    """Erro que o usuário entende. Sai sem traceback."""


def falhar(msg: str) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Ambiente Python próprio (~/.auvp-criativos/venv)
# ---------------------------------------------------------------------------
def _python_do_venv() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python3"


def garantir_venv(instalar: bool = False) -> None:
    """Reexecuta o script dentro do venv da skill. Cria o venv só quando instalar=True."""
    py = _python_do_venv()
    if Path(sys.prefix).resolve() == VENV.resolve():
        return
    if not py.exists():
        if not instalar:
            falhar("a skill ainda não foi configurada. Diga ao Claude: configurar.")
        if sys.version_info < (3, 9):
            falhar("precisa de Python 3.9 ou mais novo.")
        DADOS.mkdir(mode=0o700, parents=True, exist_ok=True)
        print("Preparando o ambiente (só na primeira vez, leva 1 a 3 minutos)...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    if instalar:
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-r", str(REQUISITOS)])
    if os.name == "nt":
        sys.exit(subprocess.call([str(py)] + sys.argv))
    os.execv(str(py), [str(py)] + sys.argv)


# ---------------------------------------------------------------------------
# Cofre: AES-256-GCM com chave derivada da senha mestra por scrypt
# ---------------------------------------------------------------------------
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 17, 8, 1


def _chave(senha: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=sal, length=32, n=n, r=r, p=p).derive(senha.encode("utf-8"))


def selar(dados: dict, senha: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sal, nonce = os.urandom(16), os.urandom(12)
    texto = json.dumps(dados).encode("utf-8")
    cifrado = AESGCM(_chave(senha, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P)).encrypt(nonce, texto, b"auvp-criativos")
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "kdf": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
            "sal": b64(sal), "nonce": b64(nonce), "dados": b64(cifrado)}


def abrir(cofre: dict, senha: str) -> dict:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d64 = lambda k: base64.b64decode(cofre[k])
    if not (2 ** 14 <= cofre["n"] <= 2 ** 20 and cofre["r"] <= 16 and cofre["p"] <= 4):
        raise Erro("cofre de chaves com formato inesperado. Atualize o plugin.")
    chave = _chave(senha, d64("sal"), cofre["n"], cofre["r"], cofre["p"])
    try:
        texto = AESGCM(chave).decrypt(d64("nonce"), d64("dados"), b"auvp-criativos")
    except InvalidTag:
        raise Erro("senha mestra incorreta.")
    return json.loads(texto)


def gravar_privado(caminho: Path, conteudo: dict) -> None:
    DADOS.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def credenciais() -> dict:
    if not CREDENCIAIS.exists():
        falhar("a skill ainda não foi configurada. Diga ao Claude: configurar.")
    return json.loads(CREDENCIAIS.read_text(encoding="utf-8"))


def cerca() -> dict:
    if not CERCA.exists():
        falhar("lista de contas não encontrada. Diga ao Claude: configurar.")
    return json.loads(CERCA.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Meta: cliente HTTP mínimo e conferência de cerca
# ---------------------------------------------------------------------------
_CAMINHO_LEITURA = re.compile(r"(act_)?\d{5,25}(/[a-z_]{3,40})?")


def validar_id(valor: str, nome: str = "ID") -> str:
    """Todo ID que vem da pessoa ou do plano passa por aqui antes de entrar numa URL."""
    v = str(valor).strip()
    if not re.fullmatch(r"(act_)?\d{5,25}", v):
        raise Erro(f"{nome} inválido: '{v}'. Use só os números.")
    return v


def _pedir(url: str, params: dict) -> dict:
    import requests
    try:
        return requests.get(url, params=params, timeout=60).json()
    except (requests.RequestException, ValueError):
        raise Erro("sem resposta da Meta (internet ou instabilidade). Tente de novo em instantes.")


def meta_get(caminho: str, token: str, **params) -> dict:
    if not _CAMINHO_LEITURA.fullmatch(caminho):
        raise Erro(f"leitura recusada: '{caminho}'.")
    params["access_token"] = token
    dados = _pedir(f"https://graph.facebook.com/{META_API}/{caminho}", params)
    if "error" in dados:
        raise Erro(f"a Meta recusou a leitura: {dados['error'].get('message')}")
    return dados


def meta_paginar(caminho: str, token: str, **params) -> list:
    itens, dados = [], meta_get(caminho, token, **params)
    while True:
        itens += dados.get("data", [])
        cursor = dados.get("paging", {}).get("cursors", {}).get("after")
        if not dados.get("paging", {}).get("next") or not cursor:
            return itens
        params["after"] = cursor
        dados = meta_get(caminho, token, **params)


def conta_meta(conta: str) -> str:
    """Normaliza e confere se a conta de anúncio está na cerca. Devolve 'act_<id>'."""
    cid = validar_id(conta, "conta").replace("act_", "")
    permitidas = {c["id"] for c in cerca()["meta"]["contas"]}
    if cid not in permitidas:
        raise Erro(f"a conta {cid} não é da AUVP. Esta skill só trabalha nas contas da BM da AUVP.")
    return f"act_{cid}"


def pagina_meta(pagina: str) -> str:
    permitidas = {p["id"] for p in cerca()["meta"]["paginas"]}
    if pagina not in permitidas:
        raise Erro(f"a página {pagina} não é da AUVP.")
    return pagina


def instagram_meta(ig: str) -> str:
    permitidas = {i["id"] for i in cerca()["meta"]["instagram"]}
    if ig not in permitidas:
        raise Erro(f"o Instagram {ig} não é da AUVP.")
    return ig


def conta_do_objeto_meta(objeto_id: str, token: str) -> str:
    """Lê a conta dona de um conjunto/anúncio e confere a cerca antes de qualquer uso."""
    dados = meta_get(validar_id(objeto_id), token, fields="account_id")
    return conta_meta(dados["account_id"])


# ---------------------------------------------------------------------------
# Google: cliente do SDK e conferência de cerca
# ---------------------------------------------------------------------------
def conta_google(conta: str) -> tuple:
    """Confere se a conta está na cerca. Devolve (customer_id, mcc que a gerencia)."""
    cid = validar_id(conta.replace("-", ""), "conta")
    for c in cerca()["google"]["contas"]:
        if c["id"] == cid:
            return cid, c["mcc"]
    raise Erro(f"a conta Google {cid} não é da AUVP. Esta skill só trabalha nas MCCs AUVP e The Brain.")


def cliente_google(mcc: str):
    if mcc not in GOOGLE_MCCS_PERMITIDAS:
        raise Erro(f"MCC {mcc} fora da AUVP.")
    os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
    from google.ads.googleads.client import GoogleAdsClient
    g = credenciais()["google"]
    return GoogleAdsClient.load_from_dict({
        "developer_token": g["developer_token"],
        "client_id": g["client_id"],
        "client_secret": g["client_secret"],
        "refresh_token": g["refresh_token"],
        "login_customer_id": mcc,
        "use_proto_plus": True,
    })


def _sem_segredo(texto: str) -> str:
    texto = re.sub(r"(access_token|refresh_token|client_secret|developer_token)=[^&\s'\"]+", r"\1=***", texto)
    try:
        for bloco in json.loads(CREDENCIAIS.read_text(encoding="utf-8")).values():
            for valor in bloco.values():
                if isinstance(valor, str) and len(valor) > 12:
                    texto = texto.replace(valor, "***")
    except Exception:
        pass
    return texto


def principal(funcao) -> None:
    """Roda a função e transforma qualquer erro em mensagem curta, sem traceback e sem chave."""
    try:
        funcao()
    except Erro as e:
        falhar(_sem_segredo(str(e)))
    except KeyboardInterrupt:
        falhar("interrompido.")
    except Exception as e:
        falhar(_sem_segredo(f"falha inesperada ({type(e).__name__}): {e}"))
