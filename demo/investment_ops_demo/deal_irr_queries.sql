-- Fund performance IRR queries
-- Owner: Investment Operations

WITH fund_cashflows AS (
    SELECT fund_id, cf_date, net_amount, cf_type
    FROM fund_cashflows_v2
    WHERE fund_id = :fund_id
),
monthly_agg AS (
    SELECT fund_id,
           DATE_TRUNC('month', cf_date) AS period,
           SUM(net_amount) AS monthly_cashflows
    FROM fund_cashflows
    GROUP BY fund_id, DATE_TRUNC('month', cf_date)
)
SELECT fund_id,
       iterative_irr(monthly_cashflows) AS fund_level_net_irr
FROM monthly_agg;

-- Gross deal IRR (realized only)
SELECT deal_id,
       SUM(distributions) / NULLIF(SUM(invested_capital), 0) AS gross_deal_moic,
       iterative_irr(realized_cashflows) AS gross_deal_irr
FROM deal_cashflows
WHERE exit_date IS NOT NULL
GROUP BY deal_id;

-- Realized IRR
SELECT fund_id,
       compute_xirr(realized_amounts, realized_dates) AS realized_irr
FROM fund_realized_cashflows;

-- TVPI calculation
SELECT fund_id,
       (total_distributions + current_nav) / NULLIF(paid_in_capital, 0) AS tvpi
FROM fund_summary;

-- Legacy reference to deprecated calculator
-- See legacy_irr_calculator.py calc_monthly_irr for reporting_job compatibility
