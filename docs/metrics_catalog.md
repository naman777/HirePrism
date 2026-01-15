# Metrics Catalog

24 named metrics defined in `metrics/definitions/`. Each metric has a canonical name, a SQL template executed against the DuckDB analytical model, and versioning metadata. Metrics are loaded by `src/metrics/loader.py` and executed by `src/metrics/executor.py`.

To run any metric: `MetricExecutor().run("metric_name")` → returns a `pd.DataFrame`.

---

## Compensation (8 metrics)

### avg_ctc_by_job_family
**Label:** Average CTC by Job Family  
**Tags:** compensation, role  
**Version:** 1.0  
**Description:** Mean normalized CTC (LPA) per job family, for offers where CTC is known or a range.

```sql
SELECT
    job_family,
    COUNT(*)                                    AS offer_count,
    ROUND(AVG(ctc_lpa_normalized), 2)           AS avg_ctc_lpa,
    ROUND(MIN(ctc_lpa_normalized), 2)           AS min_ctc_lpa,
    ROUND(MAX(ctc_lpa_normalized), 2)           AS max_ctc_lpa,
    ROUND(STDDEV(ctc_lpa_normalized), 2)        AS stddev_ctc_lpa
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
GROUP BY job_family
ORDER BY avg_ctc_lpa DESC NULLS LAST
```

---

### avg_ctc_by_branch
**Label:** Average CTC by Branch  
**Tags:** compensation, branch  
**Version:** 1.0  
**Description:** Mean normalized CTC (LPA) per branch code, joining through the bridge table.

```sql
SELECT
    b.branch_standardized,
    b.branch_group,
    COUNT(DISTINCT b.offer_id)                  AS offer_count,
    ROUND(AVG(f.ctc_lpa_normalized), 2)         AS avg_ctc_lpa,
    ROUND(MIN(f.ctc_lpa_normalized), 2)         AS min_ctc_lpa,
    ROUND(MAX(f.ctc_lpa_normalized), 2)         AS max_ctc_lpa
FROM bridge_offer_branches b
JOIN fact_offers f ON b.offer_id = f.offer_id
WHERE f.ctc_status IN ('KNOWN', 'RANGE')
  AND b.branch_standardized NOT IN ('UNKNOWN', 'NOT_APPLICABLE')
GROUP BY b.branch_standardized, b.branch_group
ORDER BY avg_ctc_lpa DESC NULLS LAST
```

---

### high_package_rate *(KPI)*
**Label:** High Package Rate  
**Tags:** compensation, kpi  
**Version:** 1.0  
**Description:** Percentage of known-CTC offers that are 10 LPA or above.

```sql
SELECT
    ROUND(
        COUNT(CASE WHEN ctc_lpa_normalized >= 10 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                           AS high_package_pct,
    COUNT(CASE WHEN ctc_lpa_normalized >= 10 THEN 1 END)
                                                AS high_package_count,
    COUNT(*)                                    AS total_known_ctc
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
```

---

### ctc_status_breakdown
**Label:** CTC Status Breakdown  
**Tags:** compensation, quality  
**Version:** 1.0  
**Description:** Distribution of CTC parsing status across all offers.

```sql
SELECT
    ctc_status,
    COUNT(*)                                    AS offer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)
                                                AS pct_of_total
FROM fact_offers
GROUP BY ctc_status
ORDER BY offer_count DESC
```

---

### stipend_by_offer_type
**Label:** Average Stipend by Offer Type  
**Tags:** compensation, internship  
**Version:** 1.0  
**Description:** Mean monthly stipend (INR) per standardized offer type, for offers with known stipend.

```sql
SELECT
    offer_type_standardized,
    COUNT(*)                                    AS offer_count,
    ROUND(AVG(stipend_monthly_normalized), 0)   AS avg_stipend_monthly,
    ROUND(MIN(stipend_monthly_normalized), 0)   AS min_stipend_monthly,
    ROUND(MAX(stipend_monthly_normalized), 0)   AS max_stipend_monthly
FROM fact_offers
WHERE stipend_status IN ('KNOWN', 'RANGE')
GROUP BY offer_type_standardized
ORDER BY avg_stipend_monthly DESC NULLS LAST
```

---

