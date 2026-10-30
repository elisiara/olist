from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

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

# Configuração da página conforme especificação
st.set_page_config(page_title="Olist · visão da operação", layout="wide")

# Verificação inicial da existência do banco DuckDB
if not Path("olist.duckdb").exists():
    st.error(
        f"Banco de dados 'olist.duckdb' não encontrado. Faltam os seguintes marts: "
        f"{', '.join(MARTS_ITEM_3)}.\n\n"
        "Execute o comando: `uv run python -m pipeline.marts`"
    )
    st.stop()


@st.cache_data
def carregar_dados() -> dict[str, pd.DataFrame]:
    """Carrega todos os data marts do item 3 em cache de memória."""
    return ler(MARTS_ITEM_3)


try:
    dados = carregar_dados()
except MartsAusentesError as erro:
    st.error(
        f"Faltam os seguintes marts no banco de dados: {', '.join(erro.faltando)}.\n\n"
        "Execute o comando: `uv run python -m pipeline.marts`"
    )
    st.stop()
except BancoNaoEncontradoError:
    st.error(
        f"Banco de dados 'olist.duckdb' não encontrado. Faltam os seguintes marts: "
        f"{', '.join(MARTS_ITEM_3)}.\n\n"
        "Execute o comando: `uv run python -m pipeline.marts`"
    )
    st.stop()

# Dicionário de abreviações dos meses para o seletor temporal
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
    """Converte Timestamp em formato legível 'mmm/aaaa' (ex.: 'jan/2017')."""
    return f"{MESES_ROTULOS[ts.month]}/{ts.year}"


# Extração e preparação das opções do filtro de meses
df_vendas = dados["vendas_mensais"]
meses_disponiveis = df_vendas["mes"].tolist()

# Define limites padrão exigidos: jan/2017 a ago/2018
inicio_padrao = [m for m in meses_disponiveis if m.year == 2017 and m.month == 1][0]
fim_padrao = [m for m in meses_disponiveis if m.year == 2018 and m.month == 8][0]

# Cabeçalho: título à esquerda e filtro de período à direita
col_titulo, col_acoes = st.columns([1, 1])

with col_titulo:
    st.title("Olist · visão da operação")

with col_acoes:
    sub_filtro, sub_btn = st.columns([4, 1])
    with sub_btn:
        st.write("")
        st.write("")
        if st.button("Recarregar dados"):
            st.cache_data.clear()
            st.rerun()

    with sub_filtro:
        periodo = st.select_slider(
            "Período de vendas",
            options=meses_disponiveis,
            value=(inicio_padrao, fim_padrao),
            format_func=formatar_mes,
            label_visibility="collapsed",
        )
        st.caption("os cartões valem para o período inteiro")

# Filtragem de linhas do faturamento mensal conforme seleção
df_vendas_filtrado = df_vendas[
    (df_vendas["mes"] >= periodo[0]) & (df_vendas["mes"] <= periodo[1])
]

# Faixa 1: Sete cartões de métricas (st.metric)
kpis = dados["kpis"]
recompra = dados["recompra"]
entrega_no_prazo = dados["entrega_no_prazo"]

# Único cálculo permitido pela spec: complemento da recompra (100 - % com 1 pedido)
linha_um_pedido = recompra[recompra["pedidos_por_cliente"] == 1]
pct_recompra = 100 - float(linha_um_pedido["pct_clientes"].iloc[0])

faixa1_cols = st.columns(7)

faixa1_cols[0].metric(
    "Ticket médio",
    reais(kpis["ticket_medio"].iloc[0], casas=2),
)
faixa1_cols[1].metric(
    "Cancelados · % de todos os pedidos",
    pct(kpis["pct_cancelados"].iloc[0], casas=2),
)
faixa1_cols[2].metric(
    "Peso do frete",
    pct(kpis["pct_frete"].iloc[0], casas=1),
)
faixa1_cols[3].metric(
    "Recompra",
    pct(pct_recompra, casas=2),
)
faixa1_cols[4].metric(
    "No prazo",
    pct(entrega_no_prazo["pct_no_prazo"].iloc[0], casas=1),
)
faixa1_cols[5].metric(
    "Dias até entregar",
    numero(kpis["dias_entrega"].iloc[0], casas=1),
)
faixa1_cols[6].metric(
    "Nota média",
    numero(kpis["nota_media"].iloc[0], casas=2),
)

# Faixa 2: Faturamento mensal em largura inteira
st.plotly_chart(
    grafico_faturamento_mensal(df_vendas_filtrado),
    width="stretch",
)

# Faixa 3: Três colunas iguais
faixa3_col1, faixa3_col2, faixa3_col3 = st.columns(3)

with faixa3_col1:
    st.plotly_chart(
        grafico_receita_por_categoria(dados["top_categorias"]),
        width="stretch",
    )

with faixa3_col2:
    st.plotly_chart(
        grafico_mix_pagamento(dados["mix_pagamento"]),
        width="stretch",
    )

with faixa3_col3:
    st.plotly_chart(
        grafico_ticket_medio_por_uf(dados["ticket_medio_por_estado"]),
        width="stretch",
    )

# Faixa 4: Três colunas iguais
faixa4_col1, faixa4_col2, faixa4_col3 = st.columns(3)

with faixa4_col1:
    st.plotly_chart(
        grafico_clientes_por_uf(dados["clientes_por_uf"]),
        width="stretch",
    )

with faixa4_col2:
    st.plotly_chart(
        grafico_nota_por_categoria(dados["nota_por_categoria"]),
        width="stretch",
    )

with faixa4_col3:
    st.plotly_chart(
        grafico_concentracao_vendedores(dados["vendedores_pareto"]),
        width="stretch",
    )

