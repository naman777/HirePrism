CREATE OR REPLACE VIEW vw_company_summary AS
SELECT
    company_name,
    COUNT(*)                                                                        AS total_offers,
    COUNT(DISTINCT offer_type_standardized)                                         AS distinct_offer_types,
    ROUND(AVG(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                                 AS avg_ctc_lpa,
    ROUND(MAX(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                                 AS max_ctc_lpa,
    COUNT(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                    AND ctc_lpa_normalized >= 10 THEN 1 END)                        AS high_package_count,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END)                             AS no_cgpa_count,
    COUNT(CASE WHEN ctc_status IN ('PENDING', 'MISSING', 'UNKNOWN') THEN 1 END)     AS unknown_ctc_count
FROM fact_offers
GROUP BY company_name
ORDER BY total_offers DESC, avg_ctc_lpa DESC NULLS LAST;