### top_paying_companies
**Label:** Top 20 Companies by Average CTC  
**Tags:** compensation, company  
**Version:** 1.0  
**Description:** Companies with highest mean CTC, filtered to those with at least 2 known-CTC offers.

```sql
SELECT
    company_name,
    COUNT(*)                                    AS offer_count,
    ROUND(AVG(ctc_lpa_normalized), 2)           AS avg_ctc_lpa,
    ROUND(MAX(ctc_lpa_normalized), 2)           AS max_ctc_lpa
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
GROUP BY company_name
HAVING COUNT(*) >= 2
ORDER BY avg_ctc_lpa DESC
LIMIT 20
```

---

### ctc_over_time
**Label:** Average CTC Trend by Notice Date  
**Tags:** compensation, trend  
**Version:** 1.0  
**Description:** Monthly trend of average CTC, to see if compensation is rising over the dataset period.

```sql
SELECT
    STRFTIME(notice_date, '%Y-%m')              AS month,
    COUNT(*)                                    AS offer_count,
    ROUND(AVG(ctc_lpa_normalized), 2)           AS avg_ctc_lpa
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
  AND notice_date IS NOT NULL
GROUP BY STRFTIME(notice_date, '%Y-%m')
ORDER BY month
```

---

## Roles (6 metrics)

### role_family_distribution
**Label:** Offer Count by Job Family  
**Tags:** roles  
**Version:** 1.0  
**Description:** Number of offers per job family, all offer types included.

```sql
SELECT
    job_family,
    COUNT(*)                                    AS offer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)
                                                AS pct_of_total
FROM fact_offers
GROUP BY job_family
ORDER BY offer_count DESC
```

---

### top_roles_by_frequency
**Label:** Top 20 Raw Roles by Frequency  
**Tags:** roles  
**Version:** 1.0  
**Description:** Most frequently appearing raw jobRole strings across all offers.

```sql
SELECT
    job_role_raw,
    role_standardized,
    job_family,
    COUNT(*)                                    AS offer_count
FROM fact_offers
WHERE job_role_raw IS NOT NULL
  AND job_role_raw NOT IN ('', 'Not Known', 'Not Declared', '-')
GROUP BY job_role_raw, role_standardized, job_family
ORDER BY offer_count DESC
LIMIT 20
```

---

### avg_ctc_by_role_family
**Label:** Average CTC by Role Family  
**Tags:** roles, compensation  
**Version:** 1.0  
**Description:** Mean CTC per job family for offers where CTC is known, with variance metrics. Delegates to `vw_role_summary`.

```sql
SELECT * FROM vw_role_summary
```

---

### role_ctc_variance
**Label:** CTC Variance by Job Family  
**Tags:** roles, compensation  
**Version:** 1.0  
**Description:** Coefficient of variation (stddev/mean) shows which role families have the most pay dispersion.

```sql
SELECT
    job_family,
    COUNT(*)                                            AS offer_count,
    ROUND(AVG(ctc_lpa_normalized), 2)                  AS avg_ctc_lpa,
    ROUND(STDDEV(ctc_lpa_normalized), 2)               AS stddev_ctc_lpa,
    ROUND(STDDEV(ctc_lpa_normalized) / NULLIF(AVG(ctc_lpa_normalized), 0), 3)
                                                       AS coeff_of_variation
FROM fact_offers
WHERE ctc_status IN ('KNOWN', 'RANGE')
GROUP BY job_family
HAVING COUNT(*) >= 5
ORDER BY coeff_of_variation DESC NULLS LAST
```

---

### no_cgpa_by_role_family
**Label:** No-CGPA Offer Rate by Role Family  
**Tags:** roles, eligibility  
**Version:** 1.0  
**Description:** Job families where the most offers have no CGPA requirement.

```sql
SELECT
    job_family,
    COUNT(*)                                    AS total_offers,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END)
                                                AS no_cgpa_count,
    ROUND(
        COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                           AS no_cgpa_pct
FROM fact_offers
GROUP BY job_family
ORDER BY no_cgpa_pct DESC
```

---

### offer_type_by_role_family
**Label:** Offer Type Mix by Role Family  
**Tags:** roles, internship  
**Version:** 1.0  
**Description:** For each job family, how many offers are FTE vs intern vs intern-to-FTE.

