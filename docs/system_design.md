# Placelytics — Complete System Design

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PLACELYTICS SYSTEM                                │
│                                                                             │
│  ┌──────────────┐    ┌─────────────────────┐    ┌─────────────────────┐    │
│  │   RAW DATA   │    │   PIPELINE LAYER    │    │  ANALYTICAL MODEL   │    │
│  │              │    │                     │    │                     │    │
│  │ placements   │───▶│ Ingestion           │    │  DuckDB             │    │
│  │ .json        │    │ Cleaning            │───▶│  (5 tables          │    │
│  │ 461 records  │    │ Quality Scoring     │    │   7 views           │    │
│  │ 654 offers   │    │ Parquet Files       │    │   anomaly_flags)    │    │
│  └──────────────┘    └─────────────────────┘    └──────────┬──────────┘    │
│                                                             │               │
│                      ┌──────────────────────────────────────┤               │
│                      │                                      │               │
│              ┌───────▼──────┐  ┌────────────┐  ┌──────────▼────────┐      │
│              │ METRICS      │  │  ANOMALY   │  │  INSIGHT          │      │
│              │ LAYER        │  │  DETECTOR  │  │  GENERATOR        │      │
│              │ 24 YAML      │  │  5 methods │  │  8 findings       │      │
│              │ metrics      │  │  100 flags │  │  InsightCards     │      │
│              └──────┬───────┘  └────────────┘  └──────────┬────────┘      │
│                     │                                       │               │
│              ┌──────▼───────────────────────────────────────▼────────┐     │
│              │               LANGGRAPH AGENT                         │     │
│              │   Planner → SQL Gen → Executor → Validator → Synth   │     │
│              │   (Claude API · read-only DuckDB · 10s timeout)       │     │
│              └────────────────────────┬──────────────────────────────┘     │
│                                       │                                     │
│              ┌────────────────────────▼──────────────────────────────┐     │
│              │               STREAMLIT APPLICATION                   │     │
│              │  Overview · Compensation · Roles · Branches           │     │
│              │  Companies · Insights · Quality · Query Console       │     │
│              └───────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Pipeline Design

### 2A. Phase Map

```
Phase 1         Phase 2           Phase 3                 Phase 4
PROFILING   →  INGESTION      →  CLEANING            →  QUALITY SCORING
                                                         
load_json      load_json          parse_ctc              checks.py
profile_       flatten_offers     parse_stipend          scorer.py
placements                        parse_dates            report.py
                                  normalize_roles
                                  normalize_branches         ↓
                                  extract_notes
                                                      quality_report.json
                                      ↓               quality_history.jsonl
                              fact_offers_clean
                              .parquet
                              bridge_offer_branches
                              .parquet

Phase 5            Phase 6            Phase 7          Phase 8
DUCKDB MODEL   →  METRICS LAYER  →  ANOMALY       →  INSIGHTS
                                    DETECTION
build_tables       loader.py         detector.py      generator.py
build_views        executor.py       explainer.py     templates.py

placelytics        MetricRegistry    anomaly_flags    InsightCard × 8
.duckdb            MetricExecutor    vw_anomalies     insight_report.json
5 tables                                              insight_report.md
7 views            24 metrics
                   in 4 YAMLs
```

### 2B. Complete Data Flow

