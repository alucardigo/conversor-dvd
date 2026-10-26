"""Testes ponta a ponta com discos reais gerados por `tests/gerar_fixtures.py`."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conversor_dvd.conversao import Cancelado, Opcoes, converter
from conversor_dvd.ffmpeg import FFmpeg
from conversor_dvd.fontes import analisar

FIX = Path(__file__).resolve().parent / "fixtures"

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(not (FIX / "disco.iso").exists(), reason="rode tests/gerar_fixtures.py"),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente"),
]


@pytest.fixture(scope="module")
def ff():
    return FFmpeg.localizar()


def sondar(arquivo: Path) -> dict:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(arquivo)],
        capture_output=True, check=True, text=True,
    ).stdout
    return json.loads(saida)


def duracoes(titulos):
    return [round(t.duracao) for t in titulos]


@pytest.mark.parametrize("entrada", ["disco_video", "disco_video/VIDEO_TS", "disco_video/VIDEO_TS/VIDEO_TS.IFO", "disco.iso"])
def test_dvd_video_lista_os_titulos_na_ordem_do_ifo(ff, entrada):
    titulos = analisar(FIX / entrada, ff)
    assert duracoes(titulos) == [8, 2, 5]
    assert {t.tipo for t in titulos} == {"DVD-Video"}
    assert titulos[0].nome == "Título 01"


def test_vobs_sem_ifo_sao_concatenados_por_titleset(ff):
    titulos = analisar(FIX / "vobs_soltos", ff)
    assert [t.nome for t in titulos] == ["VTS 01", "VTS 02"]
    assert duracoes(titulos) == [16, 5]


@pytest.mark.parametrize(("pasta", "nome", "seg"), [("disco_vr", "VR_MOVIE", 8), ("disco_vcd", "AVSEQ01", 3)])
def test_dvd_vr_e_vcd(ff, pasta, nome, seg):
    [titulo] = analisar(FIX / pasta, ff)
    assert (titulo.nome, round(titulo.duracao)) == (nome, seg)


def test_pasta_com_varios_discos(ff):
    titulos = analisar(FIX, ff)
    discos = {t.disco for t in titulos}
    assert {"disco", "disco_video", "disco_vr", "disco_vcd", "vobs_soltos"} <= discos


def test_dvd_para_mp4(ff, tmp_path):
    titulo = analisar(FIX / "disco_video", ff)[0]
    progresso = []
    saida = converter(ff, titulo, "mp4", tmp_path, Opcoes(), ao_progredir=progresso.append)
    assert saida.name == "disco_video - Título 01.mp4"
    info = sondar(saida)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (video["codec_name"], audio["codec_name"]) == ("h264", "aac")
    assert video.get("field_order", "progressive") == "progressive"
    assert video["display_aspect_ratio"] == "16:9"
    assert abs(float(info["format"]["duration"]) - 8) < 0.5
    assert progresso and progresso[-1] > 0.9
    assert not list(tmp_path.glob("*.parcial.*"))


def test_dvd_para_avi_com_pixel_quadrado(ff, tmp_path):
    titulo = analisar(FIX / "disco.iso", ff)[0]
    info = sondar(converter(ff, titulo, "avi", tmp_path, Opcoes()))
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (video["codec_name"], video.get("codec_tag_string")) == ("mpeg4", "XVID")
    assert audio["codec_name"] == "mp3"
    assert (video["width"], video["height"]) == (1024, 576)


def test_vobs_concatenados_viram_um_video_so(ff, tmp_path):
    titulo = analisar(FIX / "vobs_soltos", ff)[0]
    info = sondar(converter(ff, titulo, "mp4", tmp_path, Opcoes(qualidade="pequena")))
    assert abs(float(info["format"]["duration"]) - 16) < 0.6


def test_vcd_para_avi(ff, tmp_path):
    [titulo] = analisar(FIX / "disco_vcd", ff)
    assert converter(ff, titulo, "avi", tmp_path, Opcoes()).stat().st_size > 0


def test_cancelar_nao_deixa_arquivo_pela_metade(ff, tmp_path):
    titulo = analisar(FIX / "disco_video", ff)[0]
    chamadas = []

    def cancelado():  # deixa o ffmpeg começar e cancela no meio
        chamadas.append(1)
        return len(chamadas) > 2

    with pytest.raises(Cancelado):
        converter(ff, titulo, "mp4", tmp_path, Opcoes(), cancelado=cancelado)
    assert len(chamadas) > 2
    assert list(tmp_path.iterdir()) == []
