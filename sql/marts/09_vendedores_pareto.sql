-- Concentração de vendedores (Pareto)
-- Grão: um vendedor com venda válida.
-- Que fração dos vendedores faz 80% da receita? Uma linha por vendedor com venda válida,
-- do maior para o menor, com a receita acumulada até ele. O passo novo é a janela com ordem:
-- sum(...) OVER (ORDER BY ...) soma da primeira linha até a atual.
--
-- Colunas: vendedor_id, uf (do vendedor), receita, posicao e pct_acumulado (% da receita total até esta linha, duas casas).
--
-- Para conferir: 3.053 linhas, a última com 100,00, e a soma de receita igual à do mart 01.
-- O primeiro vendedor a passar de 80% está na posição 540. Há vendedores com a receita idêntica:
-- sem um desempate no ORDER BY da janela, eles ganham o mesmo acumulado, e rodar duas vezes pode não dar a mesma ordem.
WITH receita_por_vendedor AS (
    SELECT
        v.vendedor_id,
        v.uf,
        sum(i.preco) AS receita
    FROM refined.itens_pedido AS i
    JOIN refined.pedidos      AS p ON p.pedido_id = i.pedido_id
    JOIN refined.vendedores   AS v ON v.vendedor_id = i.vendedor_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY v.vendedor_id, v.uf
)
--, concetracao_vendedores AS (
SELECT
    vendedor_id,
    uf,
    receita,
    row_number() OVER (ORDER BY receita DESC, vendedor_id) AS posicao,
    round(100.0 * sum(receita) OVER (ORDER BY receita DESC, vendedor_id) / sum(receita) OVER (), 2) AS pct_acumulado
FROM receita_por_vendedor
ORDER BY posicao
--) SELECT SUM(receita) FROM concetracao_vendedores -- Testa se a soma de receita é igual à soma do mart 01= R$ 13.494.400,74
