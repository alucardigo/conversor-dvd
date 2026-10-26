"""Testes rápidos (sem ffmpeg): preferências, pasta do .exe instalado e cancelamento de processo."""
import sys
import time
from pathlib import Path

from conversor_dvd import gui, preferencias
from conversor_dvd.ffmpeg import FFmpeg, pastas_locais


def test_pastas_locais_quando_empacotado_ficam_ao_lado_do_exe(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ConversorDVD" / "ConversorDVD.exe"))
    assert pastas_locais()[0] == tmp_path / "ConversorDVD" / "ffmpeg" / "bin"


def test_preferencias_ida_e_volta_e_arquivo_corrompido_vira_vazio(tmp_path):
    arq = tmp_path / "config.json"
    preferencias.salvar({"qualidade": "alta"}, arq)
    assert preferencias.carregar(arq) == {"qualidade": "alta"}
    arq.write_text("{isto nao e json", encoding="utf-8")
    assert preferencias.carregar(arq) == {}


def test_preferencias_com_valores_invalidos_voltam_ao_padrao():
    limpo = gui._prefs_validas({"qualidade": "ultra", "formatos": ["xyz"], "desentrelacar": "nao"})
    assert limpo["qualidade"] == "media"
    assert limpo["formatos"] == ["mp4"]
    assert limpo["desentrelacar"] is True


def test_registro_de_erro_acumula_e_devolve_o_caminho(tmp_path):
    arq = tmp_path / "erros.log"
    assert preferencias.registrar_erro("primeiro", arq) == arq
    preferencias.registrar_erro("segundo", arq)
    texto = arq.read_text(encoding="utf-8")
    assert "primeiro" in texto and "segundo" in texto


def test_processo_que_trava_e_cancelado_sem_esperar(tmp_path):
    # Simula um ffmpeg preso (disco com setor ruim): não imprime nada e não termina.
    ff = FFmpeg(ffmpeg=sys.executable, ffprobe=sys.executable)
    inicio = time.monotonic()
    r = ff.executar([sys.executable, "-c", "import time; time.sleep(60)"], duracao=10,
                    cancelado=lambda: time.monotonic() - inicio > 0.5)
    assert r.interrompido
    assert time.monotonic() - inicio < 10


def test_processo_que_termina_sozinho_nao_e_morto(tmp_path):
    ff = FFmpeg(ffmpeg=sys.executable, ffprobe=sys.executable)
    cmd = [sys.executable, "-c", "print('out_time_us=5000000', flush=True); print('progress=end', flush=True)"]
    progresso = []
    r = ff.executar(cmd, duracao=10, ao_progredir=progresso.append)
    assert r.codigo == 0 and not r.interrompido
    assert progresso == [0.5]
