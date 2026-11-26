-- External reference data: per-business annual figures by region and industry
-- (중소벤처기업부 소상공인실태조사 via KOSIS, 기업체당 백만원/년). NULL = not published at that level.
CREATE TABLE industry_benchmarks (
    year TEXT NOT NULL,
    region TEXT NOT NULL,            -- 전국 / 서울특별시 ...
    sector TEXT NOT NULL,            -- 대분류, e.g. 숙박 및 음식점업
    industry TEXT NOT NULL,          -- 중분류 or 소계
    firms INTEGER,
    revenue INTEGER,                 -- 매출액
    operating_cost INTEGER,          -- 영업비용 = 매출원가 + 급여총액 + 임차료 + 기타비용
    cost_of_sales INTEGER,           -- 매출원가
    payroll INTEGER,                 -- 급여총액
    rent INTEGER,                    -- 임차료
    other_cost INTEGER,              -- 기타비용
    profit INTEGER,                  -- 영업이익
    PRIMARY KEY (year, region, sector, industry)
);