```
placements.json
      │
      │  load_placements()
      │  → validates top-level key "placements"
      │  → returns list[dict], 461 records
      ▼
[Profiling] ─────────────────────────────────► notebooks/01_profiling.ipynb
      │                                         docs/assumptions.md
      │  flatten_offers()
      │  → loops each record × each offer
      │  → generates offer_id = SHA-256(record_id:index)[:16]
      │  → carries forward: record_id, company_name, notice_date_raw,
      │    created_at_seconds, created_at_nanoseconds
      │  → handles 98-record branch spillover (branches_from_parent flag)
      ▼
raw_flat_offers (DataFrame, 654 rows × 22 cols)
      │
      │  Cleaning runs in sequence on same DataFrame:
      │
      │  parse_ctc(ctc_raw) ─────────────────────────────────────────────►
      │    case 1: None/"" → status=MISSING
      │    case 2: pending token match → status=PENDING
      │    case 3: unknown token match → status=UNKNOWN
      │    case 4: " / " split (degree variant) → status=RANGE
      │    case 5: hyphen/en-dash range → status=RANGE
      │    case 6: plain integer → status=KNOWN
      │    adds: ctc_lpa_min, ctc_lpa_max, ctc_lpa_normalized, ctc_status
      │
      │  parse_stipend(stipend_raw) ─────────────────────────────────────►
      │    same 6-case pattern, amounts in INR/month
      │    adds: stipend_monthly_min, stipend_monthly_max,
      │          stipend_monthly_normalized, stipend_status
      │
      │  parse_dates(notice_date_raw, created_at_seconds) ──────────────►
      │    tries %d/%m/%Y, %Y-%m-%d, ISO variants
      │    adds: notice_date, created_at (UTC), offer_type_standardized
      │
      │  normalize_roles(job_role_raw) ──────────────────────────────────►
      │    step 1: exact lookup in ROLE_MAP (120 entries)
      │    step 2: rapidfuzz fuzzy match (threshold=82) against ROLE_MAP keys
      │    step 3: _keyword_family() regex patterns
      │    step 4: fallback → job_family="Other"
      │    adds: role_standardized, job_family
      │
      │  normalize_branches(branches_allowed_raw) ───────────────────────►
      │    canonical map: 21 raw codes → standard codes + branch_group
      │    builds: bridge_offer_branches rows (exploded)
      │    adds: (bridge table built separately)
      │
      │  extract_notes(notes fields) ────────────────────────────────────►
      │    regex: city names, work_mode, duration months, gross CTC signal
      │    adds: location_extracted, work_mode_extracted,
      │          duration_months_extracted, gross_ctc_signal
      ▼
fact_offers_clean.parquet  (654 rows × 44 cols)
bridge_offer_branches.parquet  (3,639 rows × 4 cols)
      │
      │  Quality Scoring:
      │  6 check functions → run_quality_checks(df) → dict
      │  appends → quality_history.jsonl
      │  saves → quality_report.json
      │
      │  DuckDB Build:
      │  CREATE OR REPLACE TABLE fact_offers FROM parquet
      │  CREATE OR REPLACE TABLE bridge_offer_branches FROM parquet
      │  derive dim_role, dim_branch, dim_company
      │  execute sql/views/*.sql → 7 views
      │
      │  Anomaly Detection:
      │  detect_all(df) → anomaly_flags DataFrame
      │  INSERT INTO anomaly_flags TABLE in DuckDB
      │  CREATE OR REPLACE VIEW vw_anomalies
      │
      │  Insight Generation:
      │  8 functions × DuckDB queries → list[InsightCard]
      │  → insight_report.json
      │  → insight_report.md
      ▼
placelytics.duckdb
  (5 tables + 7 views + anomaly_flags + vw_anomalies)
```

---

## 3. Database Schema Design

### 3A. Entity-Relationship Diagram

```
                        ┌─────────────────────────────────────────────────┐
                        │                  fact_offers                    │
                        │  (654 rows — one row per placement offer)       │
                        │                                                 │
                        │  PK  offer_id         VARCHAR  16-char hex     │
                        │      record_id         VARCHAR  Firestore doc ID│
                        │      company_name      VARCHAR                  │
                        │  ── RAW ──────────────────────────────────────  │
                        │      notice_date_raw   VARCHAR  original string │
                        │      offer_type_raw    VARCHAR                  │
                        │      job_role_raw      VARCHAR                  │
                        │      ctc_raw           VARCHAR                  │
                        │      stipend_raw        VARCHAR                  │
                        │      eligibility_cgpa_raw  VARCHAR              │
                        │      branches_allowed_raw  VARCHAR[]            │
                        │  ── CLEANED ──────────────────────────────────  │
                        │      notice_date        TIMESTAMP               │
                        │      offer_type_standardized VARCHAR            │
                        │      ctc_lpa_normalized DOUBLE                  │
                        │      ctc_lpa_min        DOUBLE                  │
                        │      ctc_lpa_max        DOUBLE                  │
                        │      ctc_status         VARCHAR  KNOWN/RANGE/…  │
                        │      stipend_monthly_normalized DOUBLE          │
                        │      stipend_status     VARCHAR                 │
                        │      role_standardized  VARCHAR                 │
                        │      job_family         VARCHAR                 │
                        │      no_cgpa_criteria   BOOLEAN                 │
                        │      eligibility_cgpa_num DOUBLE               │
                        │      eligibility_status VARCHAR                 │
                        │      location_extracted VARCHAR                 │
                        │      work_mode_extracted VARCHAR                │
                        └──────────────────┬──────────────────────────────┘
                                           │ 1
                                           │
                             1────────────▼────────────N
                        ┌──────────────────────────────────────┐
                        │       bridge_offer_branches          │
                        │  (3,639 rows — one per offer-branch) │
                        │                                      │
                        │  FK  offer_id           VARCHAR      │
                        │  FK  branch_standardized VARCHAR     │
                        │      branch_group        VARCHAR     │
                        └──────────────────┬───────────────────┘
                                           │ N
                                           │
                                    1──────▼──────N
                        ┌───────────────────────────────────┐
                        │           dim_branch              │
                        │  (21 rows — controlled vocab)     │
                        │                                   │
                        │  PK  branch_standardized VARCHAR  │
                        │      branch_group        VARCHAR  │
                        └───────────────────────────────────┘


        fact_offers ──N──────────────────────────────1── dim_company
        (company_name FK)                            (386 rows)
                                                     company_name  VARCHAR PK
                                                     total_offers  INT
                                                     first_seen    DATE
                                                     last_seen     DATE
                                                     distinct_offer_types INT


        fact_offers ──N──────────────────────────────1── dim_role
        (role_standardized FK)                       (118 rows)
                                                     role_standardized VARCHAR PK
                                                     job_family        VARCHAR


        fact_offers ──1──────────────────────────────N── anomaly_flags
        (offer_id FK)                                (100 rows)
                                                     offer_id      VARCHAR FK
                                                     anomaly_type  VARCHAR
                                                     anomaly_detail VARCHAR
                                                     severity      VARCHAR
```

