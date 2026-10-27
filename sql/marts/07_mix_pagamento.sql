-- Resumo das formas de pagamento nos pedidos válidos
-- Grão: uma forma de pagamento (tipo).
--
-- O passo novo: a tabela pagamentos tem PK composta (pedido_id, pagamento_seq).
-- Um pedido pago com múltiplos meios (ex.: 2 vouchers e 1 cartão de crédito) possui 3 linhas.
-- Colunas: tipo, pagamentos, pedidos, valor e pct_valor (% do valor total, uma casa).
--
-- Diferença para a receita do Mart 01:
-- A soma do valor dos pagamentos (R$ 15.739.137,01) é maior que a receita do Mart 01 (R$ 13.494.400,74)
-- porque o Mart 01 calcula apenas a receita das mercadorias vendidas (sum(itens_pedido.preco)).
-- Os pagamentos, por sua vez, representam o desembolso total do cliente, que inclui o frete
-- (R$ 2.241.126,29 em itens_pedido.frete), além de eventuais ajustes e pedidos sem itens.
--
-- Soma de pedidos maior que 98.206:
-- Existem 98.206 pedidos válidos distintos com registro de pagamento. A soma da coluna pedidos
-- totaliza 100.417 porque 2.211 pedidos foram quitados utilizando combinações de formas de pagamento
-- (mix de pagamento, ex.: cartão + voucher). Como o COUNT(DISTINCT pedido_id) é feito por tipo,
-- um mesmo pedido é computado em mais de uma linha da agregação.
--
-- Para conferir:
-- 4 linhas, credit_card com 78,5% do valor e soma total de valor = R$ 15.739.137,01.

WITH pagamentos_por_tipo AS (
    SELECT
        p.tipo,
        count(*)                    AS pagamentos,
        count(DISTINCT p.pedido_id) AS pedidos,
        sum(p.valor)                AS valor
    FROM refined.pagamentos AS p
    JOIN refined.pedidos    AS o ON o.pedido_id = p.pedido_id
    WHERE o.status NOT IN ('canceled', 'unavailable')
    GROUP BY p.tipo
)
--, totais_pagamentos AS (
SELECT
    tipo,
    pagamentos,
    pedidos,
    valor,
    round(100.0 * valor / sum(valor) OVER (), 1) AS pct_valor
FROM pagamentos_por_tipo
ORDER BY valor DESC
--) SELECT ROUND(SUM(valor), 2) FROM totais_pagamentos; -- conferindo se a soma de valor dá R$ 15.739.137,01.
