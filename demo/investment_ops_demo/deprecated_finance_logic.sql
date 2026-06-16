-- Deprecated finance logic - DO NOT USE for new reports
-- Still referenced by reporting_job.sql

CREATE OR REPLACE FUNCTION legacy_monthly_irr(cashflows numeric[])
RETURNS numeric AS $$
    -- Deprecated: uses gross cashflows without fee adjustment
    SELECT iterative_irr(cashflows);
$$ LANGUAGE sql;

-- Old fund performance view using legacy tables
CREATE VIEW legacy_fund_irr AS
SELECT f.fund_id,
       legacy_monthly_irr(f.gross_cashflows) AS legacy_monthly_irr
FROM deprecated_fund_cashflows f;

-- References calc_monthly_irr from legacy_irr_calculator.py
-- reporting_job.sql depends on this view
