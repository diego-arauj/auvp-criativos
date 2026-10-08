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

nucleo.garantir_venv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from nucleo import Erro  # noqa: E402


def cliente(conta: str):
    cid, mcc = nucleo.conta_google(conta)
    return cid, nucleo.cliente_google(mcc)


def consultar(cli, cid: str, gaql: str) -> list:
    from google.ads.googleads.errors import GoogleAdsException
    try:
        return list(cli.get_service("GoogleAdsService").search(customer_id=cid, query=gaql))
    except GoogleAdsException as e:
        raise Erro(f"o Google recusou a leitura: {e.failure.errors[0].message}")


def id_do_youtube(link: str) -> str:
    m = re.search(r"(?:youtu\.be/|shorts/|v=|embed/)([A-Za-z0-9_-]{11})", link or "")
    if not m:
        raise Erro(f"link do YouTube inválido: {link}")
    return m.group(1)


# ---------------------------------------------------------------------------
# ÚNICA porta de escrita: criar asset de vídeo do YouTube e criar anúncio PAUSADO.
# ---------------------------------------------------------------------------
def escrever_assets(cli, cid: str, videos: list) -> dict:
    """videos: [(youtube_id, nome)]. Só cria asset de vídeo do YouTube."""
    from google.ads.googleads.errors import GoogleAdsException
    ops = []
    for vid, nome in videos:
        op = cli.get_type("AssetOperation")
        op.create.name = nome
        op.create.youtube_video_asset.youtube_video_id = vid
        ops.append(op)
    try:
        r = cli.get_service("AssetService").mutate_assets(customer_id=cid, operations=ops)
    except GoogleAdsException as e:
        raise Erro(f"o Google recusou o vídeo: {e.failure.errors[0].message}")
    return {vid: res.resource_name for (vid, _), res in zip(videos, r.results)}


def escrever_anuncio(cli, cid: str, op) -> str:
    from google.ads.googleads.errors import GoogleAdsException
    if op.create.status != cli.enums.AdGroupAdStatusEnum.PAUSED:
        raise Erro("anúncio só pode nascer PAUSADO.")
    if not op.create.ad.demand_gen_video_responsive_ad.videos:
        raise Erro("esta skill só cria anúncio de vídeo Demand Gen.")
    if not op.create.ad_group.startswith(f"customers/{cid}/adGroups/"):
        raise Erro("grupo de anúncios fora da conta.")
    try:
        r = cli.get_service("AdGroupAdService").mutate_ad_group_ads(customer_id=cid, operations=[op])
    except GoogleAdsException as e:
        erro = e.failure.errors[0]
        raise Erro(f"o Google recusou o anúncio: {erro.message}")
    return r.results[0].resource_name


# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------
def cmd_contas(_args) -> None:
    for c in nucleo.cerca()["google"]["contas"]:
        print(f"  {c['id']}  {c['nome']}")


def cmd_grupos(args) -> None:
    cid, cli = cliente(args.conta)
    q = ("SELECT campaign.id, campaign.name, campaign.status, ad_group.id, ad_group.name, ad_group.status "
         "FROM ad_group WHERE campaign.advertising_channel_type = 'DEMAND_GEN' "
         "AND campaign.status != 'REMOVED' AND ad_group.status != 'REMOVED' ORDER BY campaign.name, ad_group.name")
    atual = None
    for r in consultar(cli, cid, q):
        if r.campaign.id != atual:
            atual = r.campaign.id
            print(f"\n{r.campaign.id}  [{r.campaign.status.name}]  {r.campaign.name}")
        print(f"    grupo {r.ad_group.id}  [{r.ad_group.status.name}]  {r.ad_group.name}")


def cmd_anuncios(args) -> None:
    cid, cli = cliente(args.conta)
    q = ("SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.ad.type "
         f"FROM ad_group_ad WHERE ad_group.id = {int(args.grupo)} AND ad_group_ad.status != 'REMOVED'")
    for r in consultar(cli, cid, q):
        a = r.ad_group_ad
        print(f"  {a.ad.id}  [{a.status.name}]  {a.ad.name}  ({a.ad.type_.name})")


def ler_molde(cli, cid: str, anuncio_id: str):
    q = ("SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.final_urls, "
         "ad_group_ad.ad.final_url_suffix, ad_group_ad.ad.tracking_url_template, "
         "ad_group_ad.ad.url_custom_parameters, ad_group_ad.ad.final_mobile_urls, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.headlines, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.business_name, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.logo_images, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.call_to_actions, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb1, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb2, "
         "ad_group_ad.ad.demand_gen_video_responsive_ad.videos "
         f"FROM ad_group_ad WHERE ad_group_ad.ad.id = {int(anuncio_id)}")
    linhas = consultar(cli, cid, q)
    if not linhas:
        raise Erro(f"anúncio-molde {anuncio_id} não encontrado nessa conta.")
    ad = linhas[0].ad_group_ad.ad
    if not ad.demand_gen_video_responsive_ad.videos:
        raise Erro("esse anúncio não serve de molde: escolha um anúncio de vídeo Demand Gen.")
    return ad


def resumo_molde(ad) -> list:
    dg = ad.demand_gen_video_responsive_ad
    return [
        f"Molde: {ad.name} ({ad.id})",
        f"Títulos: {' | '.join(t.text for t in dg.headlines)}",
        f"Títulos longos: {' | '.join(t.text for t in dg.long_headlines)}",
        f"Descrições: {' | '.join(t.text for t in dg.descriptions)}",
        f"Empresa: {dg.business_name.text}   Link: {', '.join(ad.final_urls)}",
    ]


