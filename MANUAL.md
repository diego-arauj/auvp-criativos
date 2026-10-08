# Manual: skill AUVP Criativos

Sobe criativos nas contas de anúncio da AUVP, na Meta (Facebook e Instagram) e no Google Ads
(Demand Gen), pelo Claude Code. **Só sobe criativo:** cria o anúncio pausado num conjunto que já
existe, copiando texto, botão, link e UTMs de um anúncio-molde. Não mexe em campanha, conjunto,
orçamento, público nem status, e só enxerga as contas da AUVP.

## O que você precisa

- **Windows 10 ou 11** (ou Mac). **Não precisa instalar Python nem Git:** a skill traz o que usa.
- **Claude Code** instalado (app desktop ou terminal).
- **Acesso a este repositório no GitHub** (peça ao Diego) ou o arquivo ZIP enviado por ele.
- **A senha mestra**, que o Diego envia em separado.

## 1. Instalar (uma vez)

1. **Baixe a skill.** No GitHub, logado, abra o repositório, clique no botão verde **Code** e em
   **Download ZIP**. (Ou use o ZIP que o Diego mandou.)
2. **Extraia** o ZIP numa pasta fixa, por exemplo `Documentos\auvp-criativos`. Não deixe em
   Downloads, porque a skill passa a rodar dessa pasta.
3. **No Claude Code**, digite estes dois comandos, um de cada vez, trocando o caminho pelo da sua pasta:

```
/plugin marketplace add C:/Users/SEU-USUARIO/Documents/auvp-criativos
/plugin install auvp-criativos@auvp-criativos
```

No app desktop também dá pelo botão **+ > Plugins > Add plugin**. Depois de instalar, feche e abra
a sessão do Claude Code.

**Atualizar:** quando o Diego avisar de versão nova, baixe o ZIP de novo, substitua o conteúdo da
mesma pasta e rode, um de cada vez:

```
/plugin marketplace update auvp-criativos
/plugin update auvp-criativos@auvp-criativos
```

Depois feche e abra a sessão do Claude Code.

*Quem tem Git pode instalar direto do GitHub:* `/plugin marketplace add DONO/auvp-criativos`.

## 2. Configurar (uma vez por computador)

Diga ao Claude: **configurar**.

1. Abre uma **janela pedindo a senha mestra** (no Windows, a janela de credencial do Windows: o
   usuário já vem preenchido, digite só a senha). Digite nessa janela, **nunca no chat**.
2. Ele mostra as contas liberadas na Meta e no Google. Pronto.

Se a senha estiver errada, ele avisa: diga "configurar" de novo.

## 3. Usar

### Meta (vídeo ou imagem)

Fale com o Claude normalmente. Exemplo:

> Sobe esses 3 vídeos na conta AD01 - AUVP Escola - Principal, campanha 76, conjunto
> 99_MELHOR_PUB_OUT_26_PT1. Os arquivos estão em Downloads: STORY - 08-10.mp4, STORY - 09-10.mp4 e
> STORY - 10-10.mp4.

O Claude vai:
1. Confirmar a conta, a campanha e o conjunto (se você não disser, ele pergunta).
2. Propor um **anúncio-molde** do conjunto e mostrar o que será copiado: texto, título, botão, link
   e UTMs.
3. Mostrar o **plano** (nomes dos anúncios e arquivos) e esperar o seu ok.
4. Subir e devolver o resultado com o ID de cada anúncio, **todos pausados**.

Depois, quem cuida da conta revisa a prévia no Gerenciador de Anúncios e ativa.

### Google (Demand Gen)

1. Suba o vídeo no YouTube como **não listado** (horizontal e, se tiver, o Short).
2. Mande os links ao Claude, com a campanha e os grupos. Exemplo:

> Sobe o PITCH 08-10 na campanha 29, grupo 30D. Horizontal: https://youtu.be/xxxx,
> Short: https://youtube.com/shorts/yyyy

Mesmo fluxo: molde, plano, seu ok, anúncio pausado.

## Regras de arquivo

| | Meta | Google |
|---|---|---|
| Formato | vídeo vertical 9:16, 1080x1920, MP4 (H.264); imagem JPG ou PNG | link do YouTube não listado |
| Tamanho | até ~200 MB sem sustos; 4K costuma falhar | não se aplica |
| Nome do anúncio | segue o padrão dos vizinhos (ex.: `AD_PITCH_08-10-26`); nunca repetir | ex.: `PITCH 08-10` |

O nome do anúncio vira a `utm_content` de quem clica: nome repetido mistura os números no relatório.

## O que a skill não faz (de propósito)

Ativar ou pausar anúncio, criar campanha ou conjunto, mexer em orçamento, lance, público ou
segmentação, escrever texto de anúncio novo, subir vídeo no YouTube, ler ou mexer em contas fora da
AUVP. Se você pedir, o Claude vai dizer que não faz. Isso não é erro.

## Problemas comuns

| Mensagem | O que fazer |
|---|---|
| "a skill ainda não foi configurada" | diga "configurar" |
| "não achei o Python para rodar a trava" | Windows: confira se a pasta `plugins/auvp-criativos/runtime/windows` veio inteira no ZIP. Mac: rode `xcode-select --install` no Terminal |
| o `/plugin marketplace add` não acha a pasta | confira o caminho: é a pasta que tem o `README.md` e a pasta `plugins` dentro |
| "falha de certificado na conexão" | a rede da empresa inspeciona HTTPS; peça ao TI para liberar graph.facebook.com e googleads.googleapis.com |
| "senha mestra incorreta" | confira a senha com o Diego e diga "configurar" de novo |
| "a Meta pediu uma pausa" | espere 5 minutos e peça para rodar de novo; o que já subiu não repete |
| "esse anúncio não serve de molde" | escolha um anúncio simples de vídeo ou imagem no mesmo conjunto |
| "já existe anúncio chamado ..." | mude o nome do anúncio no plano |
| "Bloqueado: ..." | é a trava da skill; peça ao Claude para usar só os comandos da skill |
| vídeo demora ou falha | exporte de novo em 1080x1920 e tente outra vez |

## Segurança

- As chaves das contas viajam **trancadas** neste repositório e só abrem com a senha mestra. Depois de
  configurar, ficam só no seu computador, na pasta `~/.auvp-criativos` (apenas o seu usuário lê).
- Uma trava no plugin impede o Claude de usar as chaves por fora da skill, mesmo com todas as
  permissões liberadas. Ela segura o Claude, não uma pessoa decidida a abrir o arquivo: por isso a
  senha só vai para quem pode subir criativo nas contas da AUVP.
- Trocou de computador ou saiu do time: apague a pasta `~/.auvp-criativos`.

---

Trocar a senha, a chave ou cortar o acesso de alguém é com o Diego.
