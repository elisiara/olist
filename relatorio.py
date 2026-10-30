from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import sys

import pandas as pd

from painel import (
    MARTS_ITEM_3,
    BancoNaoEncontradoError,
    MartsAusentesError,
    grafico_clientes_por_uf,
    grafico_concentracao_vendedores,
    grafico_faturamento_mensal,
    grafico_mix_pagamento,
    grafico_nota_por_categoria,
    grafico_receita_por_categoria,
    grafico_ticket_medio_por_uf,
    ler,
    numero,
    pct,
    reais,
)

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "relatorio.html"

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


def formatar_mes(ts: pd.Timestamp) -> str:
    return f"{MESES_ROTULOS[ts.month]}/{ts.year}"


def periodo_padrao(df_vendas: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    meses_disponiveis = df_vendas["mes"].tolist()
    inicio_padrao = next(m for m in meses_disponiveis if m.year == 2017 and m.month == 1)
    fim_padrao = next(m for m in meses_disponiveis if m.year == 2018 and m.month == 8)
    return inicio_padrao, fim_padrao


def gerar_cartoes(dados: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
    kpis = dados["kpis"]
    recompra = dados["recompra"]
    entrega_no_prazo = dados["entrega_no_prazo"]

    linha_um_pedido = recompra[recompra["pedidos_por_cliente"] == 1]
    pct_recompra = 100 - float(linha_um_pedido["pct_clientes"].iloc[0])

    return [
        ("Ticket médio", reais(kpis["ticket_medio"].iloc[0], casas=2)),
        ("Cancelados · % de todos os pedidos", pct(kpis["pct_cancelados"].iloc[0], casas=2)),
        ("Peso do frete", pct(kpis["pct_frete"].iloc[0], casas=1)),
        ("Recompra", pct(pct_recompra, casas=2)),
        ("No prazo", pct(entrega_no_prazo["pct_no_prazo"].iloc[0], casas=1)),
        ("Dias até entregar", numero(kpis["dias_entrega"].iloc[0], casas=1)),
        ("Nota média", numero(kpis["nota_media"].iloc[0], casas=2)),
    ]


def montar_html(dados: dict[str, pd.DataFrame]) -> str:
    df_vendas = dados["vendas_mensais"]
    inicio, fim = periodo_padrao(df_vendas)
    periodo_texto = f"{formatar_mes(inicio)} a {formatar_mes(fim)}"
    df_vendas_filtrado = df_vendas[
        (df_vendas["mes"] >= inicio) & (df_vendas["mes"] <= fim)
    ]

    figures = [
        grafico_faturamento_mensal(df_vendas_filtrado),
        grafico_receita_por_categoria(dados["top_categorias"]),
        grafico_mix_pagamento(dados["mix_pagamento"]),
        grafico_ticket_medio_por_uf(dados["ticket_medio_por_estado"]),
        grafico_clientes_por_uf(dados["clientes_por_uf"]),
        grafico_nota_por_categoria(dados["nota_por_categoria"]),
        grafico_concentracao_vendedores(dados["vendedores_pareto"]),
    ]

    html_parts: list[str] = []
    for idx, fig in enumerate(figures, start=1):
        include_plotlyjs = "cdn" if idx == 1 else False
        html_parts.append(
            fig.to_html(
                full_html=False,
                include_plotlyjs=include_plotlyjs,
                div_id=f"g{idx:02d}",
            )
        )

    cartoes = gerar_cartoes(dados)
    cartoes_html = "".join(
        f"<div class='card'><div class='label'>{escape(label)}</div><div class='value'>{escape(valor)}</div></div>"
        for label, valor in cartoes
    )

    grafico_html = "".join(
        f"<div class='chart'>{fig_html}</div>" for fig_html in html_parts
    )

    agora = datetime.now()
    footer = agora.strftime("Dados de %d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang='pt-BR'>
  <head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Olist · visão da operação</title>
    <style>
      :root {{
        --bg: #f5f7fa;
        --card: #ffffff;
        --text: #212529;
        --muted: #6c757d;
        --border: #dfe3e8;
        --shadow: rgba(0, 0, 0, 0.04);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
        background: var(--bg);
        color: var(--text);
      }}
      .container {{
        max-width: 1500px;
        margin: 0 auto;
        padding: 24px 20px 12px;
      }}
      .header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 24px;
        margin-bottom: 18px;
      }}
      h1 {{
        margin: 0;
        font-size: clamp(1.8rem, 2.2vw, 2.5rem);
        font-weight: 700;
      }}
      .periodo {{
        font-size: 1.1rem;
        color: var(--muted);
        font-weight: 600;
      }}
      .faixa {{
        margin: 18px 0 26px;
      }}
      .cards {{
        display: grid;
        grid-template-columns: repeat(7, minmax(140px, 1fr));
        gap: 12px;
      }}
      .card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 2px 8px var(--shadow);
        padding: 14px 16px;
        min-height: 92px;
      }}
      .label {{
        font-size: 0.82rem;
        color: var(--muted);
        margin-bottom: 8px;
        line-height: 1.3;
      }}
      .value {{
        font-size: clamp(1.12rem, 1.7vw, 1.5rem);
        font-weight: 700;
        white-space: nowrap;
      }}
      .grafico-largo {{
        display: block;
        width: 100%;
      }}
      .graficos-3col {{
        display: grid;
        grid-template-columns: repeat(3, minmax(260px, 1fr));
        gap: 16px;
      }}
      .chart {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 2px 8px var(--shadow);
        padding: 8px;
        overflow: hidden;
      }}
      .chart > div {{
        width: 100%;
      }}
      .rodape {{
        margin-top: 20px;
        padding-top: 12px;
        border-top: 1px solid var(--border);
        font-size: 0.95rem;
        color: var(--muted);
        text-align: right;
      }}
      @media (max-width: 1100px) {{
        .cards {{
          grid-template-columns: repeat(2, minmax(180px, 1fr));
        }}
        .graficos-3col {{
          grid-template-columns: 1fr;
        }}
        .header {{
          flex-direction: column;
          align-items: flex-start;
        }}
      }}
    </style>
  </head>
  <body>
    <div class='container'>
      <div class='header'>
        <h1>Olist · visão da operação · {escape(periodo_texto)}</h1>
      </div>

      <div class='faixa'>
        <div class='cards'>{cartoes_html}</div>
      </div>

      <div class='faixa'>
        <div class='grafico-largo'>{html_parts[0]}</div>
      </div>

      <div class='faixa'>
        <div class='graficos-3col'>
          {html_parts[1]}
          {html_parts[2]}
          {html_parts[3]}
        </div>
      </div>

      <div class='faixa'>
        <div class='graficos-3col'>
          {html_parts[4]}
          {html_parts[5]}
          {html_parts[6]}
        </div>
      </div>

      <div class='rodape'>{escape(footer)}</div>
    </div>
  </body>
</html>
"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        dados = ler(MARTS_ITEM_3)
    except (BancoNaoEncontradoError, MartsAusentesError) as erro:
        print(str(erro), file=sys.stderr)
        raise SystemExit(1) from erro

    html = montar_html(dados)
    HTML_PATH.write_text(html, encoding="utf-8")

    tamanho_kb = HTML_PATH.stat().st_size / 1024
    print(f"Caminho: {HTML_PATH.resolve()}")
    print(f"Tamanho: {tamanho_kb:.1f} KB")


if __name__ == "__main__":
    main()
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
