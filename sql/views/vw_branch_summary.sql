CREATE OR REPLACE VIEW vw_branch_summary AS
SELECT
    b.branch_standardized,
    b.branch_group,
    COUNT(DISTINCT b.offer_id)                                                        AS offer_count,
    ROUND(AVG(CASE WHEN f.ctc_status IN ('KNOWN', 'RANGE')
                   THEN f.ctc_lpa_normalized END), 2)                                 AS avg_ctc_lpa,
    COUNT(CASE WHEN f.offer_type_standardized = 'FTE' THEN 1 END)                     AS fte_count,
    COUNT(CASE WHEN f.offer_type_standardized IN ('INTERN', 'INTERN_FTE',
                                                   'INTERN_POSSIBLE_FTE') THEN 1 END) AS intern_count,
    COUNT(CASE WHEN f.no_cgpa_criteria = TRUE THEN 1 END)                             AS no_cgpa_count
FROM bridge_offer_branches b
JOIN fact_offers f ON b.offer_id = f.offer_id
WHERE b.branch_standardized NOT IN ('UNKNOWN', 'NOT_APPLICABLE')
GROUP BY b.branch_standardized, b.branch_group
ORDER BY offer_count DESC;
