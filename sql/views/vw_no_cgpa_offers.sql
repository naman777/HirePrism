CREATE OR REPLACE VIEW vw_no_cgpa_offers AS
SELECT
    offer_id,
    company_name,
    job_role_raw,
    role_standardized,
    job_family,
    offer_type_standardized,
    ctc_lpa_normalized,
    ctc_status,
    stipend_monthly_normalized,
    stipend_status,
    notice_date_raw,
    location_extracted,
    work_mode_extracted
FROM fact_offers
WHERE no_cgpa_criteria = TRUE
ORDER BY ctc_lpa_normalized DESC NULLS LAST;
