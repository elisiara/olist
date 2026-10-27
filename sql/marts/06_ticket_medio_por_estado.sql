-- Ticket médio por estado
-- Grão: UF(estado)
-- Clientes por estado e sua receita média(grão 2×)
-- sql/marts/06_ticket_medio_por_estado.sql.
-- Ticket médio tem definição fechada desde os indicadores da turma: a receita de cada pedido válido,
-- somada primeiro, e a média por pedido depois. O valor está no item, a UF no cliente,
-- e os dois só se encontram passando por pedidos.
-- O passo novo: o grão muda duas vezes, de item para pedido e de pedido para UF.
-- Colunas: uf, pedidos e ticket_medio (em reais, duas casas).
-- Para conferir: 27 linhas, a soma de pedidos dá 98.199, e SP tem o menor ticket do país.
-- Se o seu ticket de SP ficou perto de R$ 110, releia o desenho da seção 02: você tirou a média de outra coisa.
--WITH pedido_agrupado AS(
-- Grão: UF(estado)
SELECT
  c.uf,
  ROUND(AVG(total_gasto), 2) AS ticket_medio,
  COUNT(DISTINCT p.pedido_id) AS pedidos
FROM refined.clientes c
JOIN refined.pedidos p ON c.cliente_id = p.cliente_id
JOIN (
  -- Grão interno é o item do pedido
  SELECT
    ip.pedido_id,
    SUM(ip.preco) AS total_gasto
  FROM refined.itens_pedido ip
  GROUP BY ip.pedido_id
) pedido_valor ON p.pedido_id = pedido_valor.pedido_id
WHERE p.status NOT IN ('canceled', 'unavailable')
GROUP BY c.uf
ORDER BY c.uf;
--) SELECT SUM(pedidos) AS numero_de__pedidos FROM pedido_agrupado; -- Conferindo se soma pedidos é igual a 98.199