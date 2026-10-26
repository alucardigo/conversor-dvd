"""Dirige a janela de verdade (tkinter) com discos de teste."""
import shutil
import time
import tkinter as tk
from pathlib import Path

import pytest

from conversor_dvd import gui
from conversor_dvd.conversao import Cancelado
from conversor_dvd.ffmpeg import FFmpeg
from conversor_dvd.gui import Janela

FIX = Path(__file__).resolve().parent / "fixtures"

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(not (FIX / "disco_video").exists(), reason="rode tests/gerar_fixtures.py"),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente"),
]


def esperar(raiz: tk.Tk, condicao, limite: float = 180) -> None:
    fim = time.monotonic() + limite
    while not condicao():
        assert time.monotonic() < fim, "a janela não terminou a tempo"
        raiz.update()
        time.sleep(0.05)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Janela com preferências isoladas e avisos capturados (sem caixa modal na frente do teste)."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    avisos: list[tuple[str, tuple]] = []
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: avisos.append(("aviso", a)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: avisos.append(("erro", a)))
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    raiz = tk.Tk()
    janela = Janela(raiz, FFmpeg.localizar(), minimo=3)
    yield janela, avisos
    raiz.destroy()


def carregar_disco(janela: Janela, origem: Path) -> None:
    janela.origem.set(str(origem))
    janela._analisar()
    esperar(janela.raiz, lambda: janela.titulos or janela.resumo.get().startswith(("Não foi", "Algo")))


def test_analisa_marca_titulos_longos_e_converte_nos_dois_formatos(ambiente, tmp_path):
    janela, avisos = ambiente
    carregar_disco(janela, FIX / "disco_video")
    assert len(janela.lista.get_children()) == 3
    assert janela.marcados == {0, 2}  # minimo=3 s: o título de 2 s começa desmarcado
    assert janela.lista.set("1", "marca") == gui.LIVRE

    janela.destino.set(str(tmp_path / "saida"))
    janela.formatos["avi"].set(True)
    janela._converter()
    assert "disabled" in janela.bt_converter.state()
    esperar(janela.raiz, lambda: not janela.convertendo)

    assert sorted(p.name for p in (tmp_path / "saida").iterdir()) == [
        "disco_video - Título 01.avi", "disco_video - Título 01.mp4",
        "disco_video - Título 03.avi", "disco_video - Título 03.mp4",
    ]
    assert janela.resumo.get().startswith("Pronto")
    assert "disabled" not in janela.bt_abrir.state()
    assert avisos == []


def test_origem_sem_dvd_mostra_aviso_e_destrava(ambiente, tmp_path):
    janela, avisos = ambiente
    carregar_disco(janela, tmp_path)  # pasta vazia
    assert avisos and avisos[0][0] == "aviso"
    assert "Nenhum vídeo" in avisos[0][1][1]
    assert "disabled" not in janela.bt_analisar.state()


def test_imagem_iso_que_nao_abre_leva_a_dica_do_explorer(ambiente, tmp_path):
    janela, avisos = ambiente
    (tmp_path / "filme.iso").write_bytes(b"isto nao e um dvd")
    carregar_disco(janela, tmp_path / "filme.iso")
    assert avisos and "Explorer" in avisos[0][1][1]


def test_marcar_com_clique_espaco_e_botoes(ambiente):
    janela, _ = ambiente
    carregar_disco(janela, FIX / "disco_video")
    janela._alternar("0")
    assert janela.marcados == {2}
    janela.lista.focus("1")
    janela._espaco_na_lista(None)
    assert janela.marcados == {1, 2}
    janela._marcar_todos(False)
    assert janela.marcados == set()
    assert "disabled" in janela.bt_converter.state()
    janela._marcar_todos(True)
    assert janela.marcados == {0, 1, 2}


def test_falha_inesperada_na_conversao_destrava_a_janela(ambiente, tmp_path, monkeypatch):
    janela, avisos = ambiente

    def quebra(*_a, **_k):
        raise OSError("disco removido no meio da conversão")

    monkeypatch.setattr(gui, "converter", quebra)
    carregar_disco(janela, FIX / "disco_video")
    janela.destino.set(str(tmp_path / "saida"))
    janela._converter()
    esperar(janela.raiz, lambda: not janela.convertendo)

    assert janela.resumo.get().startswith("Terminou com problemas")
    assert avisos and avisos[0][0] == "aviso"
    assert "disabled" not in janela.bt_analisar.state()
    assert "disabled" in janela.bt_abrir.state()  # nada ficou pronto
    assert (tmp_path / "appdata" / "ConversorDVD" / "erros.log").exists()


def test_cancelar_encerra_sem_marcar_pronto(ambiente, tmp_path, monkeypatch):
    janela, avisos = ambiente

    def falsa(_ff, _titulo, _formato, _pasta, _opcoes, ao_progredir=None, cancelado=None):
        while not cancelado():
            time.sleep(0.01)
        raise Cancelado()

    monkeypatch.setattr(gui, "converter", falsa)
    carregar_disco(janela, FIX / "disco_video")
    janela.destino.set(str(tmp_path / "saida"))
    janela._converter()
    assert "disabled" not in janela.bt_cancelar.state()
    janela.bt_cancelar.invoke()
    esperar(janela.raiz, lambda: not janela.convertendo)

    assert janela.resumo.get().startswith("Cancelado")
    assert "disabled" in janela.bt_abrir.state()
    assert avisos == []


def test_preferencias_sao_lembradas_na_proxima_abertura(ambiente, tmp_path):
    janela, _ = ambiente
    janela.qualidade.set("pequena")
    janela.destino.set(str(tmp_path / "minhas-coisas"))
    janela.formatos["avi"].set(True)
    janela._salvar_preferencias()

    raiz2 = tk.Tk()
    try:
        outra = Janela(raiz2, FFmpeg.localizar(), minimo=3)
        assert outra.qualidade.get() == "pequena"
        assert outra.destino.get() == str(tmp_path / "minhas-coisas")
        assert outra.formatos["avi"].get() and outra.formatos["mp4"].get()
    finally:
        raiz2.destroy()
