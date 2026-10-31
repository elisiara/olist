import copy
from decimal import Decimal

import duckdb
import pandas as pd
import pytest

from pipeline import transformacao


def _linha_valida(tabela):
    linha = {}
    for origem, expressao, destino in transformacao.CONFIG_TABELAS[tabela]["colunas"]:
        if expressao.startswith("strptime("):
            valor = "2024-01-02 12:34:56"
        elif "AS DATE)" in expressao:
            valor = "2024-01-02"
        elif "AS INTEGER)" in expressao:
            valor = "1"
        elif "DECIMAL(10,2)" in expressao:
            valor = "10.25"
        else:
            valor = f"{tabela}_{destino}"
        linha[origem] = valor
    return linha


def _criar_banco_raw(caminho, substituicoes=None):
    substituicoes = substituicoes or {}
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA raw")
    for tabela, configuracao in transformacao.CONFIG_TABELAS.items():
        # Uma linha válida por tabela permite exercitar todas as projeções configuradas.
        linhas = substituicoes.get(tabela, [_linha_valida(tabela)])
        colunas = [origem for origem, _, _ in configuracao["colunas"]]
        dados = pd.DataFrame(linhas, columns=colunas, dtype=object)
        con.register("dados", dados)
        con.execute(f"CREATE TABLE raw.{tabela} AS SELECT * FROM dados")
    con.close()


def _pedido(pedido_id, status):
    linha = _linha_valida("pedidos")
    linha.update(
        {
            "order_id": pedido_id,
            "customer_id": f"cliente_{pedido_id}",
            "order_status": status,
            "order_purchase_timestamp": "2024-02-01 10:00:00",
            "order_approved_at": "2024-02-01 10:10:00",
            "order_delivered_carrier_date": "2024-02-02 10:00:00",
            "order_delivered_customer_date": "2024-02-03 15:00:00",
            "order_estimated_delivery_date": "2024-02-03",
        }
    )
    return linha


def _item(pedido_id, sequencia, preco):
    linha = _linha_valida("itens_pedido")
    linha.update(
        {
            "order_id": pedido_id,
            "order_item_id": str(sequencia),
            "product_id": f"produto_{sequencia}",
            "seller_id": f"vendedor_{sequencia}",
            "shipping_limit_date": "2024-02-02 00:00:00",
            "price": preco,
            "freight_value": "2.00",
        }
    )
    return linha


def test_duplicata_exata_sai_e_tipos_sao_convertidos(tmp_path, monkeypatch):
    pedido = _pedido("pedido_1", "delivered")
    cancelado = _pedido("pedido_2", "canceled")
    # Pedido cancelado prova que data legitimamente ausente continua nula.
    cancelado["order_delivered_carrier_date"] = None
    cancelado["order_delivered_customer_date"] = None
    item_um = _item("pedido_1", 1, "10.20")
    # A repetição idêntica deve desaparecer, mas o segundo item do pedido fica.
    substituicoes = {
        "pedidos": [pedido, copy.deepcopy(pedido), cancelado],
        "itens_pedido": [item_um, copy.deepcopy(item_um), _item("pedido_1", 2, "3.40")],
    }
    banco = tmp_path / "transformacao.duckdb"
    _criar_banco_raw(banco, substituicoes)
    monkeypatch.setattr(transformacao, "conectar", lambda: duckdb.connect(str(banco)))

    transformacao.main()

    with duckdb.connect(str(banco)) as con:
        assert con.execute("SELECT COUNT(*) FROM raw.itens_pedido").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM refined.pedidos").fetchone()[0] == 2
        assert (
            con.execute("SELECT COUNT(*) FROM refined.itens_pedido").fetchone()[0] == 2
        )
        assert con.execute(
            "SELECT typeof(data_compra), typeof(data_entrega_prevista) "
            "FROM refined.pedidos WHERE pedido_id = 'pedido_1'"
        ).fetchone() == ("TIMESTAMP", "DATE")
        assert con.execute(
            "SELECT typeof(preco) FROM refined.itens_pedido LIMIT 1"
        ).fetchone() == ("DECIMAL(10,2)",)
        assert con.execute(
            "SELECT SUM(preco) FROM refined.itens_pedido"
        ).fetchone() == (Decimal("13.60"),)
        assert con.execute(
            "SELECT data_entrega FROM refined.pedidos WHERE pedido_id = 'pedido_2'"
        ).fetchone() == (None,)
        coluna, mensagem = transformacao._diagnosticar_erro_conversao(
            con, "pedidos", [("ausente", "coluna_ausente", "destino")]
        )
        assert coluna == "ausente"
        assert mensagem


def test_tabela_raw_faltando_encerra_com_system_exit(tmp_path, monkeypatch):
    banco = tmp_path / "raw_incompleto.duckdb"
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA raw")
        con.execute("CREATE TABLE raw.pedidos (order_id VARCHAR)")
    monkeypatch.setattr(transformacao, "conectar", lambda: duckdb.connect(str(banco)))

    with pytest.raises(SystemExit) as erro:
        transformacao.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM information_schema.schemata "
                "WHERE schema_name = 'refined'"
            ).fetchone()[0]
            == 0
        )


def test_valor_que_nao_converte_encerra_sem_virar_nulo(tmp_path, monkeypatch):
    item_invalido = _item("pedido_1", 1, "valor-invalido")
    banco = tmp_path / "valor_invalido.duckdb"
    _criar_banco_raw(banco, {"itens_pedido": [item_invalido]})
    monkeypatch.setattr(transformacao, "conectar", lambda: duckdb.connect(str(banco)))

    with pytest.raises(SystemExit) as erro:
        transformacao.main()

    assert erro.value.code == 1
    with duckdb.connect(str(banco)) as con:
        assert con.execute("SELECT price FROM raw.itens_pedido").fetchone() == (
            "valor-invalido",
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'refined' AND table_name = 'itens_pedido'"
            ).fetchone()[0]
            == 0
        )


def test_chave_repetida_com_conteudo_diferente_encerra(tmp_path, monkeypatch):
    primeiro = _item("pedido_1", 1, "10.20")
    # Mesmo pedido e sequência, com preço divergente, é conflito e não duplicata.
    conflitante = _item("pedido_1", 1, "11.20")
    banco = tmp_path / "chave_conflitante.duckdb"
    _criar_banco_raw(banco, {"itens_pedido": [primeiro, conflitante]})
    monkeypatch.setattr(transformacao, "conectar", lambda: duckdb.connect(str(banco)))

    with pytest.raises(SystemExit) as erro:
        transformacao.main()

    assert erro.value.code == 1
