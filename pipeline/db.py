"""
Módulo de conexão e utilitários para o DuckDB.

Expõe caminhos, funções de conexão e gravação necessárias para as etapas
de ingestão e exploração do pipeline.
"""

from pathlib import Path
import duckdb


PASTA_RAW = Path(__file__).parent.parent / "raw"


def conectar():
    """
    Abre a conexão com olist.duckdb na raiz do projeto.
    
    Cria o arquivo se não existir.
    
    Returns:
        duckdb.DuckDBPyConnection: conexão com o banco de dados.
    """
    db_path = Path(__file__).parent.parent / "olist.duckdb"
    return duckdb.connect(str(db_path))


def criar_schema(con, nome):
    """
    Cria um schema no banco, se não existir.
    
    Args:
        con: conexão DuckDB.
        nome (str): nome do schema.
    """
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {nome}")


def gravar(con, df, schema, tabela):
    """
    Grava um DataFrame no banco como tabela no schema especificado.
    
    Usa CREATE OR REPLACE TABLE para permitir reexecução idempotente.
    
    Args:
        con: conexão DuckDB.
        df: DataFrame do pandas.
        schema (str): nome do schema.
        tabela (str): nome da tabela.
    
    Returns:
        int: número de linhas gravadas (lido de um SELECT COUNT(*)).
    """
    tabela_qualificada = f"{schema}.{tabela}"
    con.execute(f"CREATE OR REPLACE TABLE {tabela_qualificada} AS SELECT * FROM df")
    resultado = con.execute(f"SELECT COUNT(*) FROM {tabela_qualificada}").fetchone()
    return resultado[0]
