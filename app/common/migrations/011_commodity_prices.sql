-- International raw material futures (aT 식품산업통계정보 FIS 「국제 원료가격」), e.g. 커피(아라비카) weekly averages.
CREATE TABLE commodity_prices (
    commodity TEXT NOT NULL,         -- 커피(아라비카)
    week_start TEXT NOT NULL,        -- YYYY-MM-DD
    cents_per_lb REAL NOT NULL,      -- 평균가 (US￠/lb, ICE)
    usd_per_ton REAL,                -- 환산가 ($/ton)
    PRIMARY KEY (commodity, week_start)
);
