-- KPI queries for the overview dashboard.
-- Each block returns one scalar value; name them via the alias.

-- Total unique companies
SELECT COUNT(DISTINCT company_name) AS total_companies
FROM fact_offers;

-- Total offer rows
SELECT COUNT(*) AS total_offers
FROM fact_offers;

-- Average CTC (known/range only, in LPA)
SELECT ROUND(AVG(ctc_lpa_normalized), 2) AS avg_ctc_lpa
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE');

-- High-package offer count (>= 10 LPA, known/range only)
SELECT COUNT(*) AS high_package_count
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
  AND ctc_lpa_normalized >= 10.0;

-- Unknown/missing CTC rate (%)
SELECT ROUND(
    COUNT(CASE WHEN ctc_status IN ('UNKNOWN', 'PENDING', 'MISSING') THEN 1 END)
    * 100.0 / COUNT(*), 1
) AS unknown_ctc_pct
FROM fact_offers;

-- No-CGPA-criteria offer count
SELECT COUNT(*) AS no_cgpa_offer_count
FROM fact_offers
WHERE no_cgpa_criteria = TRUE;
