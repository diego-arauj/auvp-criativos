---
name: subir-criativos
description: Sobe criativos (vídeo e imagem) nas contas de anúncio da AUVP na Meta (Facebook/Instagram) e no Google Ads (Demand Gen com vídeo do YouTube). Use quando a pessoa disser "configurar", "configurar a skill", "como eu uso", "subir criativo", "subir vídeo", "subir anúncio", "subir esses criativos no conjunto X", "criar anúncio com esse vídeo", "subir no Google Ads", "colocar esse link do YouTube no Demand Gen". Só sobe criativo, sempre pausado, só nas contas da AUVP. Não mexe em campanha, conjunto, orçamento, público nem status.
---

# Subir criativos AUVP

Esta skill faz uma coisa só: **pega um arquivo de vídeo/imagem (Meta) ou um link do YouTube (Google) e
cria o anúncio PAUSADO dentro de um conjunto ou grupo que já existe, copiando tudo do anúncio-molde.**
Ativar, pausar, mexer em orçamento, público, campanha ou conjunto é com o responsável pela conta, no
Gerenciador. Se pedirem isso, diga que esta skill não faz e pare.

Todo o trabalho passa por 3 scripts da pasta `scripts/` desta skill. **Nunca chame as APIs da Meta ou do
Google de outro jeito, nem leia as credenciais**: a trava do plugin bloqueia, e insistir não adianta.

## Como rodar os scripts (formato obrigatório)

Use o caminho absoluto da pasta desta skill (aparece como "Base directory" quando a skill abre) e
rode um comando por vez, sem `cd`, sem `&&`, sem `;`, sem `|`:

```
python3 "<pasta da skill>/scripts/meta.py" contas
```

Sem redirecionar a saída (`>`, `2>&1`) e sem variáveis antes do `python3`. Qualquer outro formato é
bloqueado pela trava. **Subida com vídeo demora:** rode o `--executar` com o tempo máximo de comando
(10 minutos). Se o tempo acabar, rode o mesmo comando de novo: ele continua de onde parou.

## 1. Configurar (pedido "configurar")

1. Rode `python3 "<pasta da skill>/scripts/configurar.py"`. Na primeira vez ele prepara o ambiente
   (1 a 3 minutos) e abre **uma janela pedindo a senha mestra**. Avise a pessoa antes: "vai abrir uma
   janela, digite lá a senha que você recebeu". **Nunca peça a senha no chat.**
2. Mostre o resultado: as contas liberadas na Meta e no Google.
3. Explique em 4 linhas como usar (seção 2) e pare.

Senha errada: peça para rodar de novo e conferir a senha com quem a enviou. Se a janela não abrir,
o script diz o comando para a pessoa rodar no Terminal.

## 2. Como usar (pedido "como eu uso?")

Explique assim, curto:
- **Meta:** me diga a conta, a campanha e o conjunto onde o criativo entra, e mande o caminho do
  arquivo (vídeo 9:16 ou imagem). Eu uso um anúncio que já está no conjunto como molde: o texto, o
  título, o botão, o link e as UTMs saem iguais aos dele. O anúncio nasce pausado.
- **Google:** suba o vídeo no YouTube como **não listado**, me mande o link (e o do Short, se tiver)
  e diga a campanha Demand Gen e os grupos. O anúncio nasce pausado, copiando o molde.
- Antes de subir eu mostro o plano; só subo depois do seu ok.

## 3. Subir na Meta

**Passo 1, destino.** Se a pessoa não disse campanha e conjunto, **pergunte**; nunca escolha sozinho
e nunca crie campanha ou conjunto. Para ajudar a escolher:
```
python3 "<pasta>/scripts/meta.py" contas
python3 "<pasta>/scripts/meta.py" campanhas --conta <ID>
python3 "<pasta>/scripts/meta.py" conjuntos --campanha <ID>
python3 "<pasta>/scripts/meta.py" anuncios --conjunto <ID>
```

**Passo 2, molde.** O molde é um anúncio já existente **do mesmo tipo** (vídeo para vídeo, imagem para
imagem), de preferência ativo e no mesmo conjunto. Mostre o que será copiado e peça o ok:
```
python3 "<pasta>/scripts/meta.py" molde --anuncio <ID>
```
O texto e o título **nunca** são escritos pela skill: saem do molde, letra por letra. Se a pessoa quiser
outro texto, ela precisa escolher outro molde que já tenha esse texto. Anúncio flexível, dinâmico ou
feito a partir de post não serve de molde (o script avisa).

