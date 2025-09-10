CREATE TABLE ticks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            al30 REAL NOT NULL,
            gd30 REAL NOT NULL,
            ratio REAL,
            source TEXT
        , vol_al30 REAL, vol_gd30 REAL, turn_al30 REAL, turn_gd30 REAL);
CREATE TABLE sqlite_sequence(name,seq);
CREATE INDEX idx_ticks_ts ON ticks(ts);
CREATE UNIQUE INDEX ux_ticks_ts ON ticks(ts);
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
