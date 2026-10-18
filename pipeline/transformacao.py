"""
Docstring de especificação para pipeline/transformacao.py

Este módulo implementa a etapa de transformação e refinamento dos dados da
Olist, migrando os dados brutos do schema raw para o schema refined no DuckDB.
A especificação abaixo documenta o comportamento do pipeline e as justificativas
arquiteturais e de negócio para cada regra adotada.

1. ESCOPO
- Lê exclusivamente do schema raw e grava no schema refined. Nunca escreve em raw.
  Motivo: Preservar a imutabilidade da camada raw como fonte da verdade histórica
  e estabelecer uma fronteira limpa entre os dados brutos e os dados tratados.
- Oito tabelas fazem parte do escopo: pedidos, itens_pedido, pagamentos, clientes,
  vendedores, produtos, traducao_categorias e avaliacoes.
- A tabela geolocalizacao fica explicitamente de fora.
  Motivo: Nenhum data mart analítico do curso consome esses dados. Princípio YAGNI:
  não se gasta processamento nem complexidade para limpar o que ninguém vai ler.

2. NOMES
- Todas as colunas são renomeadas para português em snake_case de acordo com o
  mapa especificado, sem adições ou omissões.
  Motivo: Padronizar o vocabulário de negócio que os alunos digitarão de memória
  nos JOINs e agregações das aulas seguintes, eliminando discrepâncias léxicas.

3. TIPOS
- Datas com hora: convertidas para TIMESTAMP usando formato declarado
  '%Y-%m-%d %H:%M:%S' (data_compra, data_aprovacao, data_envio, data_entrega,
  data_limite_envio, data_resposta).
- data_entrega_prevista: convertida para DATE.
  Motivo: A parte horária é sempre 00:00:00 nas 99.441 linhas do dataset;
  manter componente de hora seria inventar precisão inexistente no fato original.
- data_criacao: convertida para DATE.
  Motivo: A hora é 00:00:00 em 99.139 das 99.224 avaliações e 01:00:00 nas outras
  85 devido a artefato de horário de verão, e não um horário real de submissão.
- Valores monetários (preco, frete, valor): convertidos para DECIMAL(10,2).
  Motivo: Tipos de ponto flutuante (FLOAT/DOUBLE) sofrem de imprecisão binária
  ao representar frações decimais; operações financeiras e somas contábeis exigem
  fechamento exato no centavo.
- Contagens e medidas físicas (item_seq, pagamento_seq, parcelas, tamanho_nome,
  tamanho_descricao, qtd_fotos, peso_g, comprimento_cm, altura_cm, largura_cm,
  nota): convertidos para INTEGER.
- Demais colunas mantidas como VARCHAR, em particular cep_prefixo.
  Motivo: 23.995 clientes possuem CEP iniciando com dígito zero ('0'); CEP é um
  código identificador geográfico, nunca somado ou medido, e converter para
  número eliminaria o zero à esquerda corrompendo o identificador.
- Conversões executadas em SQL diretamente pelo motor colunar DuckDB (strptime, CAST),
  disparadas pelo script Python.
  Motivo: O dado já está residente no banco colunar local; carregá-lo para a memória
  RAM via DataFrames apenas para mudar tipos causaria overhead desnecessário de I/O,
  tempo e consumo de memória.

4. CONVERSÃO QUE FALHA
- Utilização estrita de strptime e CAST, que estouram erro fatal na primeira falha.
  Proibição de try_strptime, TRY_CAST ou coerção para nulo (errors='coerce').
- Em caso de falha: identificar e exibir a tabela, a coluna e um exemplo do valor
  inválido, abortando o script imediatamente com sys.exit(1).
  Motivo: Substituir falhas por nulos cria dados corrompidos silenciosos que se
  tornam indistinguíveis de valores legitimamente ausentes na origem.

5. DUPLICATAS
- Chaves primárias de negócio verificadas:
  * pedidos: (pedido_id)
  * itens_pedido: (pedido_id, item_seq)
  * pagamentos: (pedido_id, pagamento_seq)
  * clientes: (cliente_id)
  * vendedores: (vendedor_id)
  * produtos: (produto_id)
  * traducao_categorias: (categoria)
  * avaliacoes: (avaliacao_id, pedido_id) -> avaliacao_id isolado não é chave,
    pois a mesma avaliação pode associar múltiplos pedidos.
- Linhas inteiras idênticas: deduplicação por SELECT DISTINCT mantendo apenas uma
  ocorrência e contabilizando quantas saíram.
- Chave repetida com conteúdo diferente: aborta a execução, exibe a chave e as
  linhas em conflito e encerra com sys.exit(1).
  Motivo: Escolher arbitrariamente uma linha em um conflito de chaves é tomar uma
  decisão de negócio oculta sem consentimento explícito.

6. NULOS E ANOMALIAS
- Nenhuma linha é removida por conter nulos e nenhum nulo é imputado.
  Motivo: Valores nulos carregam significado semântico essencial (ex.: pedido cancelado
  legitimamente não tem data de entrega). Anomalias históricas da Olist (produtos sem
  categoria, pedidos entregues sem data de entrega registrada, etc.) devem ser
  preservadas na camada refined; decidir o tratamento dessas anomalias é atribuição
  dos marts da camada analítica.

7. SAÍDA NA TELA
- Uma linha por tabela com entrada, saída e duplicatas formatadas.
- Linha indentada para colunas com valores nulos e suas respectivas contagens
  (omitida caso a tabela não contenha valores nulos).
- Contagens obtidas diretamente de consultas SQL no banco, com separador de milhar
  por ponto.
- Linha final com o total de registros processados (TOTAL: 550.759).
- stdout reconfigurado para UTF-8 garantindo portabilidade entre sistemas operacionais.

REEXECUÇÃO
- Comandos CREATE OR REPLACE TABLE garantem idempotência: executar o script uma vez
  ou dez vezes produz rigorosamente o mesmo resultado no banco de dados.

ERRO
- Validação prévia da presença das oito tabelas de entrada no schema raw antes
  de iniciar qualquer transformação. Se faltar alguma, lista as faltantes,
  indica o comando 'uv run python -m pipeline.ingestao' e encerra com sys.exit(1).
"""

