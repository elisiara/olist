"""
Docstring de especificação para painel.py

Módulo de leitura, formatação e geração de gráficos do painel Olist.
A especificação abaixo documenta o comportamento esperado e as justificativas
técnicas e de negócio para cada regra adotada.

1. LEITURA
- ler(marts) -> dict nome -> DataFrame. Para cada nome, executa apenas:
  SELECT * FROM marts.<nome>. Nenhuma outra SQL é permitida.
- Conexão aberta com duckdb.connect("olist.duckdb", read_only=True) e fechada
  obrigatoriamente dentro de ler() (em bloco try...finally).
  Motivo: Uma conexão aberta em modo leitura segura o arquivo de banco de dados,
  impedindo que o pipeline de transformação (pipeline.marts) consiga gravar e
  publicar novos marts com o painel em execução.

2. NENHUM CÁLCULO
- É estritamente proibido realizar operações de agregação (como agrupar, somar,
  calcular média ou contagens), junções relacionais entre tabelas, pivôs ou
  qualquer cálculo aritmético entre colunas em painel.py e app.py.
  Permitido exclusivamente: ordenar linhas, filtrar linhas, head(n), renomear
  colunas e formatar strings de exibição.
  Motivo: A lógica analítica reside inteiramente nas consultas SQL dos data marts.
  Qualquer número novo apresentado na interface requer um novo arquivo .sql em
  marts. Se faltar algum indicador, a execução deve apontar qual mart está ausente.
  Única exceção permitida pela spec: o cálculo do complemento da taxa de recompra
  (100 - pct_clientes da linha com 1 pedido), já que o mart armazena o valor base.

3. LAYOUT (app.py)
- Layout wide, organizado verticalmente de cima para baixo.
- Cabeçalho: título à esquerda ("Olist · visão da operação") e filtro temporal à direita.
- Faixa 1: sete cartões de métricas (st.metric) na ordem exata definida.
- Faixa 2: gráfico de largura inteira com faturamento mensal em linha com marcadores.
- Faixa 3: três colunas iguais com receita por categoria (top 10), mix de pagamento
  e ticket médio por UF.
- Faixa 4: três colunas iguais com clientes por UF, nota por categoria (10 piores)
  e curva de concentração de vendedores.
- Gráficos padronizados: título com número do mart ("NN · Nome"), paleta unicolor,
  eixos identificados com unidade de medida e largura responsiva (width="stretch").
  Motivo: Garantir consistência visual, hierarquia clara da informação e rastreabilidade
  imediata de cada componente visual ao seu respectivo mart analítico.

4. FORMATO
- Funções puras sem dependência de streamlit ou conexão de banco de dados:
  reais(valor, casas=2), pct(valor, casas=1) e numero(valor, casas=0).
- Padrão brasileiro invariante: separador de milhar com ponto e separador decimal
  com vírgula, sem depender da configuração de locale do sistema operacional.
  Motivo: O formato dos números não pode variar conforme a máquina ou ambiente
  do usuário que executa a aplicação.
- Uma função dedicada por gráfico, recebendo o DataFrame e retornando a figura Plotly.
  Motivo: Permitir o reaproveitamento das mesmas funções visuais em outros contextos,
  como relatórios estáticos em HTML ou exportações em PDF.

5. FILTRO DE PERÍODO
- Componente st.select_slider com os meses disponíveis em vendas_mensais, com valor
  padrão de jan/2017 a ago/2018.
- Filtra exclusivamente as linhas do gráfico de faturamento mensal; os cartões e demais
  gráficos permanecem invariantes, com aviso explícito abaixo do filtro.
  Motivo: Filtrar fatias temporais equivale a uma restrição de SELECT; recalcular
  métricas globais para recortes parciais violaria a regra de não introduzir
  regras de negócio fora do SQL dos marts.

6. CACHE E TRATAMENTO DE ERROS
- Carregamento de dados protegido por st.cache_data, com botão para recarregar dados.
- Caso o arquivo olist.duckdb não exista, ou caso falte qualquer um dos marts
  necessários pelo item 3, exibe mensagem de erro (st.error) orientando a executar
  "uv run python -m pipeline.marts" e interrompe a execução com st.stop().
  Motivo: Evitar execução inconsistente e guiar o usuário diretamente para o comando
  que reconstrói o banco e as camadas analíticas.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Cor primária única para todos os gráficos do painel
COR_PRIMARIA = "#1f77b4"

# Lista canônica dos marts exigidos pelo Item 3 da especificação
MARTS_ITEM_3 = [
    "kpis",
    "recompra",
    "entrega_no_prazo",
    "vendas_mensais",
    "top_categorias",
    "mix_pagamento",
    "ticket_medio_por_estado",
    "clientes_por_uf",
    "nota_por_categoria",
    "vendedores_pareto",
]


class BancoNaoEncontradoError(FileNotFoundError):
    """Lançada quando o arquivo olist.duckdb não existe na raiz do projeto."""


class MartsAusentesError(Exception):
    """Lançada quando uma ou mais tabelas marts não existem no banco."""

    def __init__(self, faltando: list[str]) -> None:
        self.faltando = faltando
        super().__init__(f"Marts ausentes: {', '.join(faltando)}")


def ler(marts: Sequence[str] = MARTS_ITEM_3) -> dict[str, pd.DataFrame]:
    """
    Lê os marts solicitados do banco DuckDB.

    Para cada mart, executa estritamente 'SELECT * FROM marts.<nome>'.
    Abre e fecha a conexão em modo somente leitura (read_only=True)
    dentro da própria função, evitando travar o arquivo de banco de dados.
    """
    db_path = Path("olist.duckdb")
    if not db_path.exists():
        raise BancoNaoEncontradoError("olist.duckdb não encontrado")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        dados: dict[str, pd.DataFrame] = {}
        faltando: list[str] = []
        for nome in marts:
            try:
                dados[nome] = con.execute(f"SELECT * FROM marts.{nome}").df()
            except duckdb.CatalogException:
                faltando.append(nome)

        if faltando:
            raise MartsAusentesError(faltando)

        return dados
    finally:
        con.close()


def numero(valor: float | None, casas: int = 0) -> str:
    """
    Formata número com ponto para milhar e vírgula para decimal.

    Função pura e determinística, sem depender do locale do sistema operacional.
    """
    if valor is None or pd.isna(valor):
        return "-"
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def reais(valor: float | None, casas: int = 2) -> str:
    """Formata valor monetário em reais (R$) no padrão brasileiro."""
    if valor is None or pd.isna(valor):
        return "-"
    return f"R$ {numero(valor, casas=casas)}"


def pct(valor: float | None, casas: int = 1) -> str:
    """Formata valor percentual (%) no padrão brasileiro."""
    if valor is None or pd.isna(valor):
        return "-"
    return f"{numero(valor, casas=casas)}%"


def grafico_faturamento_mensal(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de linha com marcadores para o faturamento mensal (mart 01)."""
    fig = px.line(
        df,
        x="mes",
        y="receita",
        markers=True,
        title="01 · Faturamento mensal",
    )
    fig.update_traces(line_color=COR_PRIMARIA, marker={"color": COR_PRIMARIA})
    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title="Receita (R$)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_receita_por_categoria(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de barras horizontais com as 10 maiores categorias por receita (mart 02)."""
    # Ordena decrescente pela receita e recorta as 10 primeiras
    top10 = df.sort_values(by="receita", ascending=False).head(10)
    fig = px.bar(
        top10,
        x="receita",
        y="categoria",
        orientation="h",
        title="02 · Receita por categoria",
    )
    fig.update_traces(marker_color=COR_PRIMARIA)
    # autorange="reversed" garante a categoria de maior receita no topo
    fig.update_layout(
        yaxis={"autorange": "reversed", "title": "Categoria"},
        xaxis_title="Receita (R$)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_mix_pagamento(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de barras para o mix de formas de pagamento (mart 07)."""
    fig = px.bar(
        df,
        x="tipo",
        y="pct_valor",
        title="07 · Mix de pagamento",
    )
    fig.update_traces(marker_color=COR_PRIMARIA)
    fig.update_layout(
        xaxis_title="Forma de pagamento",
        yaxis_title="Participação (% do valor)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_ticket_medio_por_uf(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de barras horizontais do ticket médio por UF (mart 06)."""
    # Ordena decrescente para posicionar PB no topo e SP na base
    df_ordenado = df.sort_values(by="ticket_medio", ascending=False)
    fig = px.bar(
        df_ordenado,
        x="ticket_medio",
        y="uf",
        orientation="h",
        title="06 · Ticket médio por estado",
    )
    fig.update_traces(marker_color=COR_PRIMARIA)
    fig.update_layout(
        yaxis={"autorange": "reversed", "title": "UF"},
        xaxis_title="Ticket médio (R$)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_clientes_por_uf(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de barras horizontais de clientes por UF (mart 12)."""
    # Ordena decrescente para posicionar SP no topo
    df_ordenado = df.sort_values(by="clientes", ascending=False)
    fig = px.bar(
        df_ordenado,
        x="clientes",
        y="uf",
        orientation="h",
        title="12 · Clientes por UF",
    )
    fig.update_traces(marker_color=COR_PRIMARIA)
    fig.update_layout(
        yaxis={"autorange": "reversed", "title": "UF"},
        xaxis_title="Clientes",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_nota_por_categoria(df: pd.DataFrame) -> go.Figure:
    """Gera gráfico de dispersão pontual com as 10 piores categorias avaliadas (mart 04)."""
    # Seleciona as 10 primeiras posições da classificação de piores notas
    df_top10_piores = df.sort_values(by="posicao_pior", ascending=True).head(10)
    fig = px.scatter(
        df_top10_piores,
        x="nota_media",
        y="categoria",
        title="04 · Nota por categoria",
    )
    fig.update_traces(marker={"color": COR_PRIMARIA, "size": 10})
    # autorange="reversed" coloca a pior nota (office_furniture) no topo
    fig.update_layout(
        yaxis={"autorange": "reversed", "title": "Categoria"},
        xaxis_title="Nota média (1 a 5)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def grafico_concentracao_vendedores(df: pd.DataFrame) -> go.Figure:
    """Gera curva de Pareto da concentração acumulada de vendas por vendedor (mart 09)."""
    df_ordenado = df.sort_values(by="posicao", ascending=True)
    fig = px.line(
        df_ordenado,
        x="posicao",
        y="pct_acumulado",
        title="09 · Concentração de vendedores",
    )
    fig.update_traces(line_color=COR_PRIMARIA)
    # Linha tracejada de referência no limiar de 80% de receita
    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color="#888888",
        annotation_text="80%",
        annotation_position="bottom right",
    )
    fig.update_layout(
        xaxis_title="Posição do vendedor",
        yaxis_title="Receita acumulada (%)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig
