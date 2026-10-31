from datetime import datetime, timedelta

import duckdb
import pandas as pd

import relatorio


def _criar_banco_com_marts(caminho):
    # Datas mensais inventadas cobrem o início e o fim do período do relatório.
    meses = pd.date_range("2017-01-01", "2018-08-01", freq="MS")
    tabelas = {
        "kpis": pd.DataFrame(
            {
                "ticket_medio": [42.5],
                "pct_cancelados": [10.0],
                "pct_frete": [8.0],
                "dias_entrega": [4.5],
                "nota_media": [4.2],
            }
        ),
        "recompra": pd.DataFrame(
            {
                "pedidos_por_cliente": [1, 2],
                "pct_clientes": [75.0, 25.0],
            }
        ),
        "entrega_no_prazo": pd.DataFrame({"pct_no_prazo": [80.0]}),
        "vendas_mensais": pd.DataFrame(
            {
                "mes": meses,
                "pedidos": [2] * len(meses),
                "receita": [100.0 + indice for indice in range(len(meses))],
            }
        ),
        "top_categorias": pd.DataFrame(
            {"categoria": ["livros", "casa"], "receita": [40.0, 30.0]}
        ),
        "mix_pagamento": pd.DataFrame(
            {"tipo": ["cartao", "boleto"], "pct_valor": [60.0, 40.0]}
        ),
        "ticket_medio_por_estado": pd.DataFrame(
            {"uf": ["AA", "BB"], "ticket_medio": [40.0, 50.0]}
        ),
        "clientes_por_uf": pd.DataFrame({"uf": ["AA", "BB"], "clientes": [3, 2]}),
        "nota_por_categoria": pd.DataFrame(
            {
                "categoria": ["livros", "casa"],
                "posicao_pior": [1, 2],
                "nota_media": [3.0, 4.0],
            }
        ),
        "vendedores_pareto": pd.DataFrame(
            {
                "posicao": [1, 2],
                "pct_acumulado": [55.0, 100.0],
            }
        ),
    }
    with duckdb.connect(str(caminho)) as con:
        con.execute("CREATE SCHEMA marts")
        for nome, dados in tabelas.items():
            con.register("dados", dados)
            con.execute(f"CREATE TABLE marts.{nome} AS SELECT * FROM dados")


def test_gerar_relatorio_em_tmp_path_muda_somente_rodape(tmp_path, monkeypatch):
    banco = tmp_path / "olist.duckdb"
    _criar_banco_com_marts(banco)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(relatorio, "ROOT", tmp_path)

    class Relogio:
        instante = datetime(2026, 10, 30, 12, 0)

        @classmethod
        def now(cls):
            return cls.instante

    monkeypatch.setattr(relatorio, "datetime", Relogio)
    primeiro = relatorio.gerar_relatorio()
    html_primeiro = primeiro.read_text(encoding="utf-8")
    Relogio.instante += timedelta(minutes=1)
    segundo = relatorio.gerar_relatorio()
    html_segundo = segundo.read_text(encoding="utf-8")

    assert primeiro == tmp_path / "relatorio.html"
    assert segundo.exists()
    rodape_primeiro = "<footer>Dados de 30/10/2026 12:00</footer>"
    rodape_segundo = "<footer>Dados de 30/10/2026 12:01</footer>"
    assert rodape_primeiro in html_primeiro
    assert rodape_segundo in html_segundo
    assert html_primeiro.replace(rodape_primeiro, "<footer>RODAPE</footer>") == (
        html_segundo.replace(rodape_segundo, "<footer>RODAPE</footer>")
    )
    assert "R$ 42,50" in html_primeiro

    relatorio.main()
    assert (tmp_path / "relatorio.html").stat().st_size > 0