### 3B. View Definitions

```
vw_high_package_offers  (247 rows)
  WHERE ctc_status IN ('KNOWN','RANGE') AND ctc_lpa_normalized >= 10
  → columns: company_name, job_family, offer_type, ctc_lpa, no_cgpa_criteria,
             location, work_mode

vw_role_summary  (11 rows — one per job family)
  GROUP BY job_family on fact_offers
  → columns: job_family, offer_count, known_ctc_count, avg_ctc_lpa,
             min_ctc_lpa, max_ctc_lpa, high_package_count, no_cgpa_count

vw_branch_summary  (21 rows — one per branch code)
  JOIN fact_offers × bridge_offer_branches, GROUP BY branch_standardized
  → columns: branch_standardized, branch_group, offer_count, avg_ctc_lpa,
             fte_count, intern_count, no_cgpa_count

vw_company_summary  (386 rows — one per company)
  GROUP BY company_name on fact_offers
  → columns: company_name, total_offers, distinct_offer_types, avg_ctc_lpa,
             max_ctc_lpa, high_package_count, no_cgpa_count, unknown_ctc_count

vw_internship_summary  (5 rows — one per offer type)
  GROUP BY offer_type_standardized
  → columns: offer_type, offer_count, pct_of_total, avg_ctc_lpa,
             avg_stipend_monthly, no_cgpa_count, high_package_count

vw_no_cgpa_offers  (187 rows)
  WHERE no_cgpa_criteria = TRUE
  → columns: company_name, job_family, offer_type, ctc_lpa_normalized, ctc_status

vw_compensation_unknown  (113 rows)
  WHERE ctc_status IN ('MISSING','UNKNOWN','PENDING')
  → columns: company_name, job_role_raw, offer_type, ctc_raw, ctc_status

vw_anomalies  (100 rows)
  JOIN anomaly_flags × fact_offers
  → columns: offer_id, anomaly_type, anomaly_detail, severity,
             company_name, ctc_lpa_normalized
```

---

## 4. Cleaning Pipeline — Internal Design

### 4A. CTC Parser State Machine

```
        raw CTC string
              │
              ▼
      ┌───────────────┐
      │ None or ""?   │─── YES ──▶  MISSING
      └───────┬───────┘
              │ NO
              ▼
      ┌─────────────────────────────────┐
      │ contains a PENDING token?       │─── YES ──▶  PENDING
      │ (negotiable / to be notified /  │            (no numeric fields)
      │  process pending / …)           │
      └───────┬─────────────────────────┘
              │ NO
              ▼
      ┌─────────────────────────────────┐
      │ contains an UNKNOWN token?      │─── YES ──▶  UNKNOWN
      │ (not disclosed / not known /    │            (no numeric fields)
      │  not declared / …)              │
      └───────┬─────────────────────────┘
              │ NO
              ▼
      ┌─────────────────────────────────┐
      │ contains " / " (degree split)?  │─── YES ──▶  extract integers from
      │ "6,56,000 (B.E.) / 7,36,000    │            each part, take min/max
      │  (M.E./M.Sc.)"                 │            → RANGE (min, max, midpoint)
      └───────┬─────────────────────────┘
              │ NO
              ▼
      ┌─────────────────────────────────┐
      │ regex: (\d+)\s*[-–]\s*(\d+)    │─── YES ──▶  a ≠ b, both > 0
      │ hyphen/en-dash range?           │            → RANGE (lo, hi, midpoint)
      │ "800000-1200000"                │
      └───────┬─────────────────────────┘
              │ NO
              ▼
      ┌─────────────────────────────────┐
      │ regex: ^\d+$ (plain integer)?   │─── YES ──▶  ÷ 100,000 → LPA
      │ "411000", "920000"              │            → KNOWN (single value)
      └───────┬─────────────────────────┘
              │ NO
              ▼
           UNKNOWN  (free text, unparseable)
```

### 4B. Role Normalization Lookup Chain

