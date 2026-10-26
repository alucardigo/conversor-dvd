# Conversor de DVD

Converte DVDs antigos para **MP4** ou **AVI**: direto da unidade de DVD, de uma pasta
copiada do disco, de uma imagem ISO ou de arquivos de vídeo soltos. Tem janela
(sem precisar saber de linha de comando) e uma versão para o terminal.

## Instalação (Windows)

Baixe `ConversorDVD-Setup-<versão>.exe` na página de [releases](../../releases) e execute.
A instalação não pede administrador: o programa vai para a sua pasta de usuário.

> O instalador **não tem assinatura digital**, então o Windows pode mostrar
> "O Windows protegeu o computador". Clique em **Mais informações** e depois em
> **Executar assim mesmo**. O FFmpeg (conversor de vídeo, GPL v3) vem junto; o aviso
> de licença está em `THIRD_PARTY.txt` na pasta de instalação.

## Como usar

1. Coloque o DVD na unidade (ou escolha uma pasta, uma ISO ou um arquivo de vídeo).
2. Clique em **Analisar disco**. Os títulos aparecem numa lista.
3. Marque os títulos que quer converter (clique na caixinha ou aperte espaço).
4. Escolha o formato (MP4 ou AVI), a qualidade e a pasta de destino.
5. Clique em **Converter**. Os vídeos ficam na pasta de destino, com nomes como
   `disco - Título 01.mp4`. Nada é sobrescrito: se o nome já existe, o novo ganha `(2)`.

As escolhas de formato, qualidade e pasta são lembradas da próxima vez.
Se algo der errado, a mensagem diz onde ficou o registro (`erros.log`, em
`%APPDATA%\ConversorDVD`).

**Linha de comando** (`conversor-dvd.exe`, instalado junto):

```
conversor-dvd.exe E:                        todos os títulos do DVD para MP4
conversor-dvd.exe E: -f ambos -q alta       MP4 e AVI, qualidade alta
conversor-dvd.exe E: --listar               só mostra os títulos
conversor-dvd.exe filme.iso -t 2,4 -f avi   títulos 2 e 4, em AVI
conversor-dvd.exe D:\DVDs -o D:\Videos      todos os discos de uma pasta
```

## Formatos de entrada

| O que é | Como aparece |
|---|---|
| DVD-Video (filme, DVD gravado no PC) | unidade `E:`, pasta `VIDEO_TS`, `.ISO`, `.IFO` |
| DVD-VR (gravador de mesa, filmadora de DVD) | `DVD_RTAV\VR_MOVIE.VRO` |
| VCD / SVCD | `MPEGAV\*.DAT`, `MPEG2\*.MPG` |
| VOBs copiados sem IFO | `VTS_01_1.VOB`, `VTS_01_2.VOB`... (juntados por titleset) |
| Filmadora / MPEG solto | `.MOD`, `.TOD`, `.MTS`, `.M2TS`, `.MPG`, `.VOB`, `.M2V` |
| Pasta com vários discos | cada `VIDEO_TS`, ISO e vídeo da pasta vira uma entrada |

Os títulos do DVD-Video saem na ordem do menu (IFO). Se o IFO estiver danificado,
o programa junta os VOBs por titleset. Títulos com menos de 10 s (vinhetas,
logos) começam desmarcados.

## Saída

| | MP4 | AVI |
|---|---|---|
| Vídeo | H.264 | Xvid (MPEG-4 ASP) |
| Áudio | AAC, todas as faixas | MP3 estéreo, primeira faixa |
| Proporção | 4:3 ou 16:9 do disco, sinalizada | pixel quadrado (640x480, 1024x576...) |
| Capítulos | mantidos | — |

O AVI usa pixel quadrado porque TV e aparelho de DVD antigos ignoram a proporção
gravada no arquivo e mostrariam a imagem esticada.

**Remover serrilhado** (ligado por padrão): só mexe nos quadros que o DVD marca como
entrelaçados, então filme progressivo passa intacto.

**Qualidade** (medida num DVD de filmadora antigo, 14 min):

| | MP4 | AVI |
|---|---|---|
| alta | CRF 18 | Xvid q3 (~4 Mbps) |
| média (padrão) | CRF 21 (~2,3 Mbps) | Xvid q4 (~2,9 Mbps) |
| pequena | CRF 24 | Xvid q6 (~1,9 Mbps) |

## Limitações

- **DVD comercial com proteção (CSS)** não é lido: o programa não quebra proteção.
- **ISO que não é DVD-Video** (de VCD ou DVD-VR): dê dois cliques na ISO no Explorer
  para o Windows montá-la como unidade e escolha essa unidade no programa.
- **DVD-VR** sai como um vídeo único por `.VRO`; as gravações não são separadas.
- **Multiângulo** (raro em DVD caseiro): só o primeiro ângulo.
- **Legendas** do DVD são imagens e não vão para o arquivo.
- Se o programa for fechado à força (Gerenciador de Tarefas) no meio de uma conversão,
  o FFmpeg pode continuar até terminar o arquivo que estava gravando. O arquivo
  `*.parcial.*` fica na pasta de destino e pode ser apagado.

## Desenvolvimento

Requisitos: Python 3.10+ (com tkinter, que vem no instalador oficial do Python) e
FFmpeg com `libx264`, `libxvid`, `libmp3lame` e o demuxer `dvdvideo` (FFmpeg 7+).
`winget install Gyan.FFmpeg` traz tudo.

```
python -m conversor_dvd                 abre a janela (ou: python -m conversor_dvd E: --listar)
python -m pytest -m "not integracao"    testes rápidos, sem ffmpeg
python tests/gerar_fixtures.py          gera discos de teste reais (usa dvdauthor e genisoimage no WSL)
python -m pytest                        tudo, inclusive conversão e janela
```

**Gerar o instalador:** é preciso PyInstaller (`python -m pip install --user pyinstaller`)
e o [Inno Setup 6](https://jrsoftware.org/isdl.php) (instalação só para o usuário).
Depois, a partir da raiz do repositório:

```
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

O script roda os testes, gera `dist\ConversorDVD` com o ffmpeg dentro e compila
`installer\out\ConversorDVD-Setup-<versão>.exe`. Use `-FFmpeg` para apontar a pasta
do ffmpeg e `-Inno` para o `ISCC.exe`, se ele não estiver no lugar padrão.

`gerar_fixtures.py` cria DVD-Video com IFO de verdade (dvdauthor), ISO (genisoimage),
DVD-VR, VCD e VOBs divididos. As duas ferramentas rodam no WSL e são extraídas sem
root: `apt-get download dvdauthor genisoimage` e `dpkg -x` para `~/dvdtools/root`.

## Licença

[MIT](LICENSE). O FFmpeg incluso no instalador é GPL v3 (ver `packaging/THIRD_PARTY.txt`).
