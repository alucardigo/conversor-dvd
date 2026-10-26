"""Gera discos de teste reais (DVD-Video com IFO, ISO, DVD-VR, VCD, VOBs soltos).

Usa o ffmpeg do Windows para os vídeos-fonte e o dvdauthor/genisoimage do WSL
(extraídos sem root em ~/dvdtools: `apt-get download` + `dpkg -x`).

    python tests/gerar_fixtures.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent / "fixtures"
WSL_BIN = "$HOME/dvdtools/root/usr/bin"

DVDAUTHOR_XML = """<dvdauthor dest="disco_video">
  <vmgm />
  <titleset>
    <titles>
      <video format="pal" aspect="16:9" widescreen="nopanscan"/>
      <pgc><vob file="a.mpg" chapters="0,0:04"/></pgc>
      <pgc><vob file="c.mpg"/></pgc>
    </titles>
  </titleset>
  <titleset>
    <titles>
      <video format="pal" aspect="4:3"/>
      <pgc><vob file="b.mpg"/></pgc>
    </titles>
  </titleset>
</dvdauthor>
"""


def caminho_wsl(p: Path) -> str:
    drive, resto = p.drive.rstrip(":").lower(), p.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{resto}"


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def fonte_dvd(saida: Path, segundos: int, aspecto: str, freq: int) -> None:
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000",
        "-t", str(segundos), "-target", "pal-dvd", "-aspect", aspecto,
        "-b:v", "2000k", "-flags", "+ilme+ildct", "-vf", "setfield=tff", "-ac", "2",
        str(saida),
    )


def wsl(script: str) -> None:
    # --exec: sem isso o wsl passa a linha por um shell extra que expande o $ antes do bash.
    subprocess.run(["wsl", "-d", "Ubuntu", "--exec", "bash", "-c", script], check=True)


def main() -> None:
    if RAIZ.exists():
        shutil.rmtree(RAIZ)
    RAIZ.mkdir(parents=True)

    fonte_dvd(RAIZ / "a.mpg", 8, "16:9", 440)
    fonte_dvd(RAIZ / "b.mpg", 5, "4:3", 660)
    fonte_dvd(RAIZ / "c.mpg", 2, "16:9", 880)
    (RAIZ / "dvd.xml").write_text(DVDAUTHOR_XML, encoding="utf-8")

    # DVD-Video de verdade (3 títulos em 2 VTS) e a ISO dele.
    d = caminho_wsl(RAIZ)
    wsl(
        f'export PATH="{WSL_BIN}:$PATH" VIDEO_FORMAT=PAL; cd "{d}" && '
        "dvdauthor -x dvd.xml >/dev/null 2>&1 && "
        "genisoimage -quiet -dvd-video -V TESTE_DVD -o disco.iso disco_video"
    )

    # DVD-VR (gravador de mesa/filmadora): VRO é MPEG-PS.
    vr = RAIZ / "disco_vr" / "DVD_RTAV"
    vr.mkdir(parents=True)
    shutil.copy(RAIZ / "a.mpg", vr / "VR_MOVIE.VRO")
    (vr / "VR_MANGR.IFO").write_bytes(b"DVD_RTR_VMG0")

    # VCD: MPEG-1 dentro de MPEGAV/AVSEQ01.DAT.
    vcd = RAIZ / "disco_vcd" / "MPEGAV"
    vcd.mkdir(parents=True)
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=352x288:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=550:sample_rate=44100",
        "-t", "3", "-target", "pal-vcd", "-ac", "2", "-f", "vcd", str(vcd / "AVSEQ01.DAT"),
    )

    # VOBs copiados sem IFO (cópia "na mão" de um disco). Como num disco real, o
    # VTS_01 é UM fluxo contínuo cortado em dois arquivos numa fronteira de setor.
    soltos = RAIZ / "vobs_soltos"
    soltos.mkdir()
    fonte_dvd(RAIZ / "longo.mpg", 16, "16:9", 330)
    dados = (RAIZ / "longo.mpg").read_bytes()
    corte = (len(dados) // 2) // 2048 * 2048
    (soltos / "VTS_01_1.VOB").write_bytes(dados[:corte])
    (soltos / "VTS_01_2.VOB").write_bytes(dados[corte:])
    shutil.copy(RAIZ / "b.mpg", soltos / "VTS_02_1.VOB")
    shutil.copy(RAIZ / "c.mpg", soltos / "VTS_01_0.VOB")  # menu: deve ser ignorado

    print("fixtures em", RAIZ)


if __name__ == "__main__":
    main()
