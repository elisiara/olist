import csv
import gzip

import duckdb
import pytest

from pipeline import ingestao


def _escrever_csv_gz(caminho):
    with gzip.open(caminho, "wt", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["codigo", "valor"])
        # Zero à esquerda e duas linhas comprovam preservação do conteúdo como texto.
        escritor.writerow(["001", "10.25"])
        escritor.writerow(["002", "20.00"])


def test_csv_gz_vira_tabelas_com_as_mesmas_linhas(tmp_path, monkeypatch):
    pasta_raw = tmp_path / "raw"
    pasta_raw.mkdir()
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(ingestao, "conectar", lambda: duckdb.connect(str(banco)))

    # Cada arquivo existe para cobrir uma entrada do mapa de ingestão.
    for nome_arquivo in ingestao.MAPA_TABELAS:
        _escrever_csv_gz(pasta_raw / nome_arquivo)

    ingestao.main()

    with duckdb.connect(str(banco)) as con:
        for tabela in ingestao.MAPA_TABELAS.values():
            assert con.execute(
                f"SELECT * FROM raw.{tabela} ORDER BY codigo"
            ).fetchall() == [("001", "10.25"), ("002", "20.00")]


def test_arquivo_faltando_encerra_antes_de_conectar(tmp_path, monkeypatch):
    pasta_raw = tmp_path / "raw"
    pasta_raw.mkdir()
    # Os demais arquivos existem; este é o único motivo para interromper a ingestão.
    for nome_arquivo in list(ingestao.MAPA_TABELAS)[:-1]:
        _escrever_csv_gz(pasta_raw / nome_arquivo)
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(
        ingestao,
        "conectar",
        lambda: pytest.fail("não deve abrir o banco se faltar arquivo"),
    )

    with pytest.raises(SystemExit) as erro:
        ingestao.main()

    assert erro.value.code == 1
