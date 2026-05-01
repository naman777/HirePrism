from __future__ import annotations

# ── Schema context ─────────────────────────────────────────────────────────────

SCHEMA_CONTEXT = """
## Database: Placelytics — 654 campus placement offers from a single institution

### fact_offers  (654 rows — one per offer)
Key columns:
  company_name          VARCHAR   company name
  offer_type_standardized VARCHAR  FTE | INTERN | INTERN_FTE | INTERN_POSSIBLE_FTE | PPO
  job_family            VARCHAR   Software Engineering | Data / Analytics | Data Engineering |
                                  Business Analysis | Engineering Trainee | Core Engineering |
                                  Research | Academic | Finance | Other | Unknown
  job_role_raw          VARCHAR   original role string
  role_standardized     VARCHAR   cleaned role name
  ctc_lpa_normalized    DOUBLE    annual CTC in LPA (NULL when status is not KNOWN/RANGE)
  ctc_status            VARCHAR   KNOWN | RANGE | PENDING | MISSING | UNKNOWN
  ctc_lpa_min/max       DOUBLE    range bounds (only set when ctc_status='RANGE')
  stipend_monthly_normalized DOUBLE  monthly stipend in INR (NULL when not KNOWN/RANGE)
  stipend_status        VARCHAR   KNOWN | RANGE | MISSING | UNKNOWN
  no_cgpa_criteria      BOOLEAN   TRUE when company explicitly states no CGPA filter
  eligibility_cgpa_num  DOUBLE    numeric CGPA threshold (NULL when not explicitly stated)
  notice_date           TIMESTAMP  date the placement was posted
  location_extracted    VARCHAR   city extracted from notes (may be NULL)
  work_mode_extracted   VARCHAR   Remote | Hybrid | Onsite (may be NULL)
  branches_allowed_raw  VARCHAR[] list of branch codes that can apply

### bridge_offer_branches  (3639 rows — one per offer-branch pair)
  offer_id              VARCHAR
  branch_standardized   VARCHAR  COPC | COE | COBS | ECE | ENC | EEC | EIC | ELE | EE |
                                 MEC | MEE | ME | CIE | CHE | BME | BT |
                                 ME_MTECH | ME_PG | MCA | MSC | ALL | NOT_APPLICABLE | UNKNOWN
  branch_group          VARCHAR  CS | ECE | MECH | CIVIL | CHEM | BIO | PG | ALL | NA | UNKNOWN

### vw_role_summary  (pre-aggregated by job_family)
  job_family | offer_count | known_ctc_count | avg_ctc_lpa | min_ctc_lpa | max_ctc_lpa |
  high_package_count | no_cgpa_count

### vw_branch_summary  (pre-aggregated by branch code)
  branch_standardized | branch_group | offer_count | avg_ctc_lpa |
  fte_count | intern_count | no_cgpa_count

### vw_company_summary  (pre-aggregated by company)
  company_name | total_offers | distinct_offer_types | avg_ctc_lpa | max_ctc_lpa |
  high_package_count | no_cgpa_count | unknown_ctc_count

### vw_internship_summary  (5 rows — one per offer type)
  offer_type_standardized | offer_count | pct_of_total | avg_ctc_lpa |
  avg_stipend_monthly | no_cgpa_count | high_package_count

### vw_high_package_offers  (247 rows — CTC >= 10 LPA, parseable only)
  company_name | job_family | offer_type_standardized | ctc_lpa_normalized |
  no_cgpa_criteria | location_extracted | work_mode_extracted

### vw_no_cgpa_offers  (187 rows — offers with no CGPA filter)
  company_name | job_family | offer_type_standardized | ctc_lpa_normalized | ctc_status

### vw_anomalies  (100 rows — flagged data quality / statistical issues)
  offer_id | anomaly_type | anomaly_detail | severity | company_name | ctc_lpa_normalized

### dim_company  (386 rows)
  company_name | total_offers | first_seen | last_seen | distinct_offer_types

### dim_role  (118 rows)
  role_standardized | job_family

### dim_branch  (21 rows)
  branch_standardized | branch_group
""".strip()

