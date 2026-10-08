"""Base comum da skill: cofre de chaves, HTTP, cerca de contas da AUVP e acesso às APIs.

Só usa a biblioteca padrão do Python: nada para instalar. No Windows, o plugin traz um Python
portátil oficial (pasta runtime/windows); no Mac, usa o python3 do sistema.

A cerca é fixa no código: só a BM da AUVP na Meta e só as MCCs AUVP e The Brain no Google.
Nada fora delas é lido nem escrito, mesmo que a chave enxergue mais no futuro.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
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
GOOGLE_API = "v24"

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
PASTA_SCRIPTS = Path(__file__).resolve().parent
PASTA_PLUGIN = PASTA_SCRIPTS.parent.parent.parent
COFRE = PASTA_PLUGIN / "segredos" / "chaves.enc"
DADOS = Path.home() / ".auvp-criativos"
CREDENCIAIS = DADOS / "credenciais.json"
CERCA = DADOS / "contas-permitidas.json"


class Erro(Exception):
    """Erro que o usuário entende. Sai sem traceback."""


def falhar(msg: str) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Cofre: PBKDF2-SHA256 + cifra de fluxo HMAC-SHA256 (modo contador) + selo HMAC.
# Só biblioteca padrão, para rodar igual em qualquer Python 3.9+, no Mac e no Windows.
# ---------------------------------------------------------------------------
ITERACOES = 600_000
_ROTULO = b"auvp-criativos-v2"


def _chaves(senha: str, sal: bytes, iteracoes: int) -> tuple:
    bruto = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes, dklen=64)
    return bruto[:32], bruto[32:]


def _fluxo(chave: bytes, nonce: bytes, tamanho: int) -> bytes:
    blocos = (tamanho + 31) // 32
    return b"".join(hmac.new(chave, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
                    for i in range(blocos))[:tamanho]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def selar(dados: dict, senha: str) -> dict:
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    k_cifra, k_mac = _chaves(senha, sal, ITERACOES)
    texto = json.dumps(dados).encode("utf-8")
    cifrado = _xor(texto, _fluxo(k_cifra, nonce, len(texto)))
    selo = hmac.new(k_mac, _ROTULO + sal + nonce + cifrado, hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 2, "kdf": "pbkdf2-sha256", "iteracoes": ITERACOES, "sal": b64(sal), "nonce": b64(nonce),
            "dados": b64(cifrado), "selo": b64(selo)}


def abrir(cofre: dict, senha: str) -> dict:
    if cofre.get("v") != 2 or not (100_000 <= int(cofre.get("iteracoes", 0)) <= 5_000_000):
        raise Erro("cofre de chaves com formato inesperado. Atualize o plugin.")
    d64 = lambda k: base64.b64decode(cofre[k])
    sal, nonce, cifrado = d64("sal"), d64("nonce"), d64("dados")
    k_cifra, k_mac = _chaves(senha, sal, int(cofre["iteracoes"]))
    esperado = hmac.new(k_mac, _ROTULO + sal + nonce + cifrado, hashlib.sha256).digest()
    if not hmac.compare_digest(esperado, d64("selo")):
        raise Erro("senha mestra incorreta.")
    return json.loads(_xor(cifrado, _fluxo(k_cifra, nonce, len(cifrado))))


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
# HTTP mínimo (urllib). O erro nunca leva a URL, porque ela pode carregar a chave.
# ---------------------------------------------------------------------------
_SSL = ssl.create_default_context()


def http(metodo: str, url: str, corpo: bytes = None, cabecalhos: dict = None, tempo: int = 120) -> tuple:
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(pedido, timeout=tempo, context=_SSL) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise Erro("falha de certificado na conexão. Se a empresa usa proxy ou antivírus que inspeciona "
                       "HTTPS, fale com o suporte de TI.")
        raise Erro("sem resposta do servidor (internet ou instabilidade). Tente de novo em instantes.")
    except (OSError, TimeoutError):
        raise Erro("sem resposta do servidor (internet ou instabilidade). Tente de novo em instantes.")


def json_de(bruto: bytes) -> dict:
    try:
        return json.loads(bruto.decode("utf-8") or "{}")
    except ValueError:
        raise Erro("resposta inesperada do servidor. Tente de novo em instantes.")


def multipart(campos: dict, arquivos: dict) -> tuple:
    """Corpo multipart/form-data. arquivos: {campo: (nome, bytes)}."""
    fronteira = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    for k, (nome, conteudo) in arquivos.items():
        nome_seguro = re.sub(r'[\r\n"]', "_", nome)
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"; filename="{nome_seguro}"\r\n'
                      "Content-Type: application/octet-stream\r\n\r\n".encode("utf-8") + conteudo + b"\r\n")
    partes.append(f"--{fronteira}--\r\n".encode("utf-8"))
    return b"".join(partes), {"Content-Type": f"multipart/form-data; boundary={fronteira}"}


# ---------------------------------------------------------------------------
# Meta: leitura e conferência de cerca
# ---------------------------------------------------------------------------
_CAMINHO_LEITURA = re.compile(r"(act_)?\d{5,25}(/[a-z_]{3,40})?")


def validar_id(valor, nome: str = "ID") -> str:
    """Todo ID que vem da pessoa ou do plano passa por aqui antes de entrar numa URL."""
    v = str(valor).strip()
    if not re.fullmatch(r"(act_)?\d{5,25}", v):
        raise Erro(f"{nome} inválido: '{v}'. Use só os números.")
    return v


def meta_get(caminho: str, token: str, **params) -> dict:
    if not _CAMINHO_LEITURA.fullmatch(caminho):
        raise Erro(f"leitura recusada: '{caminho}'.")
    params["access_token"] = token
    url = f"https://graph.facebook.com/{META_API}/{caminho}?" + urllib.parse.urlencode(params)
    dados = json_de(http("GET", url, tempo=60)[1])
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
    if cid not in {c["id"] for c in cerca()["meta"]["contas"]}:
        raise Erro(f"a conta {cid} não é da AUVP. Esta skill só trabalha nas contas da BM da AUVP.")
    return f"act_{cid}"


def pagina_meta(pagina: str) -> str:
    if pagina not in {p["id"] for p in cerca()["meta"]["paginas"]}:
        raise Erro(f"a página {pagina} não é da AUVP.")
    return pagina


def instagram_meta(ig: str) -> str:
    if ig not in {i["id"] for i in cerca()["meta"]["instagram"]}:
        raise Erro(f"o Instagram {ig} não é da AUVP.")
    return ig


def conta_do_objeto_meta(objeto_id: str, token: str) -> str:
    """Lê a conta dona de um conjunto/anúncio e confere a cerca antes de qualquer uso."""
    dados = meta_get(validar_id(objeto_id), token, fields="account_id")
    return conta_meta(dados["account_id"])


# ---------------------------------------------------------------------------
# Google Ads (API REST): acesso, consulta e cerca
# ---------------------------------------------------------------------------
_acesso = {}


def _token_google() -> str:
    if _acesso.get("expira", 0) > time.time() + 60:
        return _acesso["valor"]
    g = credenciais()["google"]
    corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": g["refresh_token"],
                                    "client_id": g["client_id"], "client_secret": g["client_secret"]}).encode()
    status, bruto = http("POST", "https://oauth2.googleapis.com/token", corpo,
                         {"Content-Type": "application/x-www-form-urlencoded"}, tempo=60)
    dados = json_de(bruto)
    if status != 200 or "access_token" not in dados:
        raise Erro("o Google recusou a chave de acesso. Avise o Diego (a chave pode ter sido revogada).")
    _acesso.update(valor=dados["access_token"], expira=time.time() + int(dados.get("expires_in", 3000)))
    return _acesso["valor"]


def _erro_google(dados) -> str:
    try:
        bloco = dados[0] if isinstance(dados, list) else dados
        erro = bloco["error"]
        for d in erro.get("details", []):
            for e in d.get("errors", []):
                if e.get("message"):
                    return e["message"]
        return erro.get("message", "erro desconhecido")
    except (KeyError, IndexError, TypeError, AttributeError):
        return "erro desconhecido"


_CHAMADA_GOOGLE = re.compile(r"customers/\d{6,12}/(googleAds:search|assets:mutate|adGroupAds:mutate)")


def google_chamar(mcc: str, caminho: str, corpo: dict) -> dict:
    """POST na API do Google Ads, sempre com uma MCC da cerca no cabeçalho."""
    if mcc not in GOOGLE_MCCS_PERMITIDAS:
        raise Erro(f"MCC {mcc} fora da AUVP.")
    if not _CHAMADA_GOOGLE.fullmatch(caminho):
        raise Erro(f"chamada recusada: '{caminho}'.")
    cab = {"Authorization": f"Bearer {_token_google()}", "developer-token": credenciais()["google"]["developer_token"],
           "login-customer-id": mcc, "Content-Type": "application/json"}
    status, bruto = http("POST", f"https://googleads.googleapis.com/{GOOGLE_API}/{caminho}",
                         json.dumps(corpo).encode("utf-8"), cab, tempo=120)
    dados = json_de(bruto)
    if status != 200:
        raise Erro(f"o Google recusou: {_erro_google(dados)}")
    return dados


def google_consultar(cid: str, mcc: str, gaql: str) -> list:
    linhas, corpo = [], {"query": gaql}
    while True:
        dados = google_chamar(mcc, f"customers/{cid}/googleAds:search", corpo)
        linhas += dados.get("results", [])
        if not dados.get("nextPageToken"):
            return linhas
        corpo["pageToken"] = dados["nextPageToken"]


def conta_google(conta: str) -> tuple:
    """Confere se a conta está na cerca. Devolve (customer_id, mcc que a gerencia)."""
    cid = validar_id(str(conta).replace("-", ""), "conta")
    for c in cerca()["google"]["contas"]:
        if c["id"] == cid:
            return cid, c["mcc"]
    raise Erro(f"a conta Google {cid} não é da AUVP. Esta skill só trabalha nas MCCs AUVP e The Brain.")


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
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
    if sys.version_info < (3, 9):
        falhar("precisa de Python 3.9 ou mais novo.")
    try:
        funcao()
    except Erro as e:
        falhar(_sem_segredo(str(e)))
    except KeyboardInterrupt:
        falhar("interrompido.")
    except Exception as e:
        falhar(_sem_segredo(f"falha inesperada ({type(e).__name__}): {e}"))
