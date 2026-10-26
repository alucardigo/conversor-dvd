from pathlib import Path

import pytest

from conversor_dvd.conversao import Opcoes, formatar_duracao, montar_comando, nome_unico
from conversor_dvd.ffmpeg import ler_progresso
from conversor_dvd.fontes import Titulo

TITULO = Titulo(disco="dvd", nome="Título 01", entrada=["-f", "dvdvideo", "-title", "1", "-i", "E:/VIDEO_TS"])


def valor(cmd, opcao):
    return cmd[cmd.index(opcao) + 1]


def test_mp4_h264_aac_com_todas_as_faixas_de_audio_e_desentrelacamento():
    cmd = montar_comando("ffmpeg", TITULO, "mp4", Path("saida.mp4"), Opcoes())
    assert cmd[0] == "ffmpeg" and cmd[-1] == "saida.mp4"
    assert cmd[cmd.index("-i") - 4: cmd.index("-i") + 2] == TITULO.entrada
    assert valor(cmd, "-c:v") == "libx264"
    assert valor(cmd, "-c:a") == "aac"
    assert "0:a?" in cmd and "+faststart" in cmd
    assert valor(cmd, "-vf").startswith("bwdif=")
    assert valor(cmd, "-crf") == "21"


def test_avi_xvid_mp3_estereo_primeira_faixa_e_pixel_quadrado():
    cmd = montar_comando("ffmpeg", TITULO, "avi", Path("saida.avi"), Opcoes(), xvid=True)
    assert valor(cmd, "-c:v") == "libxvid"
    assert valor(cmd, "-vtag") == "XVID"
    assert valor(cmd, "-c:a") == "libmp3lame"
    assert valor(cmd, "-ac") == "2"
    assert "0:a:0?" in cmd and "0:a?" not in cmd
    filtros = valor(cmd, "-vf").split(",")
    assert filtros[0].startswith("bwdif=") and "setsar=1" in filtros


def test_avi_sem_libxvid_usa_o_mpeg4_nativo():
    cmd = montar_comando("ffmpeg", TITULO, "avi", Path("x.avi"), Opcoes(), xvid=False)
    assert valor(cmd, "-c:v") == "mpeg4"


def test_sem_desentrelacar():
    mp4 = montar_comando("ffmpeg", TITULO, "mp4", Path("x.mp4"), Opcoes(desentrelacar=False))
    avi = montar_comando("ffmpeg", TITULO, "avi", Path("x.avi"), Opcoes(desentrelacar=False))
    assert "-vf" not in mp4
    assert "bwdif" not in valor(avi, "-vf")


def test_perfil_de_qualidade():
    alta = montar_comando("ffmpeg", TITULO, "mp4", Path("x.mp4"), Opcoes(qualidade="alta"))
    assert valor(alta, "-crf") == "18"
    with pytest.raises(ValueError):
        Opcoes(qualidade="ultra")


def test_formato_desconhecido():
    with pytest.raises(ValueError):
        montar_comando("ffmpeg", TITULO, "mkv", Path("x.mkv"), Opcoes())


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [("out_time_us=12500000\n", 12.5), ("out_time_ms=3000000", 3.0), ("out_time_us=N/A", None), ("fps=30", None)],
)
def test_ler_progresso(linha, esperado):
    assert ler_progresso(linha) == esperado


def test_nome_unico_nao_sobrescreve(tmp_path):
    alvo = tmp_path / "dvd - Título 01.mp4"
    assert nome_unico(alvo) == alvo
    alvo.write_bytes(b"x")
    assert nome_unico(alvo).name == "dvd - Título 01 (2).mp4"


@pytest.mark.parametrize(("seg", "texto"), [(278.87, "4:38"), (2332.17, "38:52"), (3723, "1:02:03"), (0, "?")])
def test_formatar_duracao(seg, texto):
    assert formatar_duracao(seg) == texto
