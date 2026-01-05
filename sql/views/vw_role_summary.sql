CREATE OR REPLACE VIEW vw_role_summary AS
SELECT
    job_family,
    COUNT(*)                                                                     AS offer_count,
    COUNT(CASE WHEN ctc_status IN ('KNOWN', 'RANGE') THEN 1 END)                AS known_ctc_count,
    ROUND(AVG(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                             AS avg_ctc_lpa,
    ROUND(MIN(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                             AS min_ctc_lpa,
    ROUND(MAX(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                   THEN ctc_lpa_normalized END), 2)                             AS max_ctc_lpa,
    COUNT(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
                    AND ctc_lpa_normalized >= 10 THEN 1 END)                    AS high_package_count,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END)                         AS no_cgpa_count
FROM fact_offers
GROUP BY job_family
ORDER BY avg_ctc_lpa DESC NULLS LAST;
