from datetime import date
from pathlib import Path

import duckdb
import pytest

from pipeline import marts


def _preparar_marts(tmp_path, monkeypatch, nomes_sql=()):
    banco = tmp_path / "warehouse.duckdb"
    sql_dir = tmp_path / "sql_marts"
    sql_dir.mkdir()
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA refined")
        # A presença das oito tabelas satisfaz a validação de entrada do orquestrador.
        for tabela in marts.TABELAS_REFINED:
            con.execute(f"CREATE TABLE refined.{tabela} (id INTEGER)")
    monkeypatch.setattr(marts, "conectar", lambda: duckdb.connect(str(banco)))
    monkeypatch.setattr(marts, "PASTA_SQL_MARTS", sql_dir)
    for nome, sql in nomes_sql:
        (sql_dir / nome).write_text(sql, encoding="utf-8")
    return banco, sql_dir


def test_arquivo_sem_prefixo_para_antes_de_executar_sql(tmp_path, monkeypatch):
    banco, sql_dir = _preparar_marts(
        tmp_path,
        monkeypatch,
        [
            ("01_valido.sql", "SELECT 1 AS valor"),
            # SQL inválida prova que nenhum arquivo é executado antes da validação global.
            ("invalido.sql", "SELECT FROM"),
        ],
    )
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.anterior AS SELECT 9 AS valor")

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert con.execute("SELECT * FROM marts.anterior").fetchall() == [(9,)]
        assert not con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'marts' AND table_name = 'valido'"
        ).fetchone()[0]
    assert (sql_dir / "invalido.sql").exists()


def test_mart_vazio_aborta_e_preserva_schema_publicado(tmp_path, monkeypatch):
    banco, _ = _preparar_marts(
        tmp_path,
        monkeypatch,
        [("01_vazio.sql", "SELECT * FROM refined.pedidos")],
    )
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.anterior AS SELECT 7 AS valor")

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'marts'"
        ).fetchall() == [("anterior",)]
        assert con.execute("SELECT * FROM marts.anterior").fetchall() == [(7,)]


def test_arquivo_sql_apagado_remove_mart_na_execucao_seguinte(tmp_path, monkeypatch):
    banco, sql_dir = _preparar_marts(
        tmp_path,
        monkeypatch,
        [
            ("01_presente.sql", "SELECT 1 AS valor;  \n"),
            ("02_removido.sql", "SELECT 2 AS valor"),
        ],
    )
    marts.main()

    # Remover a fonte prova que o schema publicado é reconstruído sem marts órfãos.
    (sql_dir / "02_removido.sql").unlink()
    marts.main()

    with duckdb.connect(str(banco)) as con:
        assert con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'marts'"
        ).fetchall() == [("presente",)]


def test_arquivos_com_mesmo_nome_de_tabela_encerram(tmp_path, monkeypatch):
    banco, _ = _preparar_marts(
        tmp_path,
        monkeypatch,
        [
            ("01_repetido.sql", "SELECT 1 AS valor"),
            ("02_repetido.sql", "SELECT 2 AS valor"),
        ],
    )

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'marts'"
            ).fetchone()[0]
            == 0
        )


def test_falha_sql_aborta_e_reverte_schema(tmp_path, monkeypatch):
    banco, _ = _preparar_marts(
        tmp_path,
        monkeypatch,
        [("01_erro.sql", "SELECT FROM")],
    )
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.anterior AS SELECT 5 AS valor")

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert con.execute("SELECT * FROM marts.anterior").fetchall() == [(5,)]


def test_schema_refined_faltando_encerra(tmp_path, monkeypatch):
    banco = tmp_path / "refined_ausente.duckdb"
    monkeypatch.setattr(marts, "conectar", lambda: duckdb.connect(str(banco)))
    monkeypatch.setattr(marts, "PASTA_SQL_MARTS", tmp_path)

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1