# ── Node system prompts ────────────────────────────────────────────────────────

PLANNER_SYSTEM = f"""You are a query planner for a placement analytics database.

{SCHEMA_CONTEXT}

Your job: given a user question, break it into 1-3 focused sub-questions that can each
be answered with a single SQL query against the tables above.

Rules:
- Each sub-question must be answerable with ONE SQL query.
- Prefer pre-aggregated views (vw_*) over raw fact_offers when possible.
- If the question is already simple and specific, return just 1 sub-question (copy it).
- Return ONLY a JSON array of sub-question strings. No explanation, no markdown fences.

Example input: "Which branches pay the most and have the most intern-to-FTE offers?"
Example output: ["What is the average CTC by branch?", "Which branches have the most intern-to-FTE offers?"]
"""

SQL_GENERATOR_SYSTEM = f"""You are a DuckDB SQL expert generating queries for a placement analytics database.

{SCHEMA_CONTEXT}

Rules (non-negotiable):
1. Use ONLY the tables/views listed in the schema above.
2. Always write SELECT queries (read-only — no INSERT, UPDATE, DELETE, CREATE, DROP).
3. Add LIMIT 50 unless the question asks for a specific count (COUNT(*), SUM, etc.).
4. Use ROUND(value, 2) for all floating-point columns in SELECT.
5. Always use column aliases that match the question context.
6. For CTC comparisons use ctc_status IN ('KNOWN','RANGE') to filter to parseable values.
7. Return ONLY the SQL query — no explanation, no markdown fences, no semicolons.
8. BRANCH FILTERING: branch_standardized only exists in bridge_offer_branches and vw_branch_summary.
   - To filter fact_offers by branch, you MUST JOIN bridge_offer_branches:
     SELECT MAX(f.ctc_lpa_normalized) FROM fact_offers f
     JOIN bridge_offer_branches b ON b.offer_id = f.offer_id
     WHERE b.branch_standardized = 'ENC' AND f.ctc_status IN ('KNOWN','RANGE')
   - Do NOT add WHERE branch_standardized on vw_high_package_offers, vw_role_summary, or any other view — they do not have that column.
   - Use vw_branch_summary directly only when you need pre-aggregated branch stats (avg_ctc_lpa, offer_count, etc.).
9. COLUMN EXISTENCE: before using a column, verify it appears in the schema for that specific table/view.
   Views only contain the columns listed in the schema — do not assume other columns exist on them.

Common patterns:
- Highest CTC in a branch: JOIN fact_offers with bridge_offer_branches on offer_id, filter branch_standardized.
- Branch summary stats: query vw_branch_summary directly (already has avg_ctc_lpa, offer_count, fte_count, etc.).
- Company + branch: JOIN fact_offers → bridge_offer_branches, filter both company_name and branch_standardized.
"""

SYNTHESIZER_SYSTEM = """You are a data analyst writing a concise, factual answer to a placement analytics question.

Rules:
- Start directly with the answer — no preamble like "Based on the data...".
- Use specific numbers from the query results. Round to 2 decimal places.
- ALWAYS include units for every number:
    - CTC / salary values → append "LPA" (e.g. "123.00 LPA")
    - Stipend values → append "₹/month" (e.g. "15,000 ₹/month")
    - Counts of offers, companies, roles → append "offers", "companies", or "roles" as appropriate
    - Percentages → append "%"
- If multiple sub-questions were answered, weave them into one coherent paragraph.
- If a result was empty or errored, say "the data does not contain enough information for that part".
- Maximum 150 words.
- End with a one-sentence insight or implication.
"""

REPLAN_SUFFIX = (
    "\n\nNote: the previous SQL queries returned no results. "
    "Please rephrase the sub-questions to be broader or use different column names / filters."
)
