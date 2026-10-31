import pandas as pd

from pipeline import db


def test_conectar_criar_schema_e_gravar_usam_banco_temporario(tmp_path, monkeypatch):
    # O caminho aponta para a raiz temporária, nunca para o banco do projeto.
    monkeypatch.setattr(db, "__file__", str(tmp_path / "pipeline" / "db.py"))

    with db.conectar() as con:
        db.criar_schema(con, "teste")
        # A primeira gravação prova que a contagem vem da tabela persistida.
        primeira = pd.DataFrame({"codigo": ["001", "002"], "valor": [10, 20]})
        assert db.gravar(con, primeira, "teste", "amostra") == 2

        # A segunda gravação prova que CREATE OR REPLACE não acumula linhas.
        segunda = pd.DataFrame({"codigo": ["003"], "valor": [30]})
        assert db.gravar(con, segunda, "teste", "amostra") == 1
        assert con.execute("SELECT codigo FROM teste.amostra").fetchall() == [("003",)]

    assert (tmp_path / "olist.duckdb").exists()
