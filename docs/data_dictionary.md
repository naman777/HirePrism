# Data Dictionary — fact_offers_clean

`data/processed/fact_offers_clean.parquet` — 654 rows · 44 columns

Every raw field is preserved unchanged. Cleaned fields are added as parallel columns, never overwriting originals.

---

## Provenance / Identity

| Column | Type | Source | Description |
|---|---|---|---|
| `offer_id` | str | derived | 16-char hex SHA-256 of `record_id + offer_index`. Deterministic across pipeline runs. |
| `record_id` | str | `id` (parent) | Firestore document ID of the parent placement record. |
| `company_name` | str | `companyName` (parent) | Company name as stored in the source record. |

---

## Raw Ingestion Fields (unchanged)

| Column | Type | Source | Description |
|---|---|---|---|
| `notice_date_raw` | str | `noticeDate` (parent) | Original date string, e.g. `"20/04/2026"`. Format varies. |
| `created_at_seconds` | int64 | `_createdAt.seconds` (parent) | Unix epoch seconds from Firestore timestamp. |
| `created_at_nanoseconds` | int64 | `_createdAt.nanoseconds` (parent) | Sub-second precision component. Not used analytically. |
| `offer_type_raw` | str | `type` (offer) | Original offer type string, e.g. `"Intern"`, `"FTE"`, `"Intern + FTE"`. |
| `job_role_raw` | str | `jobRole` (offer) | Raw job title string. 118 distinct values before normalization. |
| `ctc_raw` | str | `ctc` (offer) | Original CTC string in any format — number, range, text, empty. |
| `has_ctc` | bool | `hasCTC` (offer) | Source flag indicating whether a CTC value was provided. |
| `ctc_note_raw` | str | `ctcNote` (offer) | Free-text note about the CTC, if any. |
| `stipend_raw` | str | `stipend` (offer) | Original stipend string. Mixed formats: monthly INR, lump sum, range, empty. |
| `has_stipend` | bool | `hasStipend` (offer) | Source flag indicating whether a stipend was provided. |
| `stipend_note_raw` | str | `stipendNote` (offer) | Free-text note about the stipend. |
| `students_selected_raw` | str | `studentsSelected` (offer) | Original selected-student count. Can be a number, text, or `"Process Pending"`. |
| `eligibility_cgpa_raw` | str | `eligibilityCgpa` (offer or parent) | Original CGPA threshold string. `"No CGPA Criteria"`, numeric, or blank. |
| `eligibility_note_raw` | str | `eligibilityNote` (offer) | Free-text eligibility note. |
| `branches_allowed_raw` | list[str] | `branchesAllowed` (offer or parent) | List of branch strings exactly as stored. May be an empty list. |
| `branches_note_raw` | str | `branchesNote` (offer) | Free-text branch note. |
| `branchwise_breakup_raw` | str | `branchwiseBreakup` (offer) | JSON-encoded dict of branch → seat count. Null when not provided. |
| `branches_from_parent` | bool | derived | `True` when `branches_allowed_raw` was inherited from the parent record (spillover). Affects 98 parent records. |
| `cgpa_from_parent` | bool | derived | `True` when `eligibility_cgpa_raw` was inherited from the parent record. |

---

## Cleaned Date Fields

| Column | Type | Cleaning logic | Notes |
|---|---|---|---|
| `notice_date` | datetime64[us] | `parse_dates.py` — tries `%d/%m/%Y`, `%Y-%m-%d`, and ISO variants | Null on failure. 100% parse rate on current data. |
| `created_at` | datetime64[ms, UTC] | Reconstructed from `created_at_seconds` + `created_at_nanoseconds` as UTC. | Used for trend analysis. |

---

## Cleaned Offer Type

| Column | Type | Possible values | Notes |
|---|---|---|---|
| `offer_type_standardized` | str | `FTE`, `INTERN`, `PPO`, `INTERN_TO_FTE`, `UNKNOWN` | Derived from `offer_type_raw` via a keyword map in `cleaning/parse_dates.py`. `PPO` = Pre-Placement Offer. |