```
      raw job_role string
              │
              ▼
      lowercase + strip
              │
              ▼
      ┌─────────────────────────────────────────────────────────┐
      │  Step 1: Exact lookup in ROLE_MAP (120 entries)         │──── HIT ──▶ return (std, family)
      │  key = lowercased raw string                            │
      └─────────────────────────────────┬───────────────────────┘
                                        │ MISS
                                        ▼
      ┌─────────────────────────────────────────────────────────┐
      │  Step 2: rapidfuzz extractOne                           │
      │  score_cutoff = 82 (Levenshtein-based similarity)       │──── HIT ──▶ return (std, family)
      │  matches against all ROLE_MAP keys                      │            from matched key
      └─────────────────────────────────┬───────────────────────┘
                                        │ MISS (score < 82)
                                        ▼
      ┌─────────────────────────────────────────────────────────┐
      │  Step 3: _keyword_family(lower)                         │
      │  checks ordered keyword groups:                         │
      │    "etl","pipeline"           → Data Engineering        │
      │    "data analyst","ml ","ai " → Data / Analytics        │
      │    "software","sde","backend" → Software Engineering     │
      │    "business analyst","strat" → Business Analysis       │
      │    "graduate engineer","get"  → Engineering Trainee     │
      │    "mechanical","electrical"  → Core Engineering        │
      │    "research","patent","r&d"  → Research                │
      │    "finance","quant"          → Finance                 │
      │    "professor","lecturer"     → Academic                │
      └─────────────────────────────────┬───────────────────────┘
                                        │ no keyword match
                                        ▼
                                 job_family = "Other"
                                 role_standardized = raw.strip()
```

---

