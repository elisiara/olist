from __future__ import annotations

import sys
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import painel

ROOT = Path(__file__).resolve().parent
MESES_ROTULOS = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


def formatar_mes(mes: pd.Timestamp) -> str:
    return f"{MESES_ROTULOS[mes.month]}/{mes.year}"


def montar_cartoes(dados: dict[str, pd.DataFrame]) -> str:
    kpis = dados["kpis"]
    recompra = dados["recompra"]
    entrega_no_prazo = dados["entrega_no_prazo"]

    linha_um_pedido = recompra[recompra["pedidos_por_cliente"] == 1]
    pct_recompra = 100 - float(linha_um_pedido["pct_clientes"].iloc[0])

    cartoes = [
        ("Ticket médio", painel.reais(kpis["ticket_medio"].iloc[0], casas=2)),
        (
            "Cancelados · % de todos os pedidos",
            painel.pct(kpis["pct_cancelados"].iloc[0], casas=2),
        ),
        ("Peso do frete", painel.pct(kpis["pct_frete"].iloc[0], casas=1)),
        ("Recompra", painel.pct(pct_recompra, casas=2)),
        (
            "No prazo",
            painel.pct(entrega_no_prazo["pct_no_prazo"].iloc[0], casas=1),
        ),
        (
            "Dias até entregar",
            painel.numero(kpis["dias_entrega"].iloc[0], casas=1),
        ),
        ("Nota média", painel.numero(kpis["nota_media"].iloc[0], casas=2)),
    ]
    return "\n".join(
        f'<article class="card"><div class="label">{escape(rotulo)}</div><div class="value">{escape(valor)}</div></article>'
        for rotulo, valor in cartoes
    )


def montar_graficos(dados: dict[str, pd.DataFrame]) -> tuple[str, str, str]:
    df_vendas = dados["vendas_mensais"]
    meses_disponiveis = df_vendas["mes"].tolist()
    inicio = next(m for m in meses_disponiveis if m.year == 2017 and m.month == 1)
    fim = next(m for m in meses_disponiveis if m.year == 2018 and m.month == 8)
    df_vendas_filtrado = df_vendas[
        (df_vendas["mes"] >= inicio) & (df_vendas["mes"] <= fim)
    ]
    periodo = f"{formatar_mes(inicio)} a {formatar_mes(fim)}"

    figura_faturamento = painel.grafico_faturamento_mensal(df_vendas_filtrado)
    figura_faturamento.update_layout(
        title=f"01 · Faturamento mensal · {periodo}"
    )

    faixa2 = figura_faturamento.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        div_id="g01",
        config={"responsive": True},
    )
    figuras_faixa3 = [
        painel.grafico_receita_por_categoria(dados["top_categorias"]),
        painel.grafico_mix_pagamento(dados["mix_pagamento"]),
        painel.grafico_ticket_medio_por_uf(dados["ticket_medio_por_estado"]),
    ]
    figuras_faixa4 = [
        painel.grafico_clientes_por_uf(dados["clientes_por_uf"]),
        painel.grafico_nota_por_categoria(dados["nota_por_categoria"]),
        painel.grafico_concentracao_vendedores(dados["vendedores_pareto"]),
    ]

    def faixa(figuras: list[go.Figure], primeiro_id: int) -> str:
        return "\n".join(
            figura.to_html(
                full_html=False,
                include_plotlyjs=False,
                div_id=f"g{indice:02}",
                config={"responsive": True},
            )
            for indice, figura in enumerate(figuras, start=primeiro_id)
        )

    return faixa2, faixa(figuras_faixa3, 2), faixa(figuras_faixa4, 5)


def gerar_relatorio() -> Path:
    dados = painel.ler()
    cartoes = montar_cartoes(dados)
    faixa2, faixa3, faixa4 = montar_graficos(dados)
    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Olist · visão da operação</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      color: #202124;
      background: #f7f9fc;
      font-family: Arial, sans-serif;
    }}
    main {{ max-width: 1600px; margin: 0 auto; }}
    h1 {{ margin: 0 0 20px; font-size: 1.8rem; }}
    section {{ margin-bottom: 20px; }}
    .cards, .charts {{
      display: grid;
      gap: 16px;
    }}
    .cards {{ grid-template-columns: repeat(7, minmax(0, 1fr)); }}
    .charts {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .card {{
      min-height: 100px;
      padding: 16px;
      background: white;
      border: 1px solid #e4e8ef;
      border-radius: 8px;
    }}
    .label {{ color: #5f6368; font-size: .85rem; }}
    .value {{ margin-top: 12px; font-size: 1.25rem; font-weight: 700; }}
    .chart {{
      min-width: 0;
      padding: 8px;
      background: white;
      border: 1px solid #e4e8ef;
      border-radius: 8px;
    }}
    .chart-wide {{ width: 100%; }}
    footer {{ padding: 8px 0; color: #5f6368; font-size: .85rem; }}
    @media (max-width: 1100px) {{
      .cards {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
      .charts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 700px) {{
      body {{ padding: 12px; }}
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .charts {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Olist · visão da operação</h1>
    <section class="cards" aria-label="Indicadores">{cartoes}</section>
    <section class="chart chart-wide" aria-label="Faturamento mensal">{faixa2}</section>
    <section class="charts" aria-label="Análises">{faixa3}</section>
    <section class="charts" aria-label="Análises complementares">{faixa4}</section>
    <footer>Dados de {gerado_em}</footer>
  </main>
</body>
</html>
"""
    destino = ROOT / "relatorio.html"
    destino.write_text(html, encoding="utf-8")
    return destino


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    caminho = gerar_relatorio()
    tamanho_kb = caminho.stat().st_size / 1024
    print(f"Arquivo gerado: {caminho}")
    print(f"Tamanho: {tamanho_kb:.2f} KB")


if __name__ == "__main__":
    main()