---

## Cleaned CTC Fields

| Column | Type | Possible values / range | Notes |
|---|---|---|---|
| `ctc_lpa_min` | float64 | LPA value or NaN | Lower bound. Equals `ctc_lpa_normalized` for point values. Null for non-numeric statuses. |
| `ctc_lpa_max` | float64 | LPA value or NaN | Upper bound. Equals `ctc_lpa_normalized` for point values. |
| `ctc_lpa_normalized` | float64 | LPA value or NaN | Midpoint of range if range; full value otherwise. Raw integers ÷ 100,000 to convert to LPA. |
| `ctc_status` | str | `KNOWN`, `RANGE`, `MISSING`, `UNKNOWN`, `PENDING` | `KNOWN` = single numeric; `RANGE` = min/max pair; `MISSING` = empty string; `UNKNOWN` = "Not disclosed"; `PENDING` = "To be notified". |

CTC counts: 406 KNOWN · 135 RANGE · 68 MISSING · 24 UNKNOWN · 21 PENDING

---

## Cleaned Stipend Fields

| Column | Type | Possible values / range | Notes |
|---|---|---|---|
| `stipend_monthly_min` | float64 | INR / month or NaN | Lower bound of monthly stipend. |
| `stipend_monthly_max` | float64 | INR / month or NaN | Upper bound. Equals min for point values. |
| `stipend_monthly_normalized` | float64 | INR / month or NaN | Midpoint or single value. Lump-sum amounts are flagged but not duration-adjusted (duration not reliably captured). |
| `stipend_status` | str | `KNOWN`, `RANGE`, `MISSING`, `UNKNOWN`, `PENDING` | Same semantics as `ctc_status`. |

---

## Cleaned Eligibility Fields

| Column | Type | Possible values | Notes |
|---|---|---|---|
| `no_cgpa_criteria` | bool | True / False | `True` when source string is "No CGPA Criteria" or equivalent. Derived before numeric parsing. |
| `eligibility_cgpa_num` | float64 | 0.0–10.0 or NaN | Parsed numeric CGPA threshold. Null when no criteria or unparseable. |
| `eligibility_status` | str | `NUMERIC`, `NO_CRITERIA`, `MISSING`, `UNKNOWN` | `NUMERIC` = successfully parsed float; `NO_CRITERIA` = explicit waiver; `MISSING` = blank; `UNKNOWN` = non-numeric text. |

---

## Cleaned Student Count Fields

| Column | Type | Possible values | Notes |
|---|---|---|---|
| `students_selected_num` | float64 | positive integer or NaN | Parsed numeric count. |
| `students_status` | str | `KNOWN`, `PENDING`, `MISSING`, `UNKNOWN` | `PENDING` = "Process Pending"; `MISSING` = blank. |

---

## Normalized Role Fields

| Column | Type | Source | Notes |
|---|---|---|---|
| `role_standardized` | str | derived from `job_role_raw` | Canonical role name. Lookup order: exact map → fuzzy match (threshold 82) → keyword fallback → raw string. |
| `job_family` | str | derived | One of: `Software Engineering`, `Data Engineering`, `Data / Analytics`, `Business Analysis`, `Engineering Trainee`, `Core Engineering`, `Research`, `Finance`, `Academic`, `Unknown`, `Other`. |

---

## Extracted Note Fields

Extracted from `ctc_note_raw`, `stipend_note_raw`, `eligibility_note_raw`, `branches_note_raw` using regex rules in `cleaning/extract_notes.py`.

| Column | Type | Notes |
|---|---|---|
| `location_extracted` | str | City name if mentioned in any note field. Null otherwise. |
| `work_mode_extracted` | str | `Remote`, `Hybrid`, `Onsite`, or null. Case-insensitive keyword match. |
| `duration_months_extracted` | float64 | Internship duration in months if mentioned. Null otherwise. |
| `gross_ctc_signal` | bool | `True` if any note contains "gross" near a numeric CTC — flags that the headline CTC may be gross, not net. |