def test_pasta_sql_sem_arquivos_encerra(tmp_path, monkeypatch):
    banco, _ = _preparar_marts(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    assert banco.exists()


def test_pasta_sql_inexistente_encerra(tmp_path, monkeypatch):
    banco, _ = _preparar_marts(tmp_path, monkeypatch)
    monkeypatch.setattr(marts, "PASTA_SQL_MARTS", tmp_path / "nao_existe")

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM information_schema.schemata "
                "WHERE schema_name = 'marts'"
            ).fetchone()[0]
            == 0
        )


def test_pasta_com_subdiretorio_sem_sql_valido_encerra(tmp_path, monkeypatch):
    _, sql_dir = _preparar_marts(tmp_path, monkeypatch)
    # O diretório existe, mas não contém arquivo SQL que possa virar um mart.
    (sql_dir / "subpasta").mkdir()

    with pytest.raises(SystemExit) as erro:
        marts.main()

    assert erro.value.code == 1


def test_venda_mensal_conta_pedido_com_dois_itens_uma_vez_e_exclui_cancelado(
    tmp_path,
):
    banco = tmp_path / "vendas_sql.duckdb"
    sql = (
        Path(__file__).resolve().parents[1] / "sql" / "marts" / "01_vendas_mensais.sql"
    ).read_text(encoding="utf-8")
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA refined")
        con.execute(
            "CREATE TABLE refined.pedidos "
            "(pedido_id VARCHAR, data_compra TIMESTAMP, status VARCHAR)"
        )
        con.execute(
            "CREATE TABLE refined.itens_pedido (pedido_id VARCHAR, preco DECIMAL(10,2))"
        )
        # Este pedido possui dois itens; o resultado deve contar o pedido uma vez.
        con.execute(
            "INSERT INTO refined.pedidos VALUES "
            "('pedido_multiplos_itens', '2024-01-15 10:00:00', 'delivered')"
        )
        # Este pedido cancelado e seu item caro não podem compor a receita.
        con.execute(
            "INSERT INTO refined.pedidos VALUES "
            "('pedido_cancelado', '2024-01-15 11:00:00', 'canceled')"
        )
        con.execute(
            "INSERT INTO refined.itens_pedido VALUES "
            "('pedido_multiplos_itens', 10.00), "
            "('pedido_multiplos_itens', 4.50), "
            "('pedido_cancelado', 99.00)"
        )

        linhas = con.execute(sql).fetchall()

    assert linhas == [(date(2024, 1, 1), 1, 14.50)]


def test_entrega_no_dia_previsto_as_15h_conta_como_no_prazo(tmp_path):
    banco = tmp_path / "prazo_sql.duckdb"
    sql = (
        Path(__file__).resolve().parents[1]
        / "sql"
        / "marts"
        / "03_entrega_no_prazo.sql"
    ).read_text(encoding="utf-8")
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA refined")
        con.execute(
            "CREATE TABLE refined.pedidos "
            "(status VARCHAR, data_entrega TIMESTAMP, data_entrega_prevista DATE)"
        )
        # Entrega às 15h no mesmo dia previsto precisa ser considerada pontual.
        con.execute(
            "INSERT INTO refined.pedidos VALUES "
            "('delivered', '2024-03-10 15:00:00', '2024-03-10')"
        )
        # Entrega um dia depois é o caso atrasado que compõe o denominador.
        con.execute(
            "INSERT INTO refined.pedidos VALUES "
            "('delivered', '2024-03-11 00:01:00', '2024-03-10')"
        )
        # Entrega sem data e pedido cancelado ficam fora da métrica.
        con.execute(
            "INSERT INTO refined.pedidos VALUES "
            "('delivered', NULL, '2024-03-10'), "
            "('canceled', '2024-03-10 15:00:00', '2024-03-10')"
        )

        linha = con.execute(sql).fetchone()

    assert linha == (2, 1, 1, 50.0)