```sql
SELECT
    job_family,
    offer_type_standardized,
    COUNT(*)                                    AS offer_count,
    ROUND(COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (PARTITION BY job_family), 1)
                                                AS pct_within_family
FROM fact_offers
GROUP BY job_family, offer_type_standardized
ORDER BY job_family, offer_count DESC
```

---

## Branches (5 metrics)

### branch_opportunity_count
**Label:** Offer Count by Branch  
**Tags:** branches  
**Version:** 1.0  
**Description:** Number of distinct offers open to each branch code, excluding unknown/NA entries. Delegates to `vw_branch_summary`.

```sql
SELECT * FROM vw_branch_summary
ORDER BY offer_count DESC
```

---

### branch_group_distribution
**Label:** Offer Count by Branch Group  
**Tags:** branches  
**Version:** 1.0  
**Description:** Aggregated opportunity count by broader branch group (CS, ECE, MECH, etc.).

```sql
SELECT
    b.branch_group,
    COUNT(DISTINCT b.offer_id)                  AS offer_count,
    ROUND(AVG(f.ctc_lpa_normalized), 2)         AS avg_ctc_lpa,
    COUNT(CASE WHEN f.offer_type_standardized = 'FTE' THEN 1 END) AS fte_count,
    COUNT(CASE WHEN f.offer_type_standardized IN
        ('INTERN', 'INTERN_FTE', 'INTERN_POSSIBLE_FTE') THEN 1 END) AS intern_count
FROM bridge_offer_branches b
JOIN fact_offers f ON b.offer_id = f.offer_id
WHERE b.branch_group NOT IN ('UNKNOWN', 'NA')
  AND f.ctc_status IN ('KNOWN', 'RANGE')
GROUP BY b.branch_group
ORDER BY offer_count DESC
```

---

### fte_vs_intern_by_branch
**Label:** FTE vs Intern Split by Branch  
**Tags:** branches, internship  
**Version:** 1.0  
**Description:** For each branch, the breakdown between full-time and internship offers.

```sql
SELECT
    b.branch_standardized, b.branch_group,
    COUNT(DISTINCT b.offer_id)                  AS total_offers,
    COUNT(CASE WHEN f.offer_type_standardized = 'FTE' THEN 1 END) AS fte_count,
    COUNT(CASE WHEN f.offer_type_standardized IN
        ('INTERN', 'INTERN_FTE', 'INTERN_POSSIBLE_FTE') THEN 1 END) AS intern_count,
    COUNT(CASE WHEN f.offer_type_standardized = 'PPO' THEN 1 END) AS ppo_count,
    ROUND(
        COUNT(CASE WHEN f.offer_type_standardized = 'FTE' THEN 1 END)
        * 100.0 / COUNT(DISTINCT b.offer_id), 1
    )                                           AS fte_pct
FROM bridge_offer_branches b
JOIN fact_offers f ON b.offer_id = f.offer_id
WHERE b.branch_standardized NOT IN ('UNKNOWN', 'NOT_APPLICABLE')
GROUP BY b.branch_standardized, b.branch_group
ORDER BY total_offers DESC
```

---

### branch_avg_ctc
**Label:** Average CTC by Branch (Known Only)  
**Tags:** branches, compensation  
**Version:** 1.0  
**Description:** Mean LPA per branch for offers with a parseable CTC value.

```sql
SELECT
    b.branch_standardized, b.branch_group,
    COUNT(DISTINCT b.offer_id)                  AS offer_count,
    ROUND(AVG(f.ctc_lpa_normalized), 2)         AS avg_ctc_lpa,
    ROUND(MAX(f.ctc_lpa_normalized), 2)         AS max_ctc_lpa
FROM bridge_offer_branches b
JOIN fact_offers f ON b.offer_id = f.offer_id
WHERE f.ctc_status IN ('KNOWN', 'RANGE')
  AND b.branch_standardized NOT IN ('UNKNOWN', 'NOT_APPLICABLE')
GROUP BY b.branch_standardized, b.branch_group
ORDER BY avg_ctc_lpa DESC NULLS LAST
```

---

### top_companies_by_branch
**Label:** Top Companies Open to CS Branches  
**Tags:** branches, compensation, company  
**Version:** 1.0  
**Description:** Companies recruiting CS-group branches (COPC, COE, COBS) with the highest CTC.

