-- A nota de quem recebeu atrasado
-- Grão: situação da entrega (ou status de prazo: no_prazo ou atrasado).
-- sql/marts/08_nota_por_prazo.sql. A pergunta que junta logística e satisfação:
-- o atraso derruba a nota? Uma linha para quem recebeu no prazo e uma para quem recebeu atrasado,
-- com o mesmo denominador do mart 03. O passo novo é combinar dois marts: a nota por pedido
-- do mart 04 com o CASE do mart 03.

-- Colunas: situacao ('no_prazo' ou 'atrasado'), pedidos_avaliados, nota_media (duas casas)
-- e pct_nota_baixa (% de pedidos com nota até 2, uma casa).

-- Para conferir: 2 linhas, a soma de pedidos_avaliados dá 95.824, e a nota dos atrasados fica
-- abaixo de 2,5. Se a soma deu 96.353, você contou avaliações, não pedidos.
-- Se a nota dos atrasados deu 2,57, releia a armadilha do mart 03.

-- Grão: situação da entrega (ou status de prazo: no_prazo ou atrasado).
WITH nota_pedido AS (
    -- Grão interno : pedido_id
    SELECT
        pedido_id,
        avg(nota) AS nota
    FROM refined.avaliacoes
    GROUP BY pedido_id
)
--, situacao AS (
SELECT
    CASE
        WHEN p.data_entrega::DATE <= p.data_entrega_prevista THEN 'no_prazo'
        ELSE 'atrasado'
    END AS situacao,
    count(*)                                                                     AS pedidos_avaliados,
    round(avg(np.nota), 2)                                                       AS nota_media,
    round(100.0 * sum(CASE WHEN np.nota <= 2 THEN 1 ELSE 0 END) / count(*), 1) AS pct_nota_baixa
FROM refined.pedidos AS p
JOIN nota_pedido     AS np ON np.pedido_id = p.pedido_id
WHERE p.status = 'delivered'
  AND p.data_entrega IS NOT NULL
GROUP BY situacao
ORDER BY situacao DESC
--) SELECT SUM(pedidos_avaliados) FROM situacao; -- conferindo se a soma de pedidos_avaliados dá 95.824,