from __future__ import annotations

import re
import sys

import duckdb

from pipeline.db import conectar, criar_schema

# Definição das 8 tabelas e seus mapeamentos:
# (coluna_origem, expressao_sql_com_alias, coluna_destino)
CONFIG_TABELAS: dict[str, dict] = {
    "pedidos": {
        "chaves": ["pedido_id"],
        "colunas": [
            ("order_id", "order_id AS pedido_id", "pedido_id"),
            ("customer_id", "customer_id AS cliente_id", "cliente_id"),
            ("order_status", "order_status AS status", "status"),
            (
                "order_purchase_timestamp",
                "strptime(order_purchase_timestamp, '%Y-%m-%d %H:%M:%S') AS data_compra",
                "data_compra",
            ),
            (
                "order_approved_at",
                "strptime(order_approved_at, '%Y-%m-%d %H:%M:%S') AS data_aprovacao",
                "data_aprovacao",
            ),
            (
                "order_delivered_carrier_date",
                "strptime(order_delivered_carrier_date, '%Y-%m-%d %H:%M:%S') AS data_envio",
                "data_envio",
            ),
            (
                "order_delivered_customer_date",
                "strptime(order_delivered_customer_date, '%Y-%m-%d %H:%M:%S') AS data_entrega",
                "data_entrega",
            ),
            (
                "order_estimated_delivery_date",
                "CAST(order_estimated_delivery_date AS DATE) AS data_entrega_prevista",
                "data_entrega_prevista",
            ),
        ],
    },
    "itens_pedido": {
        "chaves": ["pedido_id", "item_seq"],
        "colunas": [
            ("order_id", "order_id AS pedido_id", "pedido_id"),
            (
                "order_item_id",
                "CAST(order_item_id AS INTEGER) AS item_seq",
                "item_seq",
            ),
            ("product_id", "product_id AS produto_id", "produto_id"),
            ("seller_id", "seller_id AS vendedor_id", "vendedor_id"),
            (
                "shipping_limit_date",
                "strptime(shipping_limit_date, '%Y-%m-%d %H:%M:%S') AS data_limite_envio",
                "data_limite_envio",
            ),
            ("price", "CAST(price AS DECIMAL(10,2)) AS preco", "preco"),
            (
                "freight_value",
                "CAST(freight_value AS DECIMAL(10,2)) AS frete",
                "frete",
            ),
        ],
    },
    "pagamentos": {
        "chaves": ["pedido_id", "pagamento_seq"],
        "colunas": [
            ("order_id", "order_id AS pedido_id", "pedido_id"),
            (
                "payment_sequential",
                "CAST(payment_sequential AS INTEGER) AS pagamento_seq",
                "pagamento_seq",
            ),
            ("payment_type", "payment_type AS tipo", "tipo"),
            (
                "payment_installments",
                "CAST(payment_installments AS INTEGER) AS parcelas",
                "parcelas",
            ),
            (
                "payment_value",
                "CAST(payment_value AS DECIMAL(10,2)) AS valor",
                "valor",
            ),
        ],
    },
    "clientes": {
        "chaves": ["cliente_id"],
        "colunas": [
            ("customer_id", "customer_id AS cliente_id", "cliente_id"),
            (
                "customer_unique_id",
                "customer_unique_id AS cliente_unico_id",
                "cliente_unico_id",
            ),
            (
                "customer_zip_code_prefix",
                "customer_zip_code_prefix AS cep_prefixo",
                "cep_prefixo",
            ),
            ("customer_city", "customer_city AS cidade", "cidade"),
            ("customer_state", "customer_state AS uf", "uf"),
        ],
    },
    "vendedores": {
        "chaves": ["vendedor_id"],
        "colunas": [
            ("seller_id", "seller_id AS vendedor_id", "vendedor_id"),
            (
                "seller_zip_code_prefix",
                "seller_zip_code_prefix AS cep_prefixo",
                "cep_prefixo",
            ),
            ("seller_city", "seller_city AS cidade", "cidade"),
            ("seller_state", "seller_state AS uf", "uf"),
        ],
    },
    "produtos": {
        "chaves": ["produto_id"],
        "colunas": [
            ("product_id", "product_id AS produto_id", "produto_id"),
            (
                "product_category_name",
                "product_category_name AS categoria",
                "categoria",
            ),
            (
                "product_name_lenght",
                "CAST(product_name_lenght AS INTEGER) AS tamanho_nome",
                "tamanho_nome",
            ),
            (
                "product_description_lenght",
                "CAST(product_description_lenght AS INTEGER) AS tamanho_descricao",
                "tamanho_descricao",
            ),
            (
                "product_photos_qty",
                "CAST(product_photos_qty AS INTEGER) AS qtd_fotos",
                "qtd_fotos",
            ),
            (
                "product_weight_g",
                "CAST(product_weight_g AS INTEGER) AS peso_g",
                "peso_g",
            ),
            (
                "product_length_cm",
                "CAST(product_length_cm AS INTEGER) AS comprimento_cm",
                "comprimento_cm",
            ),
            (
                "product_height_cm",
                "CAST(product_height_cm AS INTEGER) AS altura_cm",
                "altura_cm",
            ),
            (
                "product_width_cm",
                "CAST(product_width_cm AS INTEGER) AS largura_cm",
                "largura_cm",
            ),
        ],
    },
    "traducao_categorias": {
        "chaves": ["categoria"],
        "colunas": [
            (
                "product_category_name",
                "product_category_name AS categoria",
                "categoria",
            ),
            (
                "product_category_name_english",
                "product_category_name_english AS categoria_en",
                "categoria_en",
            ),
        ],
    },
    "avaliacoes": {
        "chaves": ["avaliacao_id", "pedido_id"],
        "colunas": [
            ("review_id", "review_id AS avaliacao_id", "avaliacao_id"),
            ("order_id", "order_id AS pedido_id", "pedido_id"),
            ("review_score", "CAST(review_score AS INTEGER) AS nota", "nota"),
            (
                "review_comment_title",
                "review_comment_title AS titulo",
                "titulo",
            ),
            (
                "review_comment_message",
                "review_comment_message AS comentario",
                "comentario",
            ),
            (
                "review_creation_date",
                "CAST(review_creation_date AS DATE) AS data_criacao",
                "data_criacao",
            ),
            (
                "review_answer_timestamp",
                "strptime(review_answer_timestamp, '%Y-%m-%d %H:%M:%S') AS data_resposta",
                "data_resposta",
            ),
        ],
    },
}


