-- Vista de compatibilidad: convierte columnas AL30/GD30 en filas por símbolo.
CREATE VIEW IF NOT EXISTS ticks_rows AS
SELECT
  'AL30' AS symbol,
  ts,
  al30  AS last,
  NULL  AS bid,
  NULL  AS ask,
  NULL  AS bid_size,
  NULL  AS ask_size,
  turn_al30 AS turnover,
  NULL  AS "open",
  NULL  AS "close",
  source
FROM ticks
UNION ALL
SELECT
  'GD30' AS symbol,
  ts,
  gd30  AS last,
  NULL  AS bid,
  NULL  AS ask,
  NULL  AS bid_size,
  NULL  AS ask_size,
  turn_gd30 AS turnover,
  NULL  AS "open",
  NULL  AS "close",
  source
FROM ticks;