**Passo 3, plano.** Grave um arquivo JSON (por exemplo `~/planos-criativos/AAAA-MM-DD-<tema>.json`):
```json
{
  "conjunto": "120253671240340547",
  "molde_anuncio": "120253000000000000",
  "anuncios": [
    {"nome": "AD_PITCH_08-10-26", "arquivo": "/Users/fulano/Downloads/STORY - 08-10.mp4"},
    {"nome": "AD_PITCH_09-10-26", "arquivo": "/Users/fulano/Downloads/STORY - 09-10.mp4"}
  ]
}
```
Rode a conferência (não sobe nada) e mostre o resultado à pessoa:
```
python3 "<pasta>/scripts/meta.py" subir --plano "<arquivo>"
```

**Passo 4, subir** só depois do ok explícito da pessoa:
```
python3 "<pasta>/scripts/meta.py" subir --plano "<arquivo>" --executar
```
Se cair no meio (internet, limite da Meta), rode **o mesmo comando** de novo: o que já subiu não repete
(o andamento fica em `<arquivo>.estado.json`).

## 4. Subir no Google (Demand Gen)

A skill **não sobe no YouTube**. A pessoa sobe no canal como **não listado** e manda os links
(`youtu.be/...` e, se tiver, `youtube.com/shorts/...`).
```
python3 "<pasta>/scripts/gads.py" contas
python3 "<pasta>/scripts/gads.py" grupos --conta <ID>
python3 "<pasta>/scripts/gads.py" anuncios --conta <ID> --grupo <ID>
python3 "<pasta>/scripts/gads.py" molde --conta <ID> --anuncio <ID>
```
Plano:
```json
{
  "conta": "6717534890",
  "molde_anuncio": "811656881665",
  "grupos": ["203913692344"],
  "anuncios": [
    {"nome": "PITCH 08-10", "videos": ["https://youtu.be/AAAAAAAAAAA", "https://youtube.com/shorts/BBBBBBBBBBB"]}
  ]
}
```
Mesmo fluxo: `subir --plano` (confere) e, com o ok, `subir --plano ... --executar`. É criado 1 anúncio
por grupo listado. Se o nome já existe no grupo, ele pula (rodar de novo não duplica).

## Regras da casa para subir criativo

- **Formato Meta:** as contas da AUVP rodam no vertical, **9:16, 1080x1920**, H.264. Vídeo 4K ou acima
  de ~200 MB costuma travar ou ser recusado: peça a exportação em 1080x1920. Texto e rosto longe do
  topo (14%) e da base (20%) da tela.
- **Não misture vídeo e imagem no mesmo conjunto.** O script recusa.
- **Conjunto de criativo dinâmico aceita 1 anúncio só.** O script avisa.
- **O nome do anúncio vira a `utm_content`** de quem clica: nunca repita nome, nunca use "- Copy".
  Padrões em uso: vídeo de pitch `AD_PITCH_DD-MM-AA`; VSL `AD_VSL_<TEMA>_<MÊS><ANO>` (ex.:
  `AD_VSL_ETF_OUT26`); no Google, `PITCH DD-MM`. Siga o padrão dos anúncios vizinhos do conjunto.
- **Página e Instagram saem do molde.** Não troque.
- **Sempre pausado.** Quem ativa é o responsável pela conta, depois de olhar a prévia no Gerenciador.
- **Limite da Meta:** por volta de 40 criações seguidas a Meta pede pausa. O script para e avisa;
  espere 5 minutos e rode o mesmo comando.
- **Revisão:** logo depois de criado, o anúncio fica "em análise". Vídeo com tema político ou eleitoral
  e promessa de rentabilidade costumam ser reprovados; se notar isso no nome ou no pedido, avise antes.

## Resposta final à pessoa

Repita o bloco que o script imprime (`UPLOAD FINALIZADO` ou `UPLOAD COM PENDÊNCIAS`), com nome, ID e
status de cada anúncio, e lembre que estão pausados. Se houve falha, diga qual, a causa provável que
o script deu e o próximo passo. Não invente ID nem status: só o que o script imprimiu.
