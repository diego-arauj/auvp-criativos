"""Configura a skill: pede a senha mestra, abre o cofre e monta a lista de contas da AUVP.

Uso: python3 configurar.py
A senha é pedida numa janela própria do sistema; ela nunca passa pelo chat.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nucleo  # noqa: E402

import json  # noqa: E402

from nucleo import Erro  # noqa: E402

TITULO = "AUVP Criativos"
PERGUNTA = "Digite a senha mestra que você recebeu:"


def pedir_senha() -> str:
    """Abre uma janela com campo oculto. Funciona mesmo quando o Claude roda o script."""
    if sys.platform == "darwin":
        script = (f'display dialog "{PERGUNTA}" default answer "" with hidden answer '
                  f'with title "{TITULO}" buttons {{"Cancelar", "OK"}} default button "OK"\n'
                  'text returned of result')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            raise Erro("configuração cancelada.")
        return r.stdout.strip()
    if os.name == "nt":
        ps = ("$c = Get-Credential -UserName 'AUVP' -Message 'Senha mestra da skill AUVP Criativos'; "
              "if ($c) { $c.GetNetworkCredential().Password }")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            raise Erro("configuração cancelada.")
        return r.stdout.strip()
    try:
        import tkinter
        from tkinter import simpledialog
        raiz = tkinter.Tk()
        raiz.withdraw()
        senha = simpledialog.askstring(TITULO, PERGUNTA, show="*")
        raiz.destroy()
        if senha:
            return senha.strip()
    except Exception:
        pass
    if sys.stdin.isatty():
        import getpass
        return getpass.getpass(PERGUNTA + " ").strip()
    raise Erro("não consegui abrir a janela da senha. Rode este comando num terminal: "
               f"python3 {os.path.abspath(__file__)}")


def cerca_meta(token: str) -> dict:
    contas, paginas, instagram = {}, {}, {}
    for bm in nucleo.META_BMS_PERMITIDAS:
        for aresta in ("owned_ad_accounts", "client_ad_accounts"):
            for c in nucleo.meta_paginar(f"{bm}/{aresta}", token, fields="account_id,name,account_status", limit=200):
                contas[c["account_id"]] = {"id": c["account_id"], "nome": c["name"], "ativa": c.get("account_status") == 1}
        for aresta in ("owned_pages", "client_pages"):
            for p in nucleo.meta_paginar(f"{bm}/{aresta}", token, fields="id,name", limit=200):
                paginas[p["id"]] = {"id": p["id"], "nome": p["name"]}
        for i in nucleo.meta_paginar(f"{bm}/instagram_accounts", token, fields="id,username", limit=200):
            instagram[i["id"]] = {"id": i["id"], "nome": "@" + i.get("username", "")}
    return {"contas": sorted(contas.values(), key=lambda c: c["nome"]),
            "paginas": sorted(paginas.values(), key=lambda p: p["nome"]),
            "instagram": sorted(instagram.values(), key=lambda i: i["nome"])}


def cerca_google() -> dict:
    contas = []
    consulta = ("SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, "
                "customer_client.status FROM customer_client")
    for mcc in nucleo.GOOGLE_MCCS_PERMITIDAS:
        for linha in nucleo.google_consultar(mcc, mcc, consulta):
            cc = linha.get("customerClient", {})
            if cc.get("manager") or cc.get("status") != "ENABLED":
                continue
            contas.append({"id": str(cc["id"]), "nome": cc.get("descriptiveName", ""), "mcc": mcc})
    return {"contas": contas}


def main() -> None:
    if not nucleo.COFRE.exists():
        raise Erro("cofre de chaves não encontrado no plugin. Atualize o plugin e tente de novo.")
    cofre = json.loads(nucleo.COFRE.read_text(encoding="utf-8"))
    print("Abrindo a janela da senha mestra...", file=sys.stderr)
    chaves = nucleo.abrir(cofre, pedir_senha())
    nucleo.gravar_privado(nucleo.CREDENCIAIS, chaves)

    print("Senha aceita. Conferindo o acesso às contas da AUVP...", file=sys.stderr)
    cerca = {"meta": cerca_meta(chaves["meta"]["token"]), "google": cerca_google()}
    nucleo.gravar_privado(nucleo.CERCA, cerca)

    print("\nCONFIGURAÇÃO CONCLUÍDA\n")
    print(f"Meta: {len(cerca['meta']['contas'])} contas de anúncio, "
          f"{len(cerca['meta']['paginas'])} páginas, {len(cerca['meta']['instagram'])} perfis de Instagram")
    for c in cerca["meta"]["contas"]:
        print(f"  {c['id']}  {c['nome']}{'' if c['ativa'] else '  (inativa)'}")
    print(f"Google: {len(cerca['google']['contas'])} contas de anúncio")
    for c in cerca["google"]["contas"]:
        print(f"  {c['id']}  {c['nome']}")
    print("\nPróximo passo: peça ao Claude 'como eu uso?' ou já mande o criativo e o destino.")


if __name__ == "__main__":
    nucleo.principal(main)
