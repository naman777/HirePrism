CREATE OR REPLACE VIEW vw_high_package_offers AS
SELECT
    offer_id,
    company_name,
    job_role_raw,
    role_standardized,
    job_family,
    offer_type_standardized,
    ctc_lpa_normalized,
    ctc_lpa_min,
    ctc_lpa_max,
    ctc_status,
    notice_date_raw,
    no_cgpa_criteria,
    location_extracted,
    work_mode_extracted
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
  AND ctc_lpa_normalized >= 10.0
ORDER BY ctc_lpa_normalized DESC;
