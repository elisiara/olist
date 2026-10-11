"""
Docstring de especificação para pipeline/ingestao.py

Este script implementa a etapa de ingestão do pipeline de dados da Olist.
A regra central aqui é preservar a fronteira entre "o dado que chegou" e
"o dado que eu decidi", então nada é corrigido, normalizado ou deduplicado:
o objetivo é apenas carregar os nove arquivos CSV.gz em raw exatamente como
chegaram, sem inferência de tipos nem alteração de colunas.

A ingestão deve ser reexecutável sem efeito colateral: cada execução recria
a tabela no banco (CREATE OR REPLACE), então rodar dez vezes produz o mesmo
resultado que rodar uma. Isso elimina a ambiguidade de "append" e permite
testar sem medo.

Também é obrigatório verificar a existência dos nove arquivos antes de abrir
o banco. Se faltar qualquer um, o script não grava nada e encerra com exit
code 1 para evitar um dashboard parcialmente populado que pareça correto.

O arquivo é lido diretamente em .csv.gz, com encoding utf-8, sem descompactar
e sem adivinhar charset; a conversão de tipos fica fora desta etapa, conforme
a espec. A saída em tela é o único instrumento de conferência da etapa:
uma linha por tabela com o nome qualificado e a contagem vindo do banco
e uma linha final com o total. Essa saída também deve ter números com
milhar separado por ponto e UTF-8 configurado no stdout para funcionar no
Prompt de Comando do Windows.
"""

from __future__ import annotations

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

MAPA_TABELAS = {
    "olist_orders_dataset.csv.gz": "pedidos",
    "olist_order_items_dataset.csv.gz": "itens_pedido",
    "olist_order_payments_dataset.csv.gz": "pagamentos",
    "olist_order_reviews_dataset.csv.gz": "avaliacoes",
    "olist_customers_dataset.csv.gz": "clientes",
    "olist_sellers_dataset.csv.gz": "vendedores",
    "olist_products_dataset.csv.gz": "produtos",
    "product_category_name_translation.csv.gz": "traducao_categorias",
    "olist_geolocation_dataset.csv.gz": "geolocalizacao",
}


def _formatar_numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    faltantes = [
        nome_arquivo
        for nome_arquivo in MAPA_TABELAS
        if not (PASTA_RAW / nome_arquivo).exists()
    ]

    if faltantes:
        print(f"Arquivos faltando em: {PASTA_RAW}")
        for nome_arquivo in faltantes:
            print(f" - {nome_arquivo}")
        raise SystemExit(1)

    con = conectar()
    try:
        criar_schema(con, "raw")

        total = 0
        for nome_arquivo, tabela in MAPA_TABELAS.items():
            caminho = PASTA_RAW / nome_arquivo

            df = pd.read_csv(
                caminho,
                encoding="utf-8",
                compression="gzip",
                dtype=str,
                keep_default_na=True,
            )

            contagem = gravar(con, df, "raw", tabela)
            print(f"raw.{tabela}: {_formatar_numero(contagem)}")
            total += contagem

        print(f"TOTAL: {_formatar_numero(total)}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
