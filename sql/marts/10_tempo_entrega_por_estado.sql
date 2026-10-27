-- Tempo de entrega por estado
-- Grão: UF(Estado do cliente).
-- Quantos dias, da compra até a entrega, por UF do cliente. Mesmo denominador do mart 03.
-- O passo novo são duas funções: date_diff('day', inicio, fim), que conta dias de calendário, e median().
--
-- Colunas: uf, entregues, dias_medio (uma casa) e dias_mediana.
--
-- Para conferir: 27 linhas, a soma de entregues dá 96.470 — a mesma do mart 03 —,
-- SP é o mais rápido com 8,7 dias e RR o mais lento com 29,3.
-- Se partiu de data_envio, mediu outra coisa: o tempo da transportadora, não o da loja.

-- Grão: UF(Estado do cliente).
SELECT
    c.uf,
    count(*)                                                       AS entregues,
    round(avg(date_diff('day', p.data_compra, p.data_entrega)), 1) AS dias_medio,
    median(date_diff('day', p.data_compra, p.data_entrega))        AS dias_mediana
FROM refined.pedidos  AS p
JOIN refined.clientes AS c ON c.cliente_id = p.cliente_id
WHERE p.status = 'delivered'
  AND p.data_entrega IS NOT NULL
GROUP BY c.uf
ORDER BY dias_medio ASC;

