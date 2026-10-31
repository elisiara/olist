import duckdb
import pandas as pd
import pytest
from plotly.graph_objects import Figure

import painel


def test_formatadores_exibem_padrao_br_e_valores_ausentes():
    # Valores fabricados cobrem milhar, centavos e percentual com arredondamento.
    assert painel.reais(1234.5) == "R$ 1.234,50"
    assert painel.pct(12.345, casas=2) == "12,35%"
    assert painel.numero(1234567.89, casas=2) == "1.234.567,89"
    assert painel.reais(None) == "-"
    assert painel.pct(float("nan")) == "-"
    assert painel.numero(None) == "-"


def test_graficos_devolvem_figuras_com_pontos_das_linhas_inventadas():
    # Cada DataFrame contém duas observações feitas apenas para testar os gráficos.
    entradas = [
        (
            painel.grafico_faturamento_mensal,
            pd.DataFrame(
                {
                    "mes": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                    "receita": [10.0, 20.0],
                }
            ),
        ),
        (
            painel.grafico_receita_por_categoria,
            pd.DataFrame({"categoria": ["livros", "casa"], "receita": [8.0, 12.0]}),
        ),
        (
            painel.grafico_mix_pagamento,
            pd.DataFrame({"tipo": ["cartao", "boleto"], "pct_valor": [60.0, 40.0]}),
        ),
        (
            painel.grafico_ticket_medio_por_uf,
            pd.DataFrame({"uf": ["AA", "BB"], "ticket_medio": [15.0, 25.0]}),
        ),
        (
            painel.grafico_clientes_por_uf,
            pd.DataFrame({"uf": ["AA", "BB"], "clientes": [2, 3]}),
        ),
        (
            painel.grafico_nota_por_categoria,
            pd.DataFrame(
                {
                    "categoria": ["livros", "casa"],
                    "posicao_pior": [1, 2],
                    "nota_media": [2.0, 4.0],
                }
            ),
        ),
        (
            painel.grafico_concentracao_vendedores,
            pd.DataFrame(
                {
                    "posicao": [1, 2],
                    "pct_acumulado": [55.0, 100.0],
                }
            ),
        ),
    ]

    for funcao, dados in entradas:
        figura = funcao(dados)
        assert isinstance(figura, Figure)
        pontos = figura.data[0].x
        if pontos is None:
            pontos = figura.data[0].y
        assert len(pontos) == len(dados)


def test_ler_retorna_dataframe_do_banco_temporario(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    banco = tmp_path / "olist.duckdb"
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.exemplo AS SELECT 17 AS valor")

    resultado = painel.ler(["exemplo"])

    assert list(resultado) == ["exemplo"]
    assert resultado["exemplo"]["valor"].tolist() == [17]


def test_banco_ausente_gera_erro_especifico(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(painel.BancoNaoEncontradoError):
        painel.ler(["exemplo"])


def test_marts_ausentes_sao_listados(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    banco = tmp_path / "olist.duckdb"
    with duckdb.connect(str(banco)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.existe AS SELECT 1 AS valor")

    with pytest.raises(painel.MartsAusentesError) as erro:
        painel.ler(["existe", "falta_um", "falta_dois"])

    assert erro.value.faltando == ["falta_um", "falta_dois"]
