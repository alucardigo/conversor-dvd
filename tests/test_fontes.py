from pathlib import Path

import pytest

from conversor_dvd.fontes import (
    ErroFonte,
    Titulo,
    agrupar_arquivos,
    eh_pasta_dvd,
    ler_lista_numeros,
    nome_disco,
    nome_seguro,
    normalizar_entrada,
    planejar,
    selecionar,
)


def criar(raiz: Path, *nomes: str) -> list[Path]:
    caminhos = []
    for nome in nomes:
        p = raiz / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        caminhos.append(p)
    return caminhos


def test_vobs_agrupados_por_titleset_e_menus_ignorados(tmp_path):
    arquivos = criar(
        tmp_path,
        "VIDEO_TS.VOB", "VTS_01_0.VOB", "VTS_01_2.VOB", "VTS_01_1.VOB", "vts_02_1.vob",
    )
    grupos = agrupar_arquivos(arquivos)
    assert [(n, [p.name for p in g]) for n, g in grupos] == [
        ("VTS 01", ["VTS_01_1.VOB", "VTS_01_2.VOB"]),
        ("VTS 02", ["vts_02_1.vob"]),
    ]


def test_arquivos_soltos_viram_um_titulo_cada_e_o_resto_e_ignorado(tmp_path):
    arquivos = criar(tmp_path, "VR_MOVIE.VRO", "AVSEQ01.DAT", "gravacao.mpg", "leia.txt", "VR_MANGR.IFO")
    nomes = [n for n, _ in agrupar_arquivos(arquivos)]
    assert nomes == ["AVSEQ01", "gravacao", "VR_MOVIE"]


@pytest.mark.parametrize(
    ("pasta", "arquivos", "esperado"),
    [
        ("VIDEO_TS", ["VIDEO_TS.IFO", "VTS_01_1.VOB"], True),
        ("video_ts", ["vts_01_1.vob"], True),  # IFO perdido, mas a pasta é de DVD
        ("Filme", ["video_ts.ifo"], True),  # pasta renomeada
        ("Filme", ["VTS_01_1.VOB"], False),  # VOBs soltos: agrupados à parte
        ("Filmes", ["gravacao.mpg"], False),
    ],
)
def test_eh_pasta_dvd(pasta, arquivos, esperado):
    assert eh_pasta_dvd(Path(pasta), arquivos) is esperado


def test_escolher_um_vob_traz_as_outras_partes_do_mesmo_titleset(tmp_path):
    criar(tmp_path, "Copia/VTS_02_2.VOB", "Copia/VTS_02_1.VOB", "Copia/VTS_03_1.VOB")
    [item] = planejar(tmp_path / "Copia" / "VTS_02_1.VOB")
    assert (item.disco, item.nome) == ("Copia", "VTS 02")
    assert [p.name for p in item.caminhos] == ["VTS_02_1.VOB", "VTS_02_2.VOB"]


def test_escolher_o_ifo_abre_o_dvd(tmp_path):
    criar(tmp_path, "Aniversario/VIDEO_TS/VIDEO_TS.IFO")
    [item] = planejar(tmp_path / "Aniversario" / "VIDEO_TS" / "VIDEO_TS.IFO")
    assert (item.tipo, item.disco) == ("dvd", "Aniversario")


def test_arquivo_de_formato_desconhecido(tmp_path):
    [doc] = criar(tmp_path, "leia.txt")
    with pytest.raises(ErroFonte):
        planejar(doc)


def test_restos_do_programa_de_autoria_ao_lado_do_video_ts_sao_ignorados(tmp_path):
    # Disco de programa de autoria: a pasta Sonic traz o fundo do menu em .m2v.
    criar(tmp_path, "VIDEO_TS/VIDEO_TS.IFO", "VIDEO_TS/VTS_01_1.VOB", "Autoria/Menus/Video_pgc45.m2v", "AUDIO_TS/x.bin")
    assert [(i.tipo, i.caminhos[0].name) for i in planejar(tmp_path)] == [("dvd", "VIDEO_TS")]


def test_planejar_pasta_com_varios_discos_isos_e_soltos(tmp_path):
    criar(
        tmp_path,
        "Filme/VIDEO_TS/VIDEO_TS.IFO", "Filme/VIDEO_TS/VTS_01_1.VOB", "Filme/Autoria/menu.m2v",
        "Show.iso",
        "Gravador/DVD_RTAV/VR_MOVIE.VRO",
        "VCD/MPEGAV/AVSEQ01.DAT",
    )
    plano = [(i.tipo, i.disco, i.nome) for i in planejar(tmp_path)]
    assert plano == [
        ("iso", "Show", ""),
        ("dvd", "Filme", ""),
        ("arquivos", "Gravador", "VR_MOVIE"),
        ("arquivos", "VCD", "AVSEQ01"),
    ]


def test_nome_disco_sobe_pastas_estruturais(tmp_path):
    assert nome_disco(tmp_path / "Aniversario" / "VIDEO_TS") == "Aniversario"
    assert nome_disco(tmp_path / "Aniversario" / "DVD_RTAV") == "Aniversario"
    assert nome_disco(tmp_path / "Aniversario" / "MPEGAV") == "Aniversario"


def titulos(*duracoes):
    return [Titulo(disco="d", nome=f"T{i}", entrada=[], duracao=d) for i, d in enumerate(duracoes, 1)]


def test_selecionar_descarta_titulos_curtos_mas_mantem_duracao_desconhecida():
    escolhidos = selecionar(titulos(278.8, 3.0, 0.0, 154.7), minimo=10)
    assert [t.nome for t in escolhidos] == ["T1", "T3", "T4"]


def test_disco_so_de_clipes_curtos_converte_todos():
    assert [t.nome for t in selecionar(titulos(8, 2, 5), minimo=10)] == ["T1", "T2", "T3"]


def test_selecionar_por_numero_ignora_o_minimo():
    assert [t.nome for t in selecionar(titulos(5, 100, 2), numeros=[1, 3])] == ["T1", "T3"]


def test_selecionar_numero_inexistente_da_erro():
    with pytest.raises(ValueError, match="7"):
        selecionar(titulos(5, 100), numeros=[7])


def test_selecionar_so_o_maior():
    assert [t.nome for t in selecionar(titulos(278, 2332, 849), so_maior=True)] == ["T2"]


def test_ler_lista_numeros():
    assert ler_lista_numeros("1, 3-5,8") == [1, 3, 4, 5, 8]
    with pytest.raises(ValueError):
        ler_lista_numeros("a")


def test_nome_seguro_remove_caracteres_proibidos_no_windows():
    assert nome_seguro('dvd: "Título" 01/02?') == "dvd Título 01 02"
    assert nome_seguro("   ") == "DVD"


@pytest.mark.parametrize("digitado", ["E:", "e:\\", "E:/", 'E:"', '"E:\\"', "  E:  "])
def test_unidade_digitada_de_qualquer_jeito_vira_a_raiz(digitado):
    assert normalizar_entrada(digitado) == Path("E:\\")


def test_caminho_comum_so_perde_as_aspas():
    assert normalizar_entrada(r'"D:\DVDs\Aniversario"') == Path(r"D:\DVDs\Aniversario")
