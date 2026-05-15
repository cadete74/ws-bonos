CREATE TABLE ticks (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT    NOT NULL,
  symbol   TEXT    NOT NULL,
  last     REAL,
  vol      REAL,
  turnover REAL,
  source   TEXT,
  UNIQUE(ts, symbol)
);
CREATE UNIQUE INDEX ux_ticks_ts_symbol ON ticks(ts, symbol);
CREATE INDEX idx_ticks_symbol_ts_desc ON ticks(symbol, ts DESC);
CREATE TABLE orderbooks (
  symbol   TEXT    NOT NULL,
  ts       TEXT    NOT NULL,         -- mismo clock del proveedor
  side     TEXT    NOT NULL CHECK (side IN ('BID','ASK')),
  level    INTEGER NOT NULL,         -- 1..N
  price    REAL,
  size     REAL,
  PRIMARY KEY (symbol, ts, side, level)
);
CREATE INDEX idx_orderbooks_symbol_ts_desc
  ON orderbooks(symbol, ts DESC);
CREATE INDEX idx_orderbooks_symbol_ts
  ON orderbooks(symbol, ts);
