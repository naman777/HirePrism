CREATE OR REPLACE VIEW vw_compensation_unknown AS
SELECT
    offer_id,
    company_name,
    job_role_raw,
    role_standardized,
    offer_type_standardized,
    ctc_status,
    ctc_raw,
    ctc_note_raw,
    stipend_status,
    stipend_raw,
    notice_date_raw
FROM fact_offers
WHERE ctc_status IN ('PENDING', 'MISSING', 'UNKNOWN')
ORDER BY company_name, ctc_status;
