"""Sobe criativo na Meta (Facebook/Instagram) nas contas da AUVP. Só isso.

Comandos (todos de leitura, menos 'subir --executar'):
  contas                                   contas, páginas e Instagram liberados
  campanhas  --conta ID                    campanhas da conta
  conjuntos  --conta ID --campanha ID      conjuntos de uma campanha
  anuncios   --conjunto ID                 anúncios de um conjunto (para escolher o molde)
  molde      --anuncio ID                  mostra o que será copiado do anúncio-molde
  subir      --plano ARQUIVO.json          confere tudo e mostra o plano (não sobe nada)
  subir      --plano ARQUIVO.json --executar   sobe de verdade, sempre PAUSADO

Regra da casa: o criativo novo copia do anúncio-molde o texto, o título, o botão, o link, as UTMs,
a página, o Instagram e o rastreamento. Só a mídia muda. Nada é escrito do zero.
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
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import urllib.parse  # noqa: E402

from nucleo import Erro  # noqa: E402

GRAPH = f"https://graph.facebook.com/{nucleo.META_API}"
GRAPH_VIDEO = f"https://graph-video.facebook.com/{nucleo.META_API}"
VIDEO = {".mp4", ".mov", ".m4v"}
IMAGEM = {".jpg", ".jpeg", ".png"}
PEDACO = 4 * 1024 * 1024

CAMPOS_CRIATIVO = (
    "id,name,url_tags,instagram_user_id,degrees_of_freedom_spec,asset_feed_spec,object_type,"
    "object_story_spec{page_id,instagram_user_id,"
    "video_data{video_id,title,message,link_description,call_to_action,image_url,image_hash},"
    "link_data{link,message,name,description,caption,call_to_action,image_hash,picture}}"
)


def token() -> str:
    return nucleo.credenciais()["meta"]["token"]


def ler(caminho: str, **params) -> dict:
    return nucleo.meta_get(caminho, token(), **params)


# ---------------------------------------------------------------------------
# ÚNICA porta de escrita. Qualquer outro destino é recusado aqui.
# ---------------------------------------------------------------------------
_ESCRITA_PERMITIDA = re.compile(r"act_\d{5,25}/(advideos|adimages|adcreatives|ads)")


def escrever(caminho: str, dados: dict, arquivos: dict = None, tok: str = None, video: bool = False) -> dict:
    if not _ESCRITA_PERMITIDA.fullmatch(caminho):
        raise Erro(f"escrita recusada em '{caminho}': esta skill só sobe mídia, cria criativo e cria anúncio pausado.")
    nucleo.conta_meta(caminho.split("/")[0])
    if caminho.endswith("/ads") and dados.get("status") != "PAUSED":
        raise Erro("anúncio só pode nascer PAUSADO.")
    if caminho.endswith("/ads") and set(dados) - {"name", "adset_id", "creative", "status", "tracking_specs", "conversion_domain"}:
        raise Erro("campo não permitido na criação do anúncio.")
    corpo = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in dados.items()}
    corpo["access_token"] = tok or token()
    # Envio de mídia pode repetir sem risco. Criativo e anúncio não: repetir às cegas duplicaria.
    tentativas = 5 if caminho.endswith(("/advideos", "/adimages")) else 1
    for tentativa in range(1, tentativas + 1):
        if arquivos:
            bruto, cab = nucleo.multipart(corpo, arquivos)
        else:
            bruto, cab = urllib.parse.urlencode(corpo).encode(), {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            resposta = nucleo.json_de(nucleo.http("POST", f"{GRAPH_VIDEO if video else GRAPH}/{caminho}", bruto, cab, 300)[1])
        except Erro:
            if tentativa == tentativas:
                raise Erro("a Meta não respondeu. Rode o mesmo comando de novo: o que já subiu não repete.")
            time.sleep(tentativa * 3)
            continue
        erro = resposta.get("error")
        if not erro:
            time.sleep(1)
            return resposta
        if erro.get("code") == 17 or erro.get("error_subcode") == 2446079:
            raise Erro("a Meta pediu uma pausa (limite de chamadas da conta). Espere 5 minutos e rode o mesmo comando de novo.")
        detalhe = erro.get("error_user_msg") or erro.get("message")
        raise Erro(f"a Meta recusou ({erro.get('code')}/{erro.get('error_subcode')}): {detalhe}")
    raise Erro("falha inesperada na escrita.")


# ---------------------------------------------------------------------------
# Leituras para escolher destino e molde
# ---------------------------------------------------------------------------
def cmd_contas(_args) -> None:
    c = nucleo.cerca()["meta"]
    print("CONTAS DE ANÚNCIO")
    for x in c["contas"]:
        print(f"  {x['id']}  {x['nome']}{'' if x['ativa'] else '  (inativa)'}")
    print("PÁGINAS")
    for x in c["paginas"]:
        print(f"  {x['id']}  {x['nome']}")
    print("INSTAGRAM")
    for x in c["instagram"]:
        print(f"  {x['id']}  {x['nome']}")


def cmd_campanhas(args) -> None:
    conta = nucleo.conta_meta(args.conta)
    status = ["ACTIVE", "PAUSED"] if args.todas else ["ACTIVE"]
    itens = nucleo.meta_paginar(f"{conta}/campaigns", token(), fields="id,name,effective_status,objective", limit=200,
                                effective_status=json.dumps(status))
    if not args.todas:
        print("(só as ativas; use --todas para ver as pausadas)")
    for c in sorted(itens, key=lambda c: c["name"]):
        print(f"  {c['id']}  [{c['effective_status']}]  {c['name']}  ({c.get('objective', '')})")


def cmd_conjuntos(args) -> None:
    campanha = nucleo.validar_id(args.campanha, "campanha")
    nucleo.conta_do_objeto_meta(campanha, token())
    itens = nucleo.meta_paginar(f"{campanha}/adsets", token(), fields="id,name,effective_status,is_dynamic_creative",
                                limit=200, effective_status=json.dumps(["ACTIVE", "PAUSED"]))
    for s in sorted(itens, key=lambda s: s["name"]):
        dinamico = "  (criativo dinâmico: aceita 1 anúncio só)" if s.get("is_dynamic_creative") else ""
        print(f"  {s['id']}  [{s['effective_status']}]  {s['name']}{dinamico}")


def cmd_anuncios(args) -> None:
    conjunto = nucleo.validar_id(args.conjunto, "conjunto")
    nucleo.conta_do_objeto_meta(conjunto, token())
    itens = nucleo.meta_paginar(f"{conjunto}/ads", token(), fields="id,name,effective_status,creative{id}", limit=200)
    for a in sorted(itens, key=lambda a: a["name"]):
        print(f"  {a['id']}  [{a['effective_status']}]  {a['name']}")


def ler_molde(anuncio_id: str) -> dict:
    anuncio_id = nucleo.validar_id(anuncio_id, "anúncio-molde")
    nucleo.conta_do_objeto_meta(anuncio_id, token())
    ad = ler(anuncio_id, fields="id,name,account_id,adset_id,tracking_specs,conversion_domain,creative{id}")
    cr = ler(ad["creative"]["id"], fields=CAMPOS_CRIATIVO)
    spec = cr.get("object_story_spec") or {}
    if cr.get("asset_feed_spec") or not (spec.get("video_data") or spec.get("link_data")):
        raise Erro("esse anúncio não serve de molde: ele é flexível, dinâmico ou feito a partir de um post. "
                   "Escolha um anúncio simples de vídeo ou de imagem.")
    tipo = "video" if spec.get("video_data") else "imagem"
    if tipo == "imagem" and not spec["link_data"].get("image_hash"):
        raise Erro("esse anúncio de imagem não serve de molde (carrossel ou sem imagem própria).")
    nucleo.pagina_meta(spec["page_id"])
    ig = spec.get("instagram_user_id") or cr.get("instagram_user_id")
    if ig:
        nucleo.instagram_meta(ig)
    return {"anuncio": ad, "criativo": cr, "tipo": tipo, "instagram": ig}


def resumo_molde(m: dict) -> list:
    spec = m["criativo"]["object_story_spec"]
    d = spec.get("video_data") or spec.get("link_data")
    cta = (d.get("call_to_action") or {})
    link = (cta.get("value") or {}).get("link") or d.get("link")
    texto = (d.get("message") or "").replace("\n", " ")
    return [
        f"Molde: {m['anuncio']['name']} ({m['anuncio']['id']}), {m['tipo']}",
        f"Página: {spec['page_id']}  Instagram: {m['instagram'] or 'nenhum'}",
        f"Texto: {texto[:140] + ('...' if len(texto) > 140 else '') if texto else '(sem texto)'}",
        f"Título: {d.get('title') or d.get('name') or '(sem título)'}",
        f"Botão: {cta.get('type', '(sem botão)')}  Link: {link}",
        f"UTMs: {m['criativo'].get('url_tags') or '(sem UTM)'}",
    ]


def cmd_molde(args) -> None:
    print("\n".join(resumo_molde(ler_molde(args.anuncio))))


# ---------------------------------------------------------------------------
# Subir
# ---------------------------------------------------------------------------
def tipo_arquivo(caminho: Path) -> str:
    ext = caminho.suffix.lower()
    if ext in VIDEO:
        return "video"
    if ext in IMAGEM:
        return "imagem"
    raise Erro(f"formato não aceito: {caminho.name}. Vídeo: mp4/mov. Imagem: jpg/png.")


def medidas(caminho: Path):
    """Largura e altura pelo ffprobe, se existir na máquina."""
    import shutil
    import subprocess
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", str(caminho)], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("x")[:2]
        return int(w), int(h)
    except ValueError:
        return None


def carregar_plano(caminho: str) -> dict:
    p = Path(caminho).expanduser()
    if not p.exists():
        raise Erro(f"plano não encontrado: {p}")
    plano = json.loads(p.read_text(encoding="utf-8"))
    for campo in ("conjunto", "molde_anuncio", "anuncios"):
        if not plano.get(campo):
            raise Erro(f"o plano precisa do campo '{campo}'. Veja o modelo no SKILL.md.")
    plano["conjunto"] = nucleo.validar_id(plano["conjunto"], "conjunto")
    plano["molde_anuncio"] = nucleo.validar_id(plano["molde_anuncio"], "anúncio-molde")
    for a in plano["anuncios"]:
        a["nome"] = str(a.get("nome") or "").strip()
    plano["_estado"] = p.with_name(p.stem + ".estado.json")
    return plano


def carregar_estado(plano: dict, conta: str) -> dict:
    """Andamento de uma subida já começada. Só vale para o mesmo conjunto e o mesmo molde."""
    if not plano["_estado"].exists():
        return {"conjunto": plano["conjunto"], "molde": plano["molde_anuncio"], "itens": {}}
    estado = json.loads(plano["_estado"].read_text(encoding="utf-8"))
    if estado.get("conjunto") != plano["conjunto"] or estado.get("molde") != plano["molde_anuncio"]:
        raise Erro("este plano já foi usado com outro conjunto ou outro molde. Crie um arquivo de plano novo.")
    for item in estado.get("itens", {}).values():
        for chave in ("video_id", "criativo", "anuncio"):
            if item.get(chave):
                nucleo.validar_id(item[chave])
        if item.get("anuncio") and nucleo.conta_do_objeto_meta(item["anuncio"], token()) != conta:
            raise Erro("o andamento salvo aponta para outra conta. Crie um arquivo de plano novo.")
    return estado


def conferir(plano: dict) -> dict:
    """Todas as checagens antes de subir. Devolve o contexto pronto para executar."""
    conta = nucleo.conta_do_objeto_meta(plano["conjunto"], token())
    conjunto = ler(plano["conjunto"], fields="id,name,is_dynamic_creative,effective_status")
    molde = ler_molde(plano["molde_anuncio"])
    if f"act_{molde['anuncio']['account_id']}" != conta:
        raise Erro("o anúncio-molde é de outra conta. Use um molde da mesma conta do conjunto.")
    avisos, problemas = [], []

    estado = carregar_estado(plano, conta)
    feitos = {i.get("anuncio") for i in estado["itens"].values() if i.get("anuncio")}
    existentes = nucleo.meta_paginar(f"{plano['conjunto']}/ads", token(), fields="id,name", limit=200)
    pendentes = [a for a in plano["anuncios"] if not estado["itens"].get(a["nome"], {}).get("anuncio")]
    if conjunto.get("is_dynamic_creative") and len([x for x in existentes if x["id"] not in feitos]) + len(pendentes) > 1:
        problemas.append("o conjunto é de criativo dinâmico e aceita 1 anúncio só.")

    nomes_conta = set()
    for a in plano["anuncios"]:
        if a.get("nome"):
            nomes_conta |= {x["name"] for x in nucleo.meta_paginar(
                f"{conta}/ads", token(), fields="name", limit=50,
                filtering=json.dumps([{"field": "name", "operator": "EQUAL", "value": a["nome"]}]))}
    vistos = set()
    for a in plano["anuncios"]:
        nome, arq = a["nome"], Path(a.get("arquivo", "")).expanduser()
        if not nome:
            problemas.append("há anúncio sem nome no plano.")
            continue
        if nome in vistos:
            problemas.append(f"nome repetido no plano: {nome}")
        vistos.add(nome)
        if nome in nomes_conta and not estado["itens"].get(nome, {}).get("criativo"):
            problemas.append(f"já existe anúncio chamado '{nome}' na conta. O nome vira a utm_content: use outro.")
        if nome.endswith("- Copy") or "- Cópia" in nome:
            problemas.append(f"nome com sufixo de cópia: {nome}")
        if not arq.exists():
            problemas.append(f"arquivo não encontrado: {arq}")
            continue
        if tipo_arquivo(arq) != molde["tipo"]:
            problemas.append(f"{arq.name} é {tipo_arquivo(arq)}, mas o molde é {molde['tipo']}. Não se mistura vídeo e imagem.")
        tamanho = arq.stat().st_size / 1024 / 1024
        if molde["tipo"] == "video" and tamanho > 1000:
            problemas.append(f"{arq.name} tem {tamanho:.0f} MB. Exporte de novo em 1080x1920 antes de subir.")
        elif molde["tipo"] == "video" and tamanho > 200:
            avisos.append(f"{arq.name} tem {tamanho:.0f} MB: vai demorar. Se travar, exporte em 1080x1920.")
        m = medidas(arq)
        if m and molde["tipo"] == "video":
            w, h = m
            if w > 1080 * 1.5:
                avisos.append(f"{arq.name} está em {w}x{h}. Vídeo 4K costuma ser recusado: prefira 1080x1920.")
            if abs(w / h - 9 / 16) > 0.02:
                avisos.append(f"{arq.name} está em {w}x{h}, não é 9:16. As contas da AUVP rodam no formato vertical.")
    if problemas:
        raise Erro("o plano tem problemas:\n  - " + "\n  - ".join(problemas))
    return {"conta": conta, "conjunto": conjunto, "molde": molde, "avisos": avisos, "estado": estado}


def subir_video(conta: str, arq: Path) -> str:
    inicio = escrever(f"{conta}/advideos", {"upload_phase": "start", "file_size": arq.stat().st_size}, video=True)
    sessao, video_id = inicio["upload_session_id"], inicio["video_id"]
    ini, fim = int(inicio["start_offset"]), int(inicio["end_offset"])
    with open(arq, "rb") as f:
        while ini != fim:
            f.seek(ini)
            pedaco = f.read(min(fim, ini + PEDACO) - ini)
            r = escrever(f"{conta}/advideos", {"upload_phase": "transfer", "upload_session_id": sessao, "start_offset": ini},
                         arquivos={"video_file_chunk": (arq.name, pedaco)}, video=True)
            ini, fim = int(r["start_offset"]), int(r["end_offset"])
            print(f"    enviado {ini * 100 // max(arq.stat().st_size, 1)}%", file=sys.stderr)
    escrever(f"{conta}/advideos", {"upload_phase": "finish", "upload_session_id": sessao, "title": arq.stem}, video=True)
    return video_id


def capa_do_video(video_id: str) -> str:
    for tentativa in range(1, 61):
        d = ler(video_id, fields="status,picture")
        status = (d.get("status") or {}).get("video_status", "")
        if status == "error":
            raise Erro(f"a Meta não conseguiu processar o vídeo {video_id}. Exporte de novo em 1080x1920 (H.264).")
        if d.get("picture") and status in ("ready", "published"):
            return d["picture"]
        print(f"    processando o vídeo ({tentativa}/60)...", file=sys.stderr)
        time.sleep(15)
    raise Erro("o vídeo demorou demais para processar. Rode o mesmo comando de novo daqui a alguns minutos.")


def subir_imagem(conta: str, arq: Path) -> str:
    with open(arq, "rb") as f:
        r = escrever(f"{conta}/adimages", {}, arquivos={"filename": (arq.name, f.read())})
    return next(iter(r["images"].values()))["hash"]


def token_da_pagina(pagina: str) -> str:
    try:
        return ler(pagina, fields="access_token").get("access_token") or token()
    except Erro:
        return token()


def montar_criativo(molde: dict, nome: str, midia: dict) -> dict:
    cr = molde["criativo"]
    spec = copy.deepcopy(cr["object_story_spec"])
    spec.pop("id", None)
    if molde["tipo"] == "video":
        vd = spec["video_data"]
        vd["video_id"] = midia["video_id"]
        vd["image_url"] = midia["capa"]
        vd.pop("image_hash", None)
    else:
        ld = spec["link_data"]
        ld["image_hash"] = midia["hash"]
        ld.pop("picture", None)
    dados = {"name": f"CR_{nome}", "object_story_spec": spec}
    if molde["instagram"]:
        dados["instagram_user_id"] = molde["instagram"]
        spec["instagram_user_id"] = molde["instagram"]
    if cr.get("url_tags"):
        dados["url_tags"] = cr["url_tags"]
    dof = copy.deepcopy(cr.get("degrees_of_freedom_spec") or {})
    (dof.get("creative_features_spec") or {}).pop("standard_enhancements", None)
    if dof.get("creative_features_spec"):
        dados["degrees_of_freedom_spec"] = dof
    return dados


def rastreamento_do_molde(specs) -> list:
    """Do molde, só o rastreamento de pixel e conversão. O de engajamento (post, página) aponta para o
    post do molde; a Meta gera o certo sozinha para o post novo (conferido em 08/10/2026)."""
    return [x for x in (specs or []) if not ({"post", "post.wall", "page"} & set(x))]


def conferir_criativo(criativo_id: str, molde: dict) -> list:
    """Relê o criativo novo por inteiro e compara com o molde."""
    novo = ler(criativo_id, fields=CAMPOS_CRIATIVO)
    falhas = []
    chave = "video_data" if molde["tipo"] == "video" else "link_data"
    a = molde["criativo"]["object_story_spec"][chave]
    b = (novo.get("object_story_spec") or {}).get(chave) or {}
    for campo in ("message", "title", "name", "description", "link_description", "link", "call_to_action"):
        if a.get(campo) != b.get(campo):
            falhas.append(f"'{campo}' diferente do molde")
    if (molde["criativo"].get("url_tags") or "") != (novo.get("url_tags") or ""):
        falhas.append("UTMs diferentes do molde")
    if molde["instagram"] and (novo.get("instagram_user_id") or b.get("instagram_user_id")) not in (None, molde["instagram"]):
        falhas.append("Instagram diferente do molde")
    return falhas


def cmd_subir(args) -> None:
    plano = carregar_plano(args.plano)
    ctx = conferir(plano)
    molde, conta, estado = ctx["molde"], ctx["conta"], ctx["estado"]

    print("PLANO DE SUBIDA (Meta)")
    print(f"Conta: {conta}   Conjunto: {ctx['conjunto']['name']} ({ctx['conjunto']['id']})")
    print("\n".join(resumo_molde(molde)))
    print(f"Anúncios ({len(plano['anuncios'])}), todos nascem PAUSADOS:")
    for a in plano["anuncios"]:
        feito = "  (já subido)" if estado["itens"].get(a["nome"], {}).get("anuncio") else ""
        print(f"  {a['nome']}  <-  {Path(a['arquivo']).name}{feito}")
    for aviso in ctx["avisos"]:
        print(f"AVISO: {aviso}")
    if not args.executar:
        print("\nNada foi enviado. Confira o plano com a pessoa e rode de novo com --executar.")
        return

    tok_criativo = token_da_pagina(molde["criativo"]["object_story_spec"]["page_id"])
    ad_molde = molde["anuncio"]
    resultados = []
    for a in plano["anuncios"]:
        nome, arq = a["nome"], Path(a["arquivo"]).expanduser()
        e = estado["itens"].setdefault(nome, {})
        salvar = lambda: plano["_estado"].write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            print(f"\n{nome}", file=sys.stderr)
            if molde["tipo"] == "video":
                if not e.get("video_id"):
                    print("  enviando vídeo...", file=sys.stderr)
                    e["video_id"] = subir_video(conta, arq)
                    salvar()
                if not e.get("capa"):
                    e["capa"] = capa_do_video(e["video_id"])
                    salvar()
            elif not e.get("hash"):
                print("  enviando imagem...", file=sys.stderr)
                e["hash"] = subir_imagem(conta, arq)
                salvar()
            if not e.get("criativo"):
                print("  criando criativo...", file=sys.stderr)
                e["criativo"] = escrever(f"{conta}/adcreatives", montar_criativo(molde, nome, e), tok=tok_criativo)["id"]
                salvar()
            if not e.get("anuncio"):
                # Se uma tentativa anterior criou o anúncio e caiu antes de anotar, adota em vez de duplicar.
                for x in nucleo.meta_paginar(f"{plano['conjunto']}/ads", token(), fields="id,name,creative{id}", limit=200):
                    if x.get("name") == nome and (x.get("creative") or {}).get("id") == e["criativo"]:
                        e["anuncio"] = x["id"]
                        salvar()
            if not e.get("anuncio"):
                print("  criando anúncio pausado...", file=sys.stderr)
                dados = {"name": nome, "adset_id": plano["conjunto"], "creative": {"creative_id": e["criativo"]}, "status": "PAUSED"}
                rastreio = rastreamento_do_molde(ad_molde.get("tracking_specs"))
                if rastreio:
                    dados["tracking_specs"] = rastreio
                if ad_molde.get("conversion_domain"):
                    dados["conversion_domain"] = ad_molde["conversion_domain"]
                e["anuncio"] = escrever(f"{conta}/ads", dados)["id"]
                salvar()
            falhas = conferir_criativo(e["criativo"], molde)
            final = ler(e["anuncio"], fields="name,status,effective_status")
            if final.get("name") != nome:
                falhas.append(f"a Meta gravou o nome como '{final.get('name')}'")
            if final.get("status") != "PAUSED":
                falhas.append(f"status {final.get('status')}, esperado PAUSED")
            resultados.append((nome, e["anuncio"], final.get("effective_status"), falhas))
        except Erro as erro:
            resultados.append((nome, e.get("anuncio", "-"), "ERRO", [str(erro)]))
            if "pausa" in str(erro):
                break

    ok = [r for r in resultados if not r[3]]
    print("\nUPLOAD FINALIZADO" if len(ok) == len(plano["anuncios"]) else "\nUPLOAD COM PENDÊNCIAS")
    print(f"Conta: {conta}  Conjunto: {ctx['conjunto']['name']}  Status: PAUSADO")
    print(f"Total solicitado: {len(plano['anuncios'])} / Total enviado sem falha: {len(ok)}")
    for nome, ad_id, status, falhas in resultados:
        print(f"  {nome}  ID {ad_id}  [{status}]" + ("" if not falhas else "  FALHA: " + "; ".join(falhas)))
    print("Próximo passo: o responsável pela conta revisa e ativa no Gerenciador de Anúncios.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sobe criativo na Meta nas contas da AUVP.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("contas")
    p = sub.add_parser("campanhas"); p.add_argument("--conta", required=True); p.add_argument("--todas", action="store_true")
    p = sub.add_parser("conjuntos"); p.add_argument("--conta"); p.add_argument("--campanha", required=True)
    p = sub.add_parser("anuncios"); p.add_argument("--conjunto", required=True)
    p = sub.add_parser("molde"); p.add_argument("--anuncio", required=True)
    p = sub.add_parser("subir"); p.add_argument("--plano", required=True); p.add_argument("--executar", action="store_true")
    args = ap.parse_args()
    {"contas": cmd_contas, "campanhas": cmd_campanhas, "conjuntos": cmd_conjuntos, "anuncios": cmd_anuncios,
     "molde": cmd_molde, "subir": cmd_subir}[args.comando](args)


if __name__ == "__main__":
    nucleo.principal(main)
