-- Initialize database with TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create price history hypertable for time-series data
CREATE TABLE IF NOT EXISTS price_history (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    asset_type VARCHAR(20) NOT NULL,
    price DECIMAL(18, 8) NOT NULL,
    volume DECIMAL(24, 8),
    market_cap DECIMAL(24, 2),
    currency VARCHAR(10) DEFAULT 'EUR'
);

-- Convert to hypertable for efficient time-series queries
SELECT create_hypertable('price_history', 'time', if_not_exists => TRUE);

-- Create index for efficient symbol lookups
CREATE INDEX IF NOT EXISTS idx_price_history_symbol ON price_history (symbol, time DESC);

-- Create continuous aggregate for daily prices
CREATE MATERIALIZED VIEW IF NOT EXISTS price_history_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    symbol,
    asset_type,
    first(price, time) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price, time) AS close,
    sum(volume) AS volume
FROM price_history
GROUP BY bucket, symbol, asset_type;

-- Set retention policy (keep 2 years of data)
SELECT add_retention_policy('price_history', INTERVAL '2 years', if_not_exists => TRUE);

-- Create admin user (password: changeme - CHANGE IN PRODUCTION!)
-- This is created by the application on first run, but kept here as reference
-- INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
-- VALUES (
--     gen_random_uuid(),
--     'admin@investai.local',
--     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G1z3nZlrZ6n6zy', -- 'changeme'
--     'admin',
--     true,
--     NOW(),
--     NOW()
-- );
