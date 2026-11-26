-- External reference data for menu pricing (03) and location (01).
-- 외식비: monthly average price of 9 representative menus by 시도 (행정안전부 via 한국소비자원 참가격).
CREATE TABLE dineout_prices (
    month TEXT NOT NULL,             -- YYYY-MM
    region TEXT NOT NULL,            -- 서울, 부산 ...
    menu TEXT NOT NULL,              -- 냉면, 김치찌개 백반 ...
    price INTEGER NOT NULL,          -- 원
    PRIMARY KEY (month, region, menu)
);
-- 소상공인실태조사: start-up cost brackets (% of businesses) and lease terms per business, by region and industry.
CREATE TABLE startup_benchmarks (
    year TEXT NOT NULL,
    region TEXT NOT NULL,
    sector TEXT NOT NULL,
    industry TEXT NOT NULL,
    cost_under_50m REAL, cost_50m_100m REAL, cost_over_100m REAL,      -- 창업비용 구간별 기업체 비율 (%)
    own_under_50m REAL, own_50m_100m REAL, own_over_100m REAL,         -- 본인부담금액 구간별 비율 (%)
    deposit INTEGER,                 -- 보증금 있는 월세의 보증금 (만원)
    rent INTEGER,                    -- 보증금 있는 월세의 월세 (만원)
    rent_no_deposit INTEGER,         -- 보증금 없는 월세 (만원)
    PRIMARY KEY (year, region, sector, industry)
);
