-- Several retail price sources share price_series; each import replaces only its own rows.
ALTER TABLE price_series ADD COLUMN source TEXT NOT NULL DEFAULT 'KAMIS';