```sql
SELECT
    f.company_name,
    ROUND(AVG(f.ctc_lpa_normalized), 2)         AS avg_ctc_lpa,
    COUNT(DISTINCT f.offer_id)                  AS offer_count,
    LIST(DISTINCT b.branch_standardized)        AS branches
FROM fact_offers f
JOIN bridge_offer_branches b ON f.offer_id = b.offer_id
WHERE b.branch_group = 'CS'
  AND f.ctc_status IN ('KNOWN', 'RANGE')
GROUP BY f.company_name
ORDER BY avg_ctc_lpa DESC NULLS LAST
LIMIT 15
```

---

## Eligibility (6 metrics)

### no_cgpa_offer_rate *(KPI)*
**Label:** No-CGPA Offer Rate  
**Tags:** eligibility, kpi  
**Version:** 1.0  
**Description:** Percentage of all offers that explicitly state no CGPA requirement.

```sql
SELECT
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) AS no_cgpa_count,
    COUNT(*)                                    AS total_offers,
    ROUND(
        COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                           AS no_cgpa_pct
FROM fact_offers
```

---

### cgpa_threshold_distribution
**Label:** CGPA Threshold Distribution  
**Tags:** eligibility  
**Version:** 1.0  
**Description:** Frequency of each numeric CGPA threshold across offers that specify one.

```sql
SELECT
    eligibility_cgpa_num                        AS cgpa_threshold,
    COUNT(*)                                    AS offer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)
                                                AS pct_of_known
FROM fact_offers
WHERE eligibility_status = 'KNOWN'
  AND eligibility_cgpa_num IS NOT NULL
GROUP BY eligibility_cgpa_num
ORDER BY eligibility_cgpa_num
```

---

### eligibility_status_breakdown
**Label:** Eligibility Status Breakdown  
**Tags:** eligibility, quality  
**Version:** 1.0  
**Description:** Distribution of eligibility parsing outcomes across all offers.

```sql
SELECT
    eligibility_status,
    COUNT(*)                                    AS offer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)
                                                AS pct_of_total
FROM fact_offers
GROUP BY eligibility_status
ORDER BY offer_count DESC
```

---

### no_cgpa_by_company
**Label:** Companies with Most No-CGPA Offers  
**Tags:** eligibility, company  
**Version:** 1.0  
**Description:** Top companies offering the most positions without a CGPA filter.

```sql
SELECT
    company_name,
    COUNT(*)                                    AS total_offers,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) AS no_cgpa_count,
    ROUND(AVG(CASE WHEN ctc_status IN ('KNOWN', 'RANGE')
              THEN ctc_lpa_normalized END), 2)  AS avg_ctc_lpa
FROM fact_offers
GROUP BY company_name
HAVING COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) > 0
ORDER BY no_cgpa_count DESC, avg_ctc_lpa DESC NULLS LAST
LIMIT 20
```

---

### high_package_no_cgpa
**Label:** High-Package Offers with No CGPA Requirement  
**Tags:** eligibility, compensation  
**Version:** 1.0  
**Description:** Offers ≥ 10 LPA that require no CGPA — the most accessible high-value opportunities.

```sql
SELECT
    company_name, job_role_raw, role_standardized, job_family,
    offer_type_standardized, ctc_lpa_normalized, ctc_status,
    notice_date_raw, location_extracted, work_mode_extracted
FROM fact_offers
WHERE no_cgpa_criteria = TRUE
  AND ctc_status IN ('KNOWN', 'RANGE')
  AND ctc_lpa_normalized >= 10.0
ORDER BY ctc_lpa_normalized DESC
```

---

### avg_cgpa_by_job_family
**Label:** Average CGPA Threshold by Job Family  
**Tags:** eligibility, roles  
**Version:** 1.0  
**Description:** Mean CGPA cutoff per job family — shows which roles are academically selective.

```sql
SELECT
    job_family,
    COUNT(CASE WHEN eligibility_status = 'KNOWN' THEN 1 END) AS known_cgpa_count,
    ROUND(AVG(CASE WHEN eligibility_status = 'KNOWN'
              THEN eligibility_cgpa_num END), 2) AS avg_cgpa_threshold,
    COUNT(CASE WHEN no_cgpa_criteria = TRUE THEN 1 END) AS no_cgpa_count
FROM fact_offers
GROUP BY job_family
ORDER BY avg_cgpa_threshold DESC NULLS LAST
```
