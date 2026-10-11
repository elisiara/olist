"""
Docstring de especificação para ui.py

Este arquivo não é parte da ingestão e não importa o módulo de ingestão.
Sua função é abrir o navegador para explorar o banco DuckDB em modo web
com a extensão ui do DuckDB, mantendo o processo vivo enquanto a conexão
permanece aberta.

A regra aqui é explícita: o script deve abrir o banco da raiz do projeto
somente se ele existir. Se não existir, ele deve informar que a ingestão
precisa rodar antes e encerrar com sys.exit(1). Isso evita a falsa
sensação de que a ingestão funcionou ao abrir um banco vazio, o que
seria um erro grave.

Também é obrigatório instalar e carregar a extensão ui e chamar
CALL start_ui(), o que sobe o servidor em http://localhost:4213 e abre
o navegador. O servidor precisa continuar ativo enquanto a conexão estiver
viva, e o script deve permanecer em execução até CTRL+C. Ao receber Ctrl+C,
o script fecha a conexão e sai limpo, sem traceback, porque o arquivo
.duckdb aceita apenas um processo de gravação por vez; saber desligar
de forma correta faz parte da ferramenta.

Como no restante do projeto, a saída em tela usa UTF-8 para funcionar no
Prompt de Comando do Windows e manter os acentos corretos.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "olist.duckdb"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    if not DB_PATH.exists():
        print(f"Banco não encontrado em: {DB_PATH}")
        print("É preciso rodar a ingestão antes.")
        raise SystemExit(1)

    con = duckdb.connect(str(DB_PATH))

    try:
        con.execute("INSTALL ui;")
        con.execute("LOAD ui;")
        con.execute("CALL start_ui();")

        print("DuckDB UI disponível em: http://localhost:4213")
        print("Ctrl+C para encerrar")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nEncerrando DuckDB UI...")
    finally:
        con.close()


if __name__ == "__main__":
    main()
