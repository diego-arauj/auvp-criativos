"""Sobe criativo de vídeo no Google Ads (Demand Gen) nas contas da AUVP. Só isso.

O vídeo precisa já estar no YouTube (não listado). A skill não sobe no YouTube.

Comandos (todos de leitura, menos 'subir --executar'):
  contas                                   contas liberadas
  grupos     --conta ID                    campanhas Demand Gen e seus grupos de anúncios
  anuncios   --conta ID --grupo ID         anúncios de vídeo de um grupo (para escolher o molde)
  molde      --conta ID --anuncio ID       mostra o que será copiado do anúncio-molde
  subir      --plano ARQUIVO.json          confere tudo e mostra o plano (não sobe nada)
  subir      --plano ARQUIVO.json --executar   sobe de verdade, sempre PAUSADO

Regra da casa: o anúncio novo copia do molde títulos, descrições, nome da empresa, logo, botão e
link. Só os vídeos mudam.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nucleo  # noqa: E402

import argparse  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from nucleo import Erro  # noqa: E402

CAMPOS_MOLDE = (
    "ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.final_urls, ad_group_ad.ad.final_mobile_urls, "
    "ad_group_ad.ad.final_url_suffix, ad_group_ad.ad.tracking_url_template, ad_group_ad.ad.url_custom_parameters, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.headlines, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.business_name, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.logo_images, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.call_to_actions, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb1, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb2, "
    "ad_group_ad.ad.demand_gen_video_responsive_ad.videos"
)
CAMPOS_COPIADOS_DO_ANUNCIO = ("finalUrls", "finalMobileUrls", "finalUrlSuffix", "trackingUrlTemplate", "urlCustomParameters")


def numero(valor, nome: str) -> str:
    v = str(valor).strip()
    if not re.fullmatch(r"\d{4,20}", v):
        raise Erro(f"{nome} inválido: '{v}'. Use só os números.")
    return v


def id_do_youtube(link: str) -> str:
    m = re.search(r"(?:youtu\.be/|shorts/|v=|embed/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", link or "")
    if not m:
        raise Erro(f"link do YouTube inválido: {link}")
    return m.group(1)


# ---------------------------------------------------------------------------
# ÚNICA porta de escrita: criar vídeo do YouTube como recurso e criar anúncio PAUSADO.
# ---------------------------------------------------------------------------
def escrever_assets(cid: str, mcc: str, videos: list) -> dict:
    """videos: [(youtube_id, nome)]. Só cria recurso de vídeo do YouTube."""
    ops = [{"create": {"name": nome, "youtubeVideoAsset": {"youtubeVideoId": vid}}} for vid, nome in videos]
    r = nucleo.google_chamar(mcc, f"customers/{cid}/assets:mutate", {"operations": ops})
    return {vid: res["resourceName"] for (vid, _), res in zip(videos, r.get("results", []))}


def escrever_anuncio(cid: str, mcc: str, criar: dict) -> str:
    if set(criar) != {"adGroup", "status", "ad"} or criar["status"] != "PAUSED":
        raise Erro("anúncio só pode nascer PAUSADO, sem outros campos.")
    if not re.fullmatch(rf"customers/{cid}/adGroups/\d{{4,20}}", criar["adGroup"]):
        raise Erro("grupo de anúncios fora da conta.")
    if not criar["ad"].get("demandGenVideoResponsiveAd", {}).get("videos"):
        raise Erro("esta skill só cria anúncio de vídeo Demand Gen.")
    r = nucleo.google_chamar(mcc, f"customers/{cid}/adGroupAds:mutate", {"operations": [{"create": criar}]})
    return r["results"][0]["resourceName"]


# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------
def consultar(conta: str, gaql: str) -> tuple:
    cid, mcc = nucleo.conta_google(conta)
    return cid, mcc, nucleo.google_consultar(cid, mcc, gaql)


def cmd_contas(_args) -> None:
    for c in nucleo.cerca()["google"]["contas"]:
        print(f"  {c['id']}  {c['nome']}")


def cmd_grupos(args) -> None:
    _, _, linhas = consultar(args.conta, (
        "SELECT campaign.id, campaign.name, campaign.status, ad_group.id, ad_group.name, ad_group.status "
        "FROM ad_group WHERE campaign.advertising_channel_type = 'DEMAND_GEN' "
        + ("AND campaign.status != 'REMOVED' " if args.todas else "AND campaign.status = 'ENABLED' ")
        + "AND ad_group.status != 'REMOVED' ORDER BY campaign.name, ad_group.name"))
    if not args.todas:
        print("(só campanhas ativas; use --todas para ver as pausadas)")
    atual = None
    for r in linhas:
        c, g = r["campaign"], r["adGroup"]
        if c["id"] != atual:
            atual = c["id"]
            print(f"\n{c['id']}  [{c.get('status')}]  {c.get('name')}")
        print(f"    grupo {g['id']}  [{g.get('status')}]  {g.get('name')}")


def cmd_anuncios(args) -> None:
    grupo = numero(args.grupo, "grupo")
    _, _, linhas = consultar(args.conta, (
        "SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.ad.type "
        f"FROM ad_group_ad WHERE ad_group.id = {grupo} AND ad_group_ad.status != 'REMOVED'"))
    for r in linhas:
        a = r["adGroupAd"]
        print(f"  {a['ad']['id']}  [{a.get('status')}]  {a['ad'].get('name', '')}  ({a['ad'].get('type', '')})")


def ler_molde(cid: str, mcc: str, anuncio_id: str) -> dict:
    anuncio_id = numero(anuncio_id, "anúncio-molde")
    linhas = nucleo.google_consultar(cid, mcc, f"SELECT {CAMPOS_MOLDE} FROM ad_group_ad WHERE ad_group_ad.ad.id = {anuncio_id}")
    if not linhas:
        raise Erro(f"anúncio-molde {anuncio_id} não encontrado nessa conta.")
    ad = linhas[0]["adGroupAd"]["ad"]
    if not ad.get("demandGenVideoResponsiveAd", {}).get("videos"):
        raise Erro("esse anúncio não serve de molde: escolha um anúncio de vídeo Demand Gen.")
    return ad


def resumo_molde(ad: dict) -> list:
    dg = ad["demandGenVideoResponsiveAd"]
    textos = lambda k: " | ".join(t.get("text", "") for t in dg.get(k, []))
    return [
        f"Molde: {ad.get('name', '')} ({ad['id']})",
        f"Títulos: {textos('headlines')}",
        f"Títulos longos: {textos('longHeadlines')}",
        f"Descrições: {textos('descriptions')}",
        f"Empresa: {dg.get('businessName', {}).get('text', '')}   Link: {', '.join(ad.get('finalUrls', []))}",
    ]


def cmd_molde(args) -> None:
    cid, mcc = nucleo.conta_google(args.conta)
    print("\n".join(resumo_molde(ler_molde(cid, mcc, args.anuncio))))


# ---------------------------------------------------------------------------
# Subir
# ---------------------------------------------------------------------------
def carregar_plano(caminho: str) -> dict:
    p = Path(caminho).expanduser()
    if not p.exists():
        raise Erro(f"plano não encontrado: {p}")
    plano = json.loads(p.read_text(encoding="utf-8"))
    for campo in ("conta", "molde_anuncio", "grupos", "anuncios"):
        if not plano.get(campo):
            raise Erro(f"o plano precisa do campo '{campo}'. Veja o modelo no SKILL.md.")
    plano["grupos"] = [numero(g, "grupo") for g in plano["grupos"]]
    plano["molde_anuncio"] = numero(plano["molde_anuncio"], "anúncio-molde")
    for a in plano["anuncios"]:
        a["nome"] = str(a.get("nome") or "").strip()
    return plano


def conferir(cid: str, mcc: str, plano: dict) -> dict:
    problemas = []
    molde = ler_molde(cid, mcc, plano["molde_anuncio"])
    ids = ", ".join(plano["grupos"])
    grupos = {r["adGroup"]["id"]: r["adGroup"]["name"] for r in nucleo.google_consultar(cid, mcc, (
        "SELECT ad_group.id, ad_group.name FROM ad_group WHERE campaign.advertising_channel_type = 'DEMAND_GEN' "
        f"AND ad_group.status != 'REMOVED' AND ad_group.id IN ({ids})"))}
    for g in plano["grupos"]:
        if g not in grupos:
            problemas.append(f"grupo {g} não existe nessa conta ou não é Demand Gen.")
    ja = {}
    for r in nucleo.google_consultar(cid, mcc, f"SELECT ad_group.id, ad_group_ad.ad.name FROM ad_group_ad "
                                              f"WHERE ad_group.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'"):
        ja.setdefault(r["adGroup"]["id"], set()).add(r["adGroupAd"]["ad"].get("name", ""))
    vistos = set()
    for a in plano["anuncios"]:
        nome = a["nome"]
        if not nome:
            problemas.append("há anúncio sem nome no plano.")
        if nome in vistos:
            problemas.append(f"nome repetido no plano: {nome}")
        vistos.add(nome)
        if not a.get("videos"):
            problemas.append(f"{nome}: falta o link do vídeo no YouTube.")
        for link in a.get("videos", []):
            try:
                id_do_youtube(link)
            except Erro as e:
                problemas.append(f"{nome}: {e}")
    if problemas:
        raise Erro("o plano tem problemas:\n  - " + "\n  - ".join(problemas))
    return {"molde": molde, "grupos": grupos, "ja": ja}


def cmd_subir(args) -> None:
    plano = carregar_plano(args.plano)
    cid, mcc = nucleo.conta_google(plano["conta"])
    ctx = conferir(cid, mcc, plano)
    molde, grupos, ja = ctx["molde"], ctx["grupos"], ctx["ja"]

    print("PLANO DE SUBIDA (Google Demand Gen)")
    print(f"Conta: {cid}")
    print("\n".join(resumo_molde(molde)))
    print("Grupos: " + ", ".join(f"{n} ({g})" for g, n in grupos.items()))
    total = 0
    for a in plano["anuncios"]:
        for g in plano["grupos"]:
            existe = a["nome"] in ja.get(g, set())
            total += 0 if existe else 1
            print(f"  {a['nome']} -> {grupos[g]}" + ("  (já existe, pula)" if existe else ""))
    print(f"Anúncios novos: {total}, todos nascem PAUSADOS.")
    if not args.executar:
        print("\nNada foi enviado. Confira o plano com a pessoa e rode de novo com --executar.")
        return

    # Vídeos: reaproveita o recurso se o vídeo já existe na conta
    precisa = {id_do_youtube(l): f"{a['nome']} - {i + 1}" for a in plano["anuncios"] for i, l in enumerate(a["videos"])}
    lista = ", ".join(f"'{v}'" for v in precisa)
    assets = {r["asset"]["youtubeVideoAsset"]["youtubeVideoId"]: r["asset"]["resourceName"]
              for r in nucleo.google_consultar(cid, mcc, (
                  "SELECT asset.resource_name, asset.youtube_video_asset.youtube_video_id FROM asset "
                  f"WHERE asset.type = 'YOUTUBE_VIDEO' AND asset.youtube_video_asset.youtube_video_id IN ({lista})"))}
    faltam = [(v, n) for v, n in precisa.items() if v not in assets]
    if faltam:
        assets.update(escrever_assets(cid, mcc, faltam))

    criados, falhas = [], []
    for a in plano["anuncios"]:
        for g in plano["grupos"]:
            if a["nome"] in ja.get(g, set()):
                continue
            ad = {k: copy.deepcopy(molde[k]) for k in CAMPOS_COPIADOS_DO_ANUNCIO if molde.get(k)}
            ad["name"] = a["nome"]
            dg = copy.deepcopy(molde["demandGenVideoResponsiveAd"])
            dg["videos"] = [{"asset": assets[id_do_youtube(l)]} for l in a["videos"]]
            ad["demandGenVideoResponsiveAd"] = dg
            try:
                rn = escrever_anuncio(cid, mcc, {"adGroup": f"customers/{cid}/adGroups/{g}", "status": "PAUSED", "ad": ad})
                criados.append((a["nome"], grupos[g], rn))
            except Erro as e:
                falhas.append((a["nome"], grupos[g], str(e)))

    print("\nUPLOAD FINALIZADO" if not falhas else "\nUPLOAD COM PENDÊNCIAS")
    print(f"Conta: {cid}  Status: PAUSADO  Criados: {len(criados)}  Falhas: {len(falhas)}")
    for nome, grupo, rn in criados:
        print(f"  {nome} -> {grupo}  ID {rn.split('~')[-1]}")
    for nome, grupo, erro in falhas:
        print(f"  FALHA {nome} -> {grupo}: {erro}")
    print("Próximo passo: o responsável pela conta revisa e ativa no Google Ads.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sobe vídeo do YouTube como anúncio Demand Gen nas contas da AUVP.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("contas")
    p = sub.add_parser("grupos"); p.add_argument("--conta", required=True); p.add_argument("--todas", action="store_true")
    p = sub.add_parser("anuncios"); p.add_argument("--conta", required=True); p.add_argument("--grupo", required=True)
    p = sub.add_parser("molde"); p.add_argument("--conta", required=True); p.add_argument("--anuncio", required=True)
    p = sub.add_parser("subir"); p.add_argument("--plano", required=True); p.add_argument("--executar", action="store_true")
    args = ap.parse_args()
    {"contas": cmd_contas, "grupos": cmd_grupos, "anuncios": cmd_anuncios, "molde": cmd_molde,
     "subir": cmd_subir}[args.comando](args)


if __name__ == "__main__":
    nucleo.principal(main)
