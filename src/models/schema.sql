-- Warehouse schema (DuckDB). Run once via src/etl/load_warehouse.py:init_schema().

CREATE TABLE IF NOT EXISTS eia_hourly_demand (
    period          TIMESTAMP,
    respondent      VARCHAR,       -- balancing authority code, e.g. CISO
    respondent_name VARCHAR,
    value           DOUBLE,        -- demand in MWh
    value_units     VARCHAR,
    pulled_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eia_retail_price (
    period          DATE,
    stateid         VARCHAR,
    sectorid        VARCHAR,
    price           DOUBLE,        -- cents per kWh
    pulled_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS epa_frs_facilities (
    registry_id     VARCHAR,
    primary_name    VARCHAR,
    location_address VARCHAR,
    city_name       VARCHAR,
    county_name     VARCHAR,
    state_code      VARCHAR,
    latitude83      DOUBLE,
    longitude83     DOUBLE,
    pulled_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sustainability_metrics (
    company         VARCHAR,
    facility_region VARCHAR,
    report_year     INTEGER,
    metric_name     VARCHAR,
    metric_value    DOUBLE,
    unit            VARCHAR,
    source_url      VARCHAR,
    notes           VARCHAR
);