def cmd_molde(args) -> None:
    cid, cli = cliente(args.conta)
    print("\n".join(resumo_molde(ler_molde(cli, cid, args.anuncio))))


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
    return plano


def conferir(cli, cid: str, plano: dict) -> dict:
    problemas = []
    molde = ler_molde(cli, cid, plano["molde_anuncio"])
    try:
        plano["grupos"] = [str(int(g)) for g in plano["grupos"]]
        plano["molde_anuncio"] = str(int(plano["molde_anuncio"]))
    except ValueError:
        raise Erro("IDs de grupo e de molde precisam ser só números.")
    ids = ", ".join(plano["grupos"])
    grupos = {str(r.ad_group.id): r.ad_group.name for r in consultar(cli, cid, (
        "SELECT ad_group.id, ad_group.name FROM ad_group WHERE campaign.advertising_channel_type = 'DEMAND_GEN' "
        f"AND ad_group.status != 'REMOVED' AND ad_group.id IN ({ids})"))}
    for g in plano["grupos"]:
        if str(g) not in grupos:
            problemas.append(f"grupo {g} não existe nessa conta ou não é Demand Gen.")
    ja = {}
    for r in consultar(cli, cid, f"SELECT ad_group.id, ad_group_ad.ad.name FROM ad_group_ad "
                                 f"WHERE ad_group.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'"):
        ja.setdefault(str(r.ad_group.id), set()).add(r.ad_group_ad.ad.name)
    vistos = set()
    for a in plano["anuncios"]:
        a["nome"] = nome = (a.get("nome") or "").strip()
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
    cid, cli = cliente(plano["conta"])
    ctx = conferir(cli, cid, plano)
    molde, grupos, ja = ctx["molde"], ctx["grupos"], ctx["ja"]

    print("PLANO DE SUBIDA (Google Demand Gen)")
    print(f"Conta: {cid}")
    print("\n".join(resumo_molde(molde)))
    print("Grupos: " + ", ".join(f"{n} ({g})" for g, n in grupos.items()))
    total = 0
    for a in plano["anuncios"]:
        for g in plano["grupos"]:
            existe = a["nome"].strip() in ja.get(str(g), set())
            total += 0 if existe else 1
            print(f"  {a['nome']} -> {grupos[str(g)]}" + ("  (já existe, pula)" if existe else ""))
    print(f"Anúncios novos: {total}, todos nascem PAUSADOS.")
    if not args.executar:
        print("\nNada foi enviado. Confira o plano com a pessoa e rode de novo com --executar.")
        return

    # Vídeos: reaproveita o asset se o vídeo já existe na conta
    precisa = {id_do_youtube(l): f"{a['nome'].strip()} - {i + 1}" for a in plano["anuncios"] for i, l in enumerate(a["videos"])}
    lista = ", ".join(f"'{v}'" for v in precisa)
    assets = {r.asset.youtube_video_asset.youtube_video_id: r.asset.resource_name for r in consultar(cli, cid, (
        "SELECT asset.resource_name, asset.youtube_video_asset.youtube_video_id FROM asset "
        f"WHERE asset.type = 'YOUTUBE_VIDEO' AND asset.youtube_video_asset.youtube_video_id IN ({lista})"))}
    faltam = [(v, n) for v, n in precisa.items() if v not in assets]
    if faltam:
        assets.update(escrever_assets(cli, cid, faltam))

    criados, falhas = [], []
    for a in plano["anuncios"]:
        nome = a["nome"].strip()
        for g in plano["grupos"]:
            if nome in ja.get(str(g), set()):
                continue
            op = cli.get_type("AdGroupAdOperation")
            novo = op.create
            novo.ad_group = f"customers/{cid}/adGroups/{int(g)}"
            novo.status = cli.enums.AdGroupAdStatusEnum.PAUSED
            novo.ad.name = nome
            novo.ad.final_urls.extend(molde.final_urls)
            if molde.final_url_suffix:
                novo.ad.final_url_suffix = molde.final_url_suffix
            if molde.tracking_url_template:
                novo.ad.tracking_url_template = molde.tracking_url_template
            novo.ad.final_mobile_urls.extend(molde.final_mobile_urls)
            for parametro in molde.url_custom_parameters:
                cp = cli.get_type("CustomParameter")
                cp.key, cp.value = parametro.key, parametro.value
                novo.ad.url_custom_parameters.append(cp)
            dg = novo.ad.demand_gen_video_responsive_ad
            dg._pb.CopyFrom(molde.demand_gen_video_responsive_ad._pb)
            del dg.videos[:]
            for link in a["videos"]:
                v = cli.get_type("AdVideoAsset")
                v.asset = assets[id_do_youtube(link)]
                dg.videos.append(v)
            try:
                criados.append((nome, grupos[str(g)], escrever_anuncio(cli, cid, op)))
            except Erro as e:
                falhas.append((nome, grupos[str(g)], str(e)))

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
    p = sub.add_parser("grupos"); p.add_argument("--conta", required=True)
    p = sub.add_parser("anuncios"); p.add_argument("--conta", required=True); p.add_argument("--grupo", required=True)
    p = sub.add_parser("molde"); p.add_argument("--conta", required=True); p.add_argument("--anuncio", required=True)
    p = sub.add_parser("subir"); p.add_argument("--plano", required=True); p.add_argument("--executar", action="store_true")
    args = ap.parse_args()
    {"contas": cmd_contas, "grupos": cmd_grupos, "anuncios": cmd_anuncios, "molde": cmd_molde,
     "subir": cmd_subir}[args.comando](args)


if __name__ == "__main__":
    nucleo.principal(main)
