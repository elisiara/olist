"""
Docstring de especificação para pipeline/marts.py

Este módulo implementa a publicação dos data marts analíticos a partir do
schema refined, gerando as tabelas finais no schema marts do DuckDB.
A especificação abaixo documenta o comportamento esperado e as justificativas
técnicas e de negócio para cada regra adotada.

1. ESCOPO
- Lê exclusivamente de refined e escreve no schema marts. Nunca escreve em raw nem em refined.
  Motivo: Garantir a segregação estrita de camadas e a imutabilidade das camadas anteriores.
- O schema marts é apagado e recriado a cada execução (DROP SCHEMA IF EXISTS marts CASCADE).
  Motivo: Um mart cujo arquivo SQL correspondente foi apagado não pode continuar existindo no
  banco de dados, evitando dashboards zumbis ou tabelas obsoletas órfãs.

2. UM ARQUIVO, UMA TABELA
- Lê todos os sql/marts/*.sql em ordem alfabética.
- Nome da tabela = nome do arquivo sem a extensão e sem o prefixo numérico:
    sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
- Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
- Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais.
  O Python não altera, não monta e não completa a SQL.
  Motivo: A regra de negócio mora inteira no arquivo .sql, mantendo a responsabilidade analítica
  desacoplada da orquestração em Python.

3. SAÍDA NA TELA
- Uma linha por mart, com a contagem de registros vinda do banco e milhar com ponto:
    ✓ marts.vendas_mensais        24 linhas
- Linha final com o número de marts e o total de linhas.
- stdout reconfigurado para UTF-8 garantindo portabilidade entre sistemas operacionais.

4. ERRO
- Validação prévia de refined: Antes de tudo, se faltar qualquer uma das oito tabelas em refined
  (pedidos, itens_pedido, pagamentos, clientes, vendedores, produtos, traducao_categorias, avaliacoes),
  lista quais faltam, orienta a executar "uv run python -m pipeline.transformacao" e encerra com sys.exit(1).
- Validação de pasta de marts: Se sql/marts/ não tiver nenhum arquivo, avisa e encerra com sys.exit(1).
- Validação de arquivos: Antes de executar qualquer SQL, arquivo sem prefixo NN_ ou dois arquivos
  que gerem o mesmo nome de tabela são listados na tela e o script encerra com sys.exit(1).
- Falha na execução SQL: Se um .sql falhar, exibe o nome do arquivo e a mensagem de erro do DuckDB,
  interrompe imediatamente sem executar os arquivos seguintes e encerra com sys.exit(1).
- Mart vazio: Se um mart voltar com zero linhas, mostra o nome e encerra com sys.exit(1).
  Motivo: Mart vazio é quase sempre indicativo de um JOIN que não casou ou filtro incorreto;
  um dashboard vazio transmite a falsa impressão de um negócio sem movimentação.
- Atomicidade / Transação única: Tudo roda numa única transação de banco. Se qualquer passo falhar
  (inclusive um mart vazio ou erro de sintaxe SQL), o schema marts sofre rollback e volta a ser
  o da última execução que deu certo.
  Motivo: Um schema publicado pela metade quebra relatórios e dashboards em produção sem aviso.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

from pipeline.db import conectar, criar_schema

PASTA_PROJETO = Path(__file__).parent.parent
PASTA_SQL_MARTS = PASTA_PROJETO / "sql" / "marts"

TABELAS_REFINED = (
    "pedidos",
    "itens_pedido",
    "pagamentos",
    "clientes",
    "vendedores",
    "produtos",
    "traducao_categorias",
    "avaliacoes",
)


def _formatar_numero(valor: int) -> str:
    """Formata número inteiro utilizando ponto como separador de milhar."""
    return f"{valor:_}".replace("_", ".")


def _limpar_sql(conteudo: str) -> str:
    """
    Remove espaços e no máximo um ponto e vírgula do final da SQL.

    Preserva intacto todo o restante do conteúdo (comentários iniciais, WITH, etc.).
    """
    sql = conteudo.rstrip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql


def _rollback_se_ativo(con: duckdb.DuckDBPyConnection) -> None:
    """Executa rollback na conexão apenas se houver transação ativa."""
    try:
        con.rollback()
    except duckdb.Error:
        pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        # 1. Validação prévia de integridade da camada refined
        tabelas_refined_existentes = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'refined'"
            ).fetchall()
        }
        faltantes = [t for t in TABELAS_REFINED if t not in tabelas_refined_existentes]
        if faltantes:
            print("Tabelas faltando no schema 'refined':")
            for t in faltantes:
                print(f" - {t}")
            print("Execute primeiro: uv run python -m pipeline.transformacao")
            sys.exit(1)

        # 2. Verificação de existência da pasta sql/marts e arquivos
        if not PASTA_SQL_MARTS.exists():
            print("Aviso: A pasta sql/marts/ não existe.")
            sys.exit(1)

        arquivos_diretorio = [
            f for f in sorted(PASTA_SQL_MARTS.iterdir()) if not f.name.startswith(".")
        ]
        if not arquivos_diretorio:
            print("Aviso: Nenhum arquivo encontrado em sql/marts/.")
            sys.exit(1)

        # 3. Validação de formato NN_ e colisão de nomes antes de executar qualquer SQL
        arquivos_sem_prefixo: list[str] = []
        tabelas_map: dict[str, list[str]] = defaultdict(list)
        marts_para_executar: list[tuple[Path, str]] = []

        for f in arquivos_diretorio:
            if not f.is_file():
                continue
            # O prefixo NN_ exige exatamente dois dígitos numéricos seguidos de underscore
            m = re.match(r"^(\d{2})_(.+)\.sql$", f.name)
            if not m:
                arquivos_sem_prefixo.append(f.name)
            else:
                nome_tabela = m.group(2)
                tabelas_map[nome_tabela].append(f.name)
                marts_para_executar.append((f, nome_tabela))

        houve_erro_validacao = False
        if arquivos_sem_prefixo:
            houve_erro_validacao = True
            print("Erro: Arquivo(s) sem o prefixo numérico obrigatório 'NN_':")
            for nome in arquivos_sem_prefixo:
                print(f" - {nome}")

        duplicados = {tab: arqs for tab, arqs in tabelas_map.items() if len(arqs) > 1}
        if duplicados:
            houve_erro_validacao = True
            print("Erro: Arquivos que resultam no mesmo nome de tabela:")
            for tab, arqs in duplicados.items():
                print(f" - Tabela 'marts.{tab}': {', '.join(arqs)}")

        if houve_erro_validacao:
            sys.exit(1)

        if not marts_para_executar:
            print("Aviso: Nenhum arquivo SQL válido encontrado em sql/marts/.")
            sys.exit(1)

        # 4. Execução atômica em transação única
        con.begin()
        sucesso_transacao = False
        try:
            con.execute("DROP SCHEMA IF EXISTS marts CASCADE")
            criar_schema(con, "marts")

            resultados: list[tuple[str, int]] = []

            for arquivo, nome_tabela in marts_para_executar:
                conteudo = arquivo.read_text(encoding="utf-8")
                sql_limpa = _limpar_sql(conteudo)

                try:
                    con.execute(f"CREATE TABLE marts.{nome_tabela} AS {sql_limpa}")
                except duckdb.Error as e:
                    _rollback_se_ativo(con)
                    print(f"Erro ao executar '{arquivo.name}':\n{e}")
                    sys.exit(1)

                qtd_linhas = con.execute(
                    f"SELECT COUNT(*) FROM marts.{nome_tabela}"
                ).fetchone()[0]
                if qtd_linhas == 0:
                    _rollback_se_ativo(con)
                    print(
                        f"Erro: Mart 'marts.{nome_tabela}' ({arquivo.name}) retornou 0 linhas."
                    )
                    sys.exit(1)

                resultados.append((nome_tabela, qtd_linhas))

            con.commit()
            sucesso_transacao = True
        finally:
            # Garante rollback caso o fluxo seja abortado inesperadamente antes do commit
            if not sucesso_transacao:
                _rollback_se_ativo(con)

        # 5. Saída na tela (exibida após o commit para garantir que reflete o estado persistido)
        total_linhas = 0
        for nome_tabela, qtd in resultados:
            total_linhas += qtd
            nome_qualificado = f"marts.{nome_tabela}"
            linhas_formatadas = _formatar_numero(qtd)
            sufixo_linhas = "linha" if qtd == 1 else "linhas"
            print(f"✓ {nome_qualificado:<27} {linhas_formatadas} {sufixo_linhas}")

        total_marts = len(resultados)
        sufixo_marts = "mart" if total_marts == 1 else "marts"
        sufixo_total_linhas = "linha" if total_linhas == 1 else "linhas"
        print(
            f"TOTAL: {total_marts} {sufixo_marts}, {_formatar_numero(total_linhas)} {sufixo_total_linhas}"
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