def _formatar_numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _diagnosticar_erro_conversao(
    con, tabela: str, colunas: list[tuple[str, str, str]]
) -> tuple[str, str]:
    """
    Identifica qual coluna falhou na conversão e obtém um exemplo do valor inválido.
    """
    for col_orig, expr, _ in colunas:
        try:
            con.execute(f"SELECT {expr} FROM raw.{tabela}")
        except duckdb.Error as exc:
            msg = str(exc)
            match = re.search(
                r"""(?:Could not parse string ["']|Could not convert string ["'])([^"']+)""",
                msg,
            )
            if match:
                return col_orig, match.group(1)
            return col_orig, msg
    return "desconhecida", "valor desconhecido"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        tabelas_raw_existentes = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
            ).fetchall()
        }

        faltantes = [
            tabela for tabela in CONFIG_TABELAS if tabela not in tabelas_raw_existentes
        ]
        if faltantes:
            print("Tabelas faltando no schema 'raw':")
            for t in faltantes:
                print(f" - {t}")
            print("Execute primeiro: uv run python -m pipeline.ingestao")
            sys.exit(1)

        criar_schema(con, "refined")

        total_linhas_saida = 0

        for tabela, cfg in CONFIG_TABELAS.items():
            chaves = cfg["chaves"]
            colunas = cfg["colunas"]

            linhas_entrada = con.execute(
                f"SELECT COUNT(*) FROM raw.{tabela}"
            ).fetchone()[0]

            projecoes = ",\n    ".join(expr for _, expr, _ in colunas)
            sql_transformacao = f"""
                CREATE OR REPLACE TABLE refined.{tabela} AS
                SELECT DISTINCT
                    {projecoes}
                FROM raw.{tabela}
            """

            try:
                con.execute(sql_transformacao)
            except duckdb.Error:
                coluna_erro, valor_erro = _diagnosticar_erro_conversao(
                    con, tabela, colunas
                )
                print(
                    f"Erro de conversão na tabela '{tabela}', coluna '{coluna_erro}': "
                    f"valor inválido '{valor_erro}'."
                )
                sys.exit(1)

            linhas_saida = con.execute(
                f"SELECT COUNT(*) FROM refined.{tabela}"
            ).fetchone()[0]
            duplicatas = linhas_entrada - linhas_saida

            # Como refined.{tabela} foi gerada com DISTINCT, qualquer repetição de chave
            # implica obrigatoriamente divergência de conteúdo em outros atributos.
            chaves_str = ", ".join(chaves)
            conflitos = con.execute(f"""
                SELECT {chaves_str}, COUNT(*) AS total
                FROM refined.{tabela}
                GROUP BY {chaves_str}
                HAVING COUNT(*) > 1
                LIMIT 5
            """).fetchall()

            if conflitos:
                print(
                    f"Erro: chave duplicada com conteúdo diferente na tabela 'refined.{tabela}'."
                )
                for grupo in conflitos:
                    chave_dict = dict(zip(chaves, grupo[: len(chaves)]))
                    where_cond = " AND ".join(
                        f"{col} = '{chave_dict[col]}'"
                        if chave_dict[col] is not None
                        else f"{col} IS NULL"
                        for col in chaves
                    )
                    linhas_conflito = con.execute(
                        f"SELECT * FROM refined.{tabela} WHERE {where_cond}"
                    ).fetchall()
                    print(f"Chave: {chave_dict}")
                    print("Linhas conflitantes:")
                    for linha in linhas_conflito:
                        print(f"  {linha}")
                sys.exit(1)

            # Exibição do status da tabela
            nome_qualificado = f"refined.{tabela}"
            print(
                f"{nome_qualificado:<27} {_formatar_numero(linhas_entrada)} -> "
                f"{_formatar_numero(linhas_saida)} linhas  ({_formatar_numero(duplicatas)} duplicatas)"
            )

            # Contagem e exibição de nulos existentes
            colunas_destino = [col_dest for _, _, col_dest in colunas]
            expressoes_nulos = [f"COUNT(*) - COUNT({c})" for c in colunas_destino]
            resultado_nulos = con.execute(
                f"SELECT {', '.join(expressoes_nulos)} FROM refined.{tabela}"
            ).fetchone()

            nulos_mantidos = [
                f"{col} {_formatar_numero(qtd)}"
                for col, qtd in zip(colunas_destino, resultado_nulos)
                if qtd > 0
            ]
            if nulos_mantidos:
                print(f"    nulos mantidos: {', '.join(nulos_mantidos)}")

            total_linhas_saida += linhas_saida

        print(f"TOTAL: {_formatar_numero(total_linhas_saida)}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
