CREATE OR REPLACE VIEW vw_internship_summary AS
SELECT
    offer_type_standardized,
    COUNT(*)                                                                          AS offer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)                               AS pct_of_total,
    ROUND(AVG(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                                   AS avg_ctc_lpa,
    ROUND(AVG(CASE WHEN stipend_status IN ('KNOWN', 'RANGE')
                   THEN stipend_monthly_normalized END), 0)                            AS avg_stipend_monthly,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END)                               AS no_cgpa_count,
    COUNT(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                    AND ctc_lpa_normalized >= 10 THEN 1 END)                          AS high_package_count
FROM fact_offers
GROUP BY offer_type_standardized
ORDER BY offer_count DESC;
