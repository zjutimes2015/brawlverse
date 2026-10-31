CREATE TABLE IF NOT EXISTS bouts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  fighter_a TEXT NOT NULL,
  fighter_b TEXT NOT NULL,
  round_no INTEGER NOT NULL DEFAULT 1,
  voting_open INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bout_id TEXT NOT NULL,
  round_no INTEGER NOT NULL,
  choice TEXT NOT NULL,
  device_hash TEXT NOT NULL,
  ip TEXT NOT NULL,
  ip_ua TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE (bout_id, round_no, device_hash)
);
CREATE TABLE IF NOT EXISTS rate_hits (
  ip TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_ip_ts ON rate_hits (ip, ts);

INSERT OR IGNORE INTO bouts (id, title, fighter_a, fighter_b, round_no, voting_open, created_at) VALUES
  ('qf1', 'QF1 — Sample Bout', 'IRON JAW', 'VIPER', 2, 1, unixepoch()),
  ('qf2', 'QF2', 'SLEDGE', 'MONSOON', 1, 0, unixepoch()),
  ('qf3', 'QF3', 'VOLT', 'THE PROFESSOR', 1, 0, unixepoch()),
  ('qf4', 'QF4', 'GOLIATH-7', 'LA REINA', 1, 0, unixepoch());
