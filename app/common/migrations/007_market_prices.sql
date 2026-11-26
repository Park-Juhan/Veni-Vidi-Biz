-- External reference data: monthly retail prices (KAMIS 소매가격, 부류별·월간) and the link from a saved material to one price item.
CREATE TABLE price_series (
    region TEXT NOT NULL,            -- 전국 / 서울
    month TEXT NOT NULL,             -- YYYY-MM
    category TEXT NOT NULL,          -- '' (농수산물) or 가공식품
    item TEXT NOT NULL,              -- 품목
    kind TEXT NOT NULL,              -- 품종
    unit TEXT NOT NULL,              -- 조사 단위, e.g. 1kg, 10개, 1포기
    rank TEXT NOT NULL,              -- 등급
    price INTEGER NOT NULL,          -- 월평균 가격 (원)
    PRIMARY KEY (region, month, item, kind, unit, rank)
);
CREATE INDEX price_series_by_item ON price_series (item, kind, unit, rank, month);
-- NULL: match automatically by name; '': no comparison; otherwise 품목|품종|단위|등급.
ALTER TABLE materials ADD COLUMN market_item TEXT;