## 5. Quality Scoring System Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     QUALITY SCORING ARCHITECTURE                        │
│                                                                         │
│  INPUT: fact_offers_clean DataFrame (654 rows)                          │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      checks.py                                  │   │
│  │                                                                  │   │
│  │  check_ctc_parseability()     → 0.8272  (KNOWN+RANGE / total)  │   │
│  │  check_stipend_parseability() → 0.6988  (KNOWN+RANGE / total)  │   │
│  │  check_branch_coverage()      → 0.9924  (has known branch)     │   │
│  │  check_role_standardization() → 0.9602  (job_family != Unknown) │   │
│  │  check_date_validity()        → 1.0000  (notice_date not null) │   │
│  │  check_cgpa_numeric_rate()    → 0.6697  (eligibility = KNOWN)  │   │
│  └───────────────────────────────┬─────────────────────────────────┘   │
│                                  │                                       │
│                                  ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      scorer.py                                  │   │
│  │                                                                  │   │
│  │  overall_score = mean(all_scores) = 0.858                       │   │
│  │                                                                  │   │
│  │  for each score < FLAG_THRESHOLD (0.75):                        │   │
│  │    → _severity():  score < 0.50 → HIGH                         │   │
│  │                    score < 0.65 → MEDIUM                        │   │
│  │                    score >= 0.65 → LOW                          │   │
│  │    → _flag_message(): human-readable explanation                │   │
│  │                                                                  │   │
│  │  flagged_issues: [stipend_parseability LOW,                     │   │
│  │                   cgpa_numeric_rate LOW]                        │   │
│  └───────────────────────────────┬─────────────────────────────────┘   │
│                                  │                                       │
│                                  ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      report.py                                  │   │
│  │                                                                  │   │
│  │  save_report(report_dict)                                       │   │
│  │    → overwrites data/quality/quality_report.json  (latest)     │   │
│  │    → APPENDS line to data/quality/quality_history.jsonl        │   │
│  │         (one JSON object per pipeline run, with timestamp)      │   │
│  │                                                                  │   │
│  │  load_history() → list[dict]  (for trend chart in app)         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  OUTPUT SCHEMA:                                                         │
│  {                                                                      │
│    "run_timestamp": "2026-04-24T10:30:00",                             │
│    "total_offers": 654,                                                 │
│    "scores": { "ctc_parseability": 0.8272, … },                       │
│    "overall_score": 0.858,                                             │
│    "flagged_issues": [{"check": …, "score": …, "severity": …, …}]    │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Anomaly Detection Design

```
┌────────────────────────────────────────────────────────────────────────┐
│                   ANOMALY DETECTION ARCHITECTURE                       │
│                                                                        │
│  INPUT: fact_offers_clean DataFrame (654 rows)                         │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  detector.py — 5 independent detectors, each returns DataFrame │   │
│  │                                                                 │   │
│  │  1. detect_ctc_outliers()          METHOD: Z-score per family  │   │
│  │     Filter: ctc_status IN (KNOWN, RANGE)                       │   │
│  │     Group: by job_family (skip if group size < 5)              │   │
│  │     Flag: |z| > 2.5 std deviations from family mean           │   │
│  │     Severity: HIGH if |z| > 3.5, else MEDIUM                  │   │
│  │     Result: 17 flags                                           │   │
│  │                                                                 │   │
│  │  2. detect_stipend_exceeds_ctc()   METHOD: Rule-based join      │   │
│  │     Select: intern offers with known stipend                    │   │
│  │     Join: FTE offers from same company (same company_name)     │   │
│  │     Flag: stipend_monthly * 12 / 100000 > fte_ctc_lpa         │   │
│  │     Severity: HIGH (clear data error / unit mismatch)          │   │
│  │     Result: 1 flag                                             │   │
│  │                                                                 │   │
│  │  3. detect_implausible_student_count()  METHOD: IQR            │   │
│  │     Filter: students_status = KNOWN                            │   │
│  │     Compute: Q1, Q3, IQR = Q3-Q1                              │   │
│  │     Fence: upper = Q3 + 3.0 × IQR                             │   │
│  │     Flag: students_selected_num > upper_fence                  │   │
│  │     Severity: MEDIUM                                           │   │
│  │     Result: 28 flags                                           │   │
│  │                                                                 │   │
│  │  4. detect_no_compensation()       METHOD: Rule-based          │   │
│  │     Flag: ctc_status MISSING/UNKNOWN                           │   │
│  │           AND stipend_status MISSING/UNKNOWN                   │   │
│  │           AND has_ctc = False                                  │   │
│  │           AND has_stipend = False                              │   │
│  │     Severity: HIGH (no compensation signal at all)             │   │
│  │     Result: 0 flags (all structurally complete in this dataset)│   │
│  │                                                                 │   │
│  │  5. detect_rare_roles()            METHOD: Frequency threshold │   │
│  │     Flag: job_role_raw appears ≤ 1 time                        │   │
│  │           AND job_family = "Other" (not mapped)                │   │
│  │     Severity: LOW (possible typo or non-standard entry)        │   │
│  │     Result: 54 flags                                           │   │
│  └──────────────────────────────────┬──────────────────────────────┘  │
│                                     │                                   │
│                                     ▼                                   │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  detect_all() — orchestrator                                   │   │
│  │    pd.concat([det1, det2, det3, det4, det5])                   │   │
│  │    .drop_duplicates(subset=["offer_id", "anomaly_type"])       │   │
│  │    → 100 rows × [offer_id, anomaly_type, anomaly_detail,      │   │
│  │                    severity]                                    │   │
│  └──────────────────────────────────┬──────────────────────────────┘  │
│                                     │                                   │
│                                     ▼                                   │
│  build_anomalies.py                                                     │
│    → INSERT anomaly_flags TABLE into DuckDB                            │
│    → CREATE OR REPLACE VIEW vw_anomalies (joined with fact_offers)     │
│    → save data/quality/anomaly_summary.json                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Metrics Layer Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       METRICS LAYER ARCHITECTURE                            │
│                                                                             │
│  DEFINITION LAYER                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  metrics/definitions/                                                │  │
│  │    compensation.yaml  (8 metrics)                                   │  │
│  │    roles.yaml         (6 metrics)                                   │  │
│  │    branches.yaml      (5 metrics)                                   │  │
│  │    eligibility.yaml   (6 metrics)                                   │  │
│  │                                                                      │  │
│  │  Each entry:                                                         │  │
│  │  ┌─────────────────────────────────────────────────┐               │  │
│  │  │  name: high_package_rate                        │               │  │
│  │  │  label: "High Package Rate"                     │               │  │
│  │  │  description: "% of known-CTC offers >= 10 LPA"│               │  │
│  │  │  sql: |                                         │               │  │
│  │  │    SELECT ROUND(...) AS high_package_pct ...    │               │  │
│  │  │  version: "1.0"                                 │               │  │
│  │  │  owner: "Naman"                                 │               │  │
│  │  │  tags: [compensation, kpi]                      │               │  │
│  │  └─────────────────────────────────────────────────┘               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                │                                                             │
│                │  load_registry(path)                                        │
│                ▼                                                             │
│  REGISTRY LAYER                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  MetricDefinition (frozen dataclass)                                │  │
│  │    name, label, description, sql, version, owner, tags, category   │  │
│  │    frozen=True → immutable, hashable                                │  │
│  │                                                                      │  │
│  │  MetricRegistry                                                     │  │
│  │    _metrics: dict[str, MetricDefinition]                           │  │
│  │                                                                      │  │
│  │    .get(name) → MetricDefinition  (raises KeyError if not found)  │  │
│  │    .all() → list[MetricDefinition]                                 │  │
│  │    .by_tag(tag) → list[MetricDefinition]                           │  │
│  │    .by_category(cat) → list[MetricDefinition]                      │  │
│  │    .names() → sorted list[str]                                     │  │
│  │    len(registry) → 24                                              │  │
│  │    "name" in registry → bool                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                │                                                             │
│                │  MetricExecutor(registry)                                   │
│                ▼                                                             │
│  EXECUTION LAYER                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  MetricExecutor                                                     │  │
│  │                                                                      │  │
│  │    .run("metric_name") → pd.DataFrame                              │  │
│  │      registry.get(name)                                             │  │
│  │      → connect(DB_PATH, read_only=True)                            │  │
│  │      → con.execute(metric.sql).df()                                │  │
│  │      → con.close()                                                  │  │
│  │      → return DataFrame                                             │  │
│  │                                                                      │  │
│  │    .run_definition(MetricDefinition) → pd.DataFrame                │  │
│  │    .run_all() → dict[str, DataFrame]  (with error handling)        │  │
│  │    .run_by_tag(tag) → dict[str, DataFrame]                         │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                │                                                             │
│                │  Consumers                                                  │
│                ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Streamlit Query Console  →  executor.run(selected_metric_name)    │  │
│  │  LangGraph Agent Tools    →  lookup_metrics(tag) → agent context   │  │
│  │  Future BI/Notebook       →  executor.run_by_tag("kpi")            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. LangGraph Agent State Machine

### 8A. Graph Structure

```
                    ┌──────────────────────────────────────────────────────┐
                    │                   AgentState (TypedDict)             │
                    │                                                       │
                    │  question         str      original user question     │
                    │  sub_questions    list[str] 1-3 from planner         │
                    │  generated_sqls   list[str] one per sub-question     │
                    │  results          list[dict] execute_sql() outputs   │
                    │  answer           str      final natural language     │
                    │  sql_trace        list[str] for UI display           │
                    │  routing          str      "replan" | "synthesize"   │
                    │  replanned        bool     prevents infinite loop     │
                    │  error            str|None exception message         │
                    └──────────────────────────────────────────────────────┘

           ENTRY POINT
               │
               ▼
    ┌──────────────────────┐
    │    PLANNER NODE      │
    │                      │
    │  Claude API call     │  prompt: PLANNER_SYSTEM + schema context
    │  system: PLANNER     │  user: question
    │                      │  If replanned=True: + REPLAN_SUFFIX
    │  → sub_questions     │  max_tokens: 256
    │    (JSON array)      │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │  SQL GENERATOR NODE  │
    │                      │  For each sub_question:
    │  Claude API call     │    prompt: SQL_GENERATOR_SYSTEM + schema
    │  system: SQL_GEN     │    user: "Sub-question: {sq}"
    │                      │    max_tokens: 512
    │  → generated_sqls    │    strip trailing semicolons
    │    (one per sub-q)   │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │   EXECUTOR NODE      │
    │                      │  For each generated_sql:
    │  execute_sql(sql)    │    validate_sql() — block write keywords
    │                      │    open read_only DuckDB connection
    │  → results           │    run in daemon thread
    │    (list of dicts)   │    join with 10s timeout
    │  → sql_trace         │    return {sql, data, columns, row_count, error}
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │   VALIDATOR NODE     │
    │                      │
    │  Check: all results  │    all_empty = all(row_count==0 and no error)
    │  empty AND not yet   │    should_replan = all_empty AND NOT replanned
    │  replanned?          │
    │                      │
    │  Sets state:         │
    │   routing = "replan" │
    │   OR "synthesize"    │
    │   replanned = True   │
    └──────────┬───────────┘
               │
       ┌───────┴───────────┐
       │  CONDITIONAL EDGE │  _route_after_validation(state)
       │  reads state      │  returns state["routing"]
       └───────────────────┘
           │          │
     "replan"    "synthesize"
           │          │
           │          ▼
           │   ┌──────────────────────┐
           │   │  SYNTHESIZER NODE    │
           │   │                      │
           │   │  Claude API call     │
           │   │  system: SYNTH       │  Context: question + all sub-results
           │   │                      │  Cap: 10 rows per result (prompt size)
           │   │  → answer            │  max_tokens: 300
           │   │    (natural language)│  Rules: direct answer, <150 words
           │   └──────────┬───────────┘
           │              │
           │              ▼
           │            END
           │
           └──── back to PLANNER (once only — replanned=True prevents loop)
```

### 8B. Guardrail Layers

```
REQUEST        validate_sql()              DuckDB read_only         Thread timeout
ENTERS    →    keyword blocklist      →    connection flag      →   10 seconds
               [insert, update,            prevents physical
                delete, drop,              writes at DB level
                create, alter,
                truncate, replace]
               Returns error string
               if blocked — never
               reaches DuckDB
```

### 8C. AgentResult Schema

```python
@dataclass
class AgentResult:
    question: str           # original user question
    answer: str             # synthesizer output
    sub_questions: list     # what planner decomposed it into
    sql_trace: list         # exact SQL executed (shown in UI)
    results: list           # raw query results (dicts)
    replanned: bool         # whether a replan occurred
    success: bool           # False if exception was caught
    error: str | None       # exception message if success=False
```

---

## 9. Insight Generation Design

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     INSIGHT GENERATOR ARCHITECTURE                       │
│                                                                          │
│  8 independent generator functions, each:                                │
│    1. Opens read-only DuckDB connection                                  │
│    2. Runs a targeted analytical query                                   │
│    3. Computes derived metrics (%, ratios, correlations)                 │
│    4. Returns a typed InsightCard dataclass                              │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  InsightCard (dataclass)                                           │ │
│  │    insight_id:        "INS_001" – "INS_008"                       │ │
│  │    title:             one-sentence finding                         │ │
│  │    finding:           2-4 sentence narrative with exact numbers    │ │
│  │    supporting_metric: name of the metric layer metric used        │ │
│  │    confidence:        HIGH | MEDIUM | LOW                          │ │
│  │    data_caveat:       explicit limitation of the finding           │ │
│  │    numbers:           dict of key numeric values (for JSON export) │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  INS_001  CTC season decline        → STRFTIME month-level avg CTC      │
│  INS_002  PPO premium               → GROUP BY offer_type avg CTC       │
│  INS_003  Company size vs CTC       → Pearson correlation (pandas.corr) │
│  INS_004  Branch FTE/intern ratio   → vw_branch_summary aggregate       │
│  INS_005  No-CGPA by role family    → vw_role_summary no_cgpa_pct       │
│  INS_006  SWE CTC variance          → STDDEV/AVG = coeff. of variation  │
│  INS_007  Overall no-CGPA rate      → COUNT CASE WHEN (two conditions)  │
│  INS_008  Meesho outlier            → GROUP BY company HAVING n >= 2    │
│                                                                          │
│  Output:                                                                 │
│    data/insights/insight_report.json  → list of InsightCard.to_dict()   │
│    data/insights/insight_report.md   → Jinja2 markdown template         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Application Layer Design

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       STREAMLIT APP ARCHITECTURE                         │
│                                                                          │
│  src/app/components.py  — shared utilities                               │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  qdb(sql: str | None) → pd.DataFrame                              │ │
│  │    @st.cache_resource: DuckDB connection created once per session  │ │
│  │    connect(DB_PATH, read_only=True)                                │ │
│  │    if sql → execute and return df                                  │ │
│  │    if None → return connection object                              │ │
│  │                                                                     │ │
│  │  kpi_row(metrics: dict[str, Any]) → None                          │ │
│  │    renders N equal-width st.metric() columns                       │ │
│  │                                                                     │ │
│  │  page_header(title, subtitle) → None                              │ │
│  │                                                                     │ │
│  │  db_path_ok() → bool                                              │ │
│  │    returns False + st.error() if DB file missing                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Page Structure:                                                         │
│                                                                          │
│  main.py (Overview)                                                      │
│    KPI row (6 metrics via single SQL)                                    │
│    Quality scorecard (reads quality_report.json)                         │
│    Top 3 insight cards (reads insight_report.json)                       │
│    Offer type breakdown (vw_internship_summary)                          │
│                                                                          │
│  01_Compensation.py                                                      │
│    CTC histogram + boxplot (fact_offers WHERE ctc_status IN ...)         │
│    High-package company table (vw_high_package_offers)                  │
│    Stipend distribution (stipend_monthly_normalized)                    │
│    CTC trend over time (ctc_over_time metric)                           │
│                                                                          │
│  02_Roles.py                                                             │
│    Job family bar chart (role_family_distribution metric)                │
│    Avg CTC by role (avg_ctc_by_role_family metric)                      │
│    CTC variance scatter (role_ctc_variance metric)                      │
│    Top-20 raw roles table (top_roles_by_frequency metric)               │
│    No-CGPA rate by role (no_cgpa_by_role_family metric)                 │
│                                                                          │
│  03_Branches.py                                                          │
│    Branch group bar chart (branch_group_distribution metric)             │
│    FTE vs intern grouped bars (fte_vs_intern_by_branch metric)           │
│    Per-branch filterable table (branch_opportunity_count metric)         │
│    Avg CTC by branch (branch_avg_ctc metric)                            │
│                                                                          │
│  04_Companies.py                                                         │
│    Sidebar: search + filter + offer type checkbox                        │
│    Company table (vw_company_summary)                                   │
│    Top-20 by CTC / by volume charts                                     │
│    Single-company drilldown (WHERE company_name = selected)             │
│                                                                          │
│  05_Insights.py                                                          │
│    8 insight cards with confidence filter                                │
│    Expandable details (finding + caveat + numbers dict)                  │
│    Full markdown report (insight_report.md rendered via st.markdown)    │
│                                                                          │
│  06_Quality.py                                                           │
│    Quality scorecard table with color gauge                             │
│    History trend chart (quality_history.jsonl → line chart)             │
│    Anomaly summary pie + bar (vw_anomalies)                             │
│    Flagged records filterable table                                      │
│                                                                          │
│  07_Query_Console.py                                                     │
│    Tab 1: Metric selector (24 metrics dropdown → auto-chart)            │
│           MetricExecutor().run(selected_name)                           │
│           auto-detect chart type (bar/line/table)                       │
│    Tab 2: NL Query (text_input → agent.run(question))                   │
│           Show: answer, sub-questions, SQL trace, reasoning expander    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Component Dependency Map

```
                        ┌────────────────────┐
                        │   placements.json  │
                        └─────────┬──────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │  src/ingestion/            │
                    │    load_json.py            │
                    │    flatten_offers.py       │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │  src/cleaning/            │
                    │    parse_ctc.py           │
                    │    parse_stipend.py       │ ──────────────────────────┐
                    │    parse_dates.py         │                           │
                    │    normalize_roles.py     │                           │
                    │    normalize_branches.py  │                           │
                    │    extract_notes.py       │                           │
                    └─────────────┬─────────────┘                          │
                                  │                                         │
                    ┌─────────────▼─────────────┐                          │
                    │  src/quality/             │                           │
                    │    checks.py              │ ──────────────────────────┤
                    │    scorer.py              │                           │
                    │    report.py              │                           │
                    └─────────────┬─────────────┘                          │
                                  │                                         │
                    ┌─────────────▼─────────────┐                          │
                    │  src/modeling/            │                           │
                    │    build_tables.py        │ ──── placelytics.duckdb ─►│
                    └─────────────┬─────────────┘                          │
                                  │                                         │
               ┌──────────────────┼──────────────────┐                     │
               │                  │                   │                     │
    ┌──────────▼───┐   ┌──────────▼───┐  ┌──────────▼───┐               │
    │ src/metrics/ │   │ src/anomaly/ │  │ src/insights/│               │
    │   loader.py  │   │  detector.py │  │  generator.py│               │
    │   executor.py│   │  explainer.py│  │  templates.py│               │
    └──────┬───────┘   └──────┬───────┘  └──────┬───────┘               │
           │                  │                   │                        │
           └──────────────────┼───────────────────┘                        │
                              │                                             │
                    ┌─────────▼─────────────┐                             │
                    │  src/agent/           │                             │
                    │    graph.py           │◄────────────────────────────┘
                    │    nodes.py           │  (metrics layer via tools)
                    │    tools.py           │
                    │    prompts.py         │
                    └─────────┬─────────────┘
                              │
                    ┌─────────▼─────────────┐
                    │  src/app/             │
                    │    main.py            │
                    │    components.py      │
                    │    pages/*.py         │
                    └───────────────────────┘
```

---

## 12. Data Lineage — CTC Field Example

```
Source JSON field "ctc": "12,00,000-16,00,000"
                │
                ▼
  flatten_offers.py
    ctc_raw = "12,00,000-16,00,000"   ← preserved, never modified
                │
                ▼
  parse_ctc.py
    strip commas → "1200000-1600000"
    regex: (\d+)\s*[-–]\s*(\d+) matches → (1200000, 1600000)
    a ≠ b, both > 0 → RANGE case
    lo = 1200000, hi = 1600000
    ctc_lpa_min = 12.0
    ctc_lpa_max = 16.0
    ctc_lpa_normalized = 14.0  (midpoint)
    ctc_status = "RANGE"
                │
                ▼
  fact_offers_clean.parquet
    ctc_raw = "12,00,000-16,00,000"    ← original preserved
    ctc_lpa_min = 12.0
    ctc_lpa_max = 16.0
    ctc_lpa_normalized = 14.0
    ctc_status = "RANGE"
                │
                ▼
  DuckDB fact_offers table
    All 5 columns available for SQL queries
                │
                ├──▶ Anomaly detector: groups by job_family, z-score on ctc_lpa_normalized
                │
                ├──▶ high_package_rate metric: ctc_lpa_normalized >= 10 → TRUE
                │
                ├──▶ avg_ctc_by_branch metric: AVG(ctc_lpa_normalized) per branch
                │
                ├──▶ Streamlit chart: histogram on ctc_lpa_normalized
                │
                └──▶ Agent: SELECT avg_ctc from fact_offers → synthesizer answer
```

---

## 13. Key Design Decisions Summary

| Decision | Choice | Alternative Rejected | Reason |
|---|---|---|---|
| Raw field preservation | Parallel cleaned columns | Overwrite raw | Auditability + re-derivability |
| Branch storage | Bridge table (3,639 rows) | Array in fact row | Clean JOIN vs UNNEST in every query |
| Offer ID | SHA-256 deterministic | Sequential auto-increment | Stable across pipeline re-runs |
| Analytical engine | DuckDB persisted file | PostgreSQL / in-memory only | Zero server overhead, ships with repo |
| Storage format | Parquet | CSV / JSON | Typed, compressed, native DuckDB input |
| Metrics | YAML registry | Hardcoded SQL everywhere | Single source of truth for all consumers |
| Anomaly method | Z-score + IQR + rules | Isolation Forest / autoencoder | Explainability > accuracy for 654 rows |
| Agent graph | LangGraph StateGraph | LangChain SQL Agent | Explicit nodes = observable, testable |
| Agent write protection | Two layers (keyword check + read_only) | Single layer | Defense in depth |
| Replan loop prevention | `replanned: bool` state flag | Unlimited retries | Prevents infinite API cost |
| Quality tracking | Append-only JSONL history | Overwrite single file | Trend analysis across pipeline runs |
| Test coverage | 93% (main() excluded) | 100% | CLI entry points require full pipeline; logic fully covered |
