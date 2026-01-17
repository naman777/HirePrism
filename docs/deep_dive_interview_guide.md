# Placelytics — Complete Deep Dive & Interview Guide

This document covers the full system design, every tech decision with alternatives, and comprehensive interview Q&A across all layers of the project.

---

## 1. What Is This Project, In One Paragraph

Placelytics is a placement analytics platform built over 654 real campus placement offers from 461 companies. The raw data is a single messy JSON file from a Firestore database — nested, inconsistently formatted, with CTC values in 6+ different formats and branch lists stored at the wrong schema level. The project flattens and cleans this data through an explicit pipeline, loads it into a DuckDB analytical model, defines 24 named business metrics in YAML, runs 5 statistical anomaly detectors, generates 8 data-backed insight cards, and surfaces everything through an 8-page Streamlit app with a LangGraph-powered multi-step natural language query layer.

---

## 2. Full System Design

### Data Flow (End to End)

```
placements.json (raw, 461 records)
         │
         ▼
[Phase 2: Ingestion]
  load_json.py ─── validates top-level structure, logs record count
  flatten_offers.py ─── explodes nested offers, assigns deterministic offer_id
         │
         ▼
raw_flat_offers.parquet (654 rows, 22 cols) ← RAW VALUES NEVER MODIFIED
         │
         ▼
[Phase 3: Cleaning Pipeline]
  parse_ctc.py ─── 6-case explicit rules → ctc_lpa_normalized, ctc_status
  parse_stipend.py ─── same pattern → stipend_monthly_normalized, stipend_status
  parse_dates.py ─── notice_date, created_at, offer_type_standardized
  normalize_roles.py ─── exact→fuzzy→keyword→fallback → role_standardized, job_family
  normalize_branches.py ─── canonical map → branch_standardized, branch_group
  extract_notes.py ─── regex rules → location, work_mode, duration, gross_ctc_signal
         │
         ▼
fact_offers_clean.parquet (654 rows, 44 cols)
bridge_offer_branches.parquet (3,639 rows)  ← junction table (offer × branch)
         │
         ▼
[Phase 4: Quality Scoring]
  checks.py ─── 6 check functions → per-dimension 0–1 scores
  scorer.py ─── aggregates → overall score 0.858 + flagged issues
  report.py ─── saves quality_report.json + appends quality_history.jsonl
         │
         ▼
[Phase 5: DuckDB Model]
  build_tables.py ─── CREATE TABLE from parquet (idempotent)
       ├── fact_offers (654)
       ├── bridge_offer_branches (3,639)
       ├── dim_role (118)  ─── derived: DISTINCT role_standardized, job_family
       ├── dim_branch (21) ─── derived: DISTINCT branch codes
       ├── dim_company (386) ─── aggregated per company
       └── 7 views: vw_high_package_offers, vw_role_summary, vw_branch_summary,
                    vw_company_summary, vw_internship_summary,
                    vw_no_cgpa_offers, vw_compensation_unknown
         │
         ▼
[Phase 6: Anomaly Detection]               [Phase 7: Metrics Layer]
  detector.py ─── 5 detectors                loader.py ─── YAML → MetricRegistry
  anomaly_flags table (100 rows)             executor.py ─── run(name) → DataFrame
  vw_anomalies view                          24 metrics across 4 categories
         │                                           │
         ▼                                           │
[Phase 8: Insight Report]                            │
  generator.py ─── 8 DuckDB queries                 │
  templates.py ─── Jinja2 renderer                  │
  insight_report.json + .md                         │
         │                                           │
         └─────────────────┬─────────────────────────┘
                           ▼
                  [Phase 9: LangGraph Agent]
                    Planner → SQL Generator → Executor
                           → Validator → Synthesizer
                           (replan loop, read-only guardrails)
                           │
                           ▼
                  [Phase 10: Streamlit App]
                    8 pages consuming all layers above
```

### Schema Design Decisions

**Why `fact_offers` + `bridge_offer_branches` instead of just `fact_offers`?**

Each offer has a `branchesAllowed` field that is a list — typically 3–15 branch codes. If that list were stored as a column in `fact_offers`, every branch-level aggregation would require `UNNEST()` or array manipulation. Instead, the bridge table follows standard dimensional modeling: one row per `(offer_id, branch_standardized)` pair. Branch analytics become clean `JOIN + GROUP BY`, not array functions.

**Why dim tables if they're mostly derived?**

`dim_role` (118 rows) and `dim_branch` (21 rows) are small, but they serve as the single source of truth for the controlled vocabulary — what role names and branch codes are valid. Any query that needs to enumerate all valid families can `SELECT * FROM dim_role` instead of doing a `DISTINCT` scan on a 654-row fact table. More importantly, they are the right modeling pattern — showing you understand the difference between a fact (an event that happened) and a dimension (the attributes used to filter and group).

---

## 3. Technology Decisions — Why This, Not That

### Python

**Chose:** Python 3.11+  
**Why:** The dominant language for data work. Pandas, DuckDB, LangGraph, and the Anthropic SDK all have first-class Python support. For an analytics portfolio project, using Python is itself a signal — it's what analysts and analytics engineers use in every real role.  
**Alternative considered:** R — better for statistical analysis but lacks the ecosystem for the agent layer and app framework. Not expected in data engineering interviews.

---

### Pandas

**Chose:** Pandas  
**Why:** The standard for Python data manipulation. Every data engineering interview will assume you know it. The cleaning pipeline (parse, normalize, join, filter) is naturally expressed as DataFrame transformations. Pandas also integrates directly with DuckDB — `con.execute(sql).df()` returns a DataFrame.  
**Alternative considered:** Polars — faster, better memory model, but less familiar to interviewers and less integrated with the rest of the ecosystem at the time of this build. Polars is a valid upgrade path but adds explanation overhead in interviews.

---

### DuckDB

**Chose:** DuckDB  
**Why four reasons:**
1. It reads Parquet natively — `SELECT * FROM read_parquet('path.parquet')` — no data loading ceremony.
2. It runs full analytical SQL (window functions, CTEs, `UNNEST`, aggregates) without a server process.
3. The DB file ships with the repo — zero setup for anyone cloning the project.
4. At 654 rows, every query returns in under 20ms.

**Alternative considered:** SQLite — no analytical functions (no window functions in older versions), no Parquet support. PostgreSQL/MySQL — require a running server, connection credentials, and a separate setup step. Completely unnecessary overhead for a single-file analytical dataset.

**Alternative considered:** Just using Pandas for all analytics — Pandas DataFrames are valid but SQL is the lingua franca of analytical work. Having a queryable DuckDB database means the metrics layer, the agent, and any future BI tool can all point at the same source of truth.

---

### Parquet

**Chose:** Parquet  
**Why:** Typed (no silent coercion of `"920000"` to int or leaving it as string), columnar (reads only the columns you need), compressed by default (~60% smaller than equivalent CSV), and the native input format for DuckDB.  
**Alternative considered:** CSV — no types, no compression, requires re-parsing on every read. JSON — verbose, slow to parse, no columnar access. Both are fine for small one-off files but inappropriate as the persistent storage layer for a pipeline.

---

### Streamlit

**Chose:** Streamlit  
**Why:** The fastest path from a Python data analysis to a shareable, polished web application. No HTML, no CSS, no JavaScript. The entire 8-page app is ~900 lines of Python. The reactive execution model (re-run on widget change) is perfect for a filter-and-explore analytics interface.  
**Alternative considered:** Dash (Plotly) — more control but significantly more boilerplate. Flask/FastAPI + frontend — appropriate for production apps but not for a portfolio demo. Jupyter notebooks — not shareable as an interactive app.

---

### LangGraph

**Chose:** LangGraph  
**Why:** The key requirement was a multi-step agent with explicit, observable nodes. LangGraph is a state graph — each node is a named Python function, each edge is explicit, and the routing logic is a separate function (`_route_after_validation`). The full execution trace (which sub-questions were generated, which SQL was executed, whether a replan occurred) is captured in the `AgentState` dict and shown to the user.

**Alternative considered:** LangChain SQL Agent — a black box. One `agent.run(question)` call. You cannot explain what happened between input and output to an interviewer. You cannot add a replan step without hacking internal chain internals.

**Alternative considered:** Raw Claude API with a loop — possible, but you'd be reimplementing what LangGraph provides (state management, conditional edges, graph compilation).

---

### Claude (Anthropic SDK)

**Chose:** Claude Sonnet 4.6  
**Why:** Three reasons specific to this use case: (1) Claude follows structured output instructions reliably — the Planner must return a JSON array, the SQL Generator must return bare SQL with no markdown fences. Cheaper models hallucinate format violations. (2) Claude's system prompt adherence is strong — the "read-only only" and "use these tables only" guardrails hold. (3) We're already in the Anthropic ecosystem; the SDK is clean and well-documented.

**Alternative considered:** GPT-4 — comparable quality but higher cost for the use case. GPT-3.5-class — frequent format violations in structured output tasks. Open-source models (Llama, Mistral) — require hosting, higher setup cost, and less reliable instruction following for complex SQL generation.

---

### YAML Metrics Layer

**Chose:** YAML + MetricRegistry + MetricExecutor  
**Why:** Each metric is defined once and reused across the dashboard, the agent's tool catalog, and any future consumers. The YAML format is readable by non-engineers. The registry provides a type-safe Python interface (`registry.get("high_package_rate")` returns a `MetricDefinition` dataclass, not a raw dict). Versioning and ownership are fields in the schema.

**What this replaces:** The alternative is hardcoding the same SQL in the Streamlit page, the agent prompt, and the notebook. When the query changes, you update 3+ places and inevitably miss one. This is the same problem that tools like dbt and Cube.dev solve at scale — the YAML layer is a lightweight version of that pattern.

**Alternative considered:** dbt — appropriate for production data teams managing hundreds of models. Overkill for a single-analyst portfolio project and adds a significant operational dependency. Cube.dev — requires a running service. The YAML approach is self-contained and explains the concept without the overhead.

---

### scipy.stats / IQR Anomaly Detection

**Chose:** Z-score per job family (scipy) + IQR (pandas quantile) + rule-based checks  
**Why:** Each method has a one-sentence explanation that holds up in an interview: "Z-score flags values that are more than 2.5 standard deviations from the mean within the same job family — so a 40 LPA software role isn't flagged globally, but a 200 LPA software role is." IQR for student counts avoids the Gaussian assumption. Rule-based for the logical checks (stipend > CTC) because statistical methods would miss those.

**Alternative considered:** PyOD (Isolation Forest, DBSCAN-based) — more powerful but completely unexplainable. An interviewer asks "why was this flagged?" and the answer is "the model decided" — that's not acceptable for a data trust use case. Statistical anomaly detection is about surfacing records for human review, not automatic classification. Explainability is the requirement.

---

### pytest (Testing)

**Chose:** pytest + pytest-cov  
**Why:** Standard. 93% total coverage. The 26 CTC test cases are the most valuable — they document every input format that exists in the real data and prove that the parser handles all of them correctly.

**Alternative considered:** unittest — more verbose, less readable. No serious alternative here.

---

## 4. Interview Questions — Complete Set

### Project Overview

**Q: Describe the project in 60 seconds.**

Placelytics is an end-to-end placement analytics platform. I took a real JSON dump from a campus placement system — 461 companies, 654 offers, messy and inconsistently formatted — and built a full data pipeline on top of it. The pipeline flattens nested JSON, parses 6 variants of CTC format, normalizes 118 raw role names into 11 job families, and runs a quality scoring system on every run. The cleaned data lives in a DuckDB analytical model with 24 named metrics in YAML. On top of that I built 5 statistical anomaly detectors, 8 real insight findings, a LangGraph multi-step NL query agent, and an 8-page Streamlit dashboard. 305 tests, 93% coverage.

---

**Q: What was the hardest part to build?**

The CTC parser. The field looks simple — it's a compensation number — but in practice it has 6 completely different formats: bare integers in rupees (920000), LPA strings ("10 LPA"), ranges ("12-16 LPA"), text deferrals ("To be notified"), disclosure refusals ("Not disclosed"), and empty strings. Each case needs different handling. Getting all 26 test cases to pass took most of a day. The second hardest was the branch spillover problem — 98 of the 461 parent records had branch data at the parent level instead of the offer level, which isn't where it should be. Handling that correctly required checking both the offer-level and parent-level fields during flattening and adding a provenance flag to track where each value came from.

---

**Q: How would you scale this to 5 million records?**

Three changes: (1) Replace Pandas cleaning with Polars or DuckDB itself for the cleaning step — both handle multi-million rows without OOM issues. (2) Replace the persisted `.duckdb` file with a partitioned Parquet lake on S3 and query it with DuckDB's S3 integration or Spark SQL. (3) Replace the in-process LangGraph agent with a server-deployed version behind an API. The DuckDB schema, the metrics YAML, and the agent graph design all stay identical — the storage and compute layer scales independently.

---

### Data Engineering Questions

**Q: Why do you have a bridge table? Explain it to me like I'm a junior.**

An offer can be open to 5 branches at once. If I store those 5 branch names as a list in the `fact_offers` row, then every time I want to ask "how many offers is ECE eligible for?" I have to scan every row and check if ECE is in the list — which requires array operations. Instead, I explode the list: one row for each offer-branch pair. So offer A with 5 branches becomes 5 rows in the bridge table. Now "how many offers is ECE eligible for?" is just `SELECT COUNT(*) FROM bridge_offer_branches WHERE branch_standardized = 'ECE'` — a simple index scan. That's the standard relational pattern for many-to-many relationships.

---

**Q: Why do you preserve raw values instead of overwriting them?**

Two reasons. First, correctness: if I find a bug in my CTC parser next week, I can fix it and re-derive `ctc_lpa_normalized` from `ctc_raw` without re-running the expensive ingestion step. If I'd overwritten, the original string is gone. Second, auditing: every analytical claim I make downstream is traceable to the exact original string. An interviewer or data reviewer can follow `ctc_lpa_normalized` → `ctc_raw` → the original JSON field.

---

**Q: What is an offer_id and why is it deterministic?**

It's a 16-character hex string derived from `SHA-256(record_id + ":" + offer_index)`. Deterministic means if I run the pipeline twice on the same input, I get the same `offer_id`. This matters for incremental processing — if I append new records and re-run, existing offer IDs don't change. It also means the anomaly_flags table, which references offer IDs, stays consistent across pipeline runs.

---

**Q: What's in the cleaning pipeline, specifically?**

Six modules in `src/cleaning/`:
1. `parse_ctc.py` — handles 6 format variants, returns `{min, max, normalized, status, raw}`
2. `parse_stipend.py` — same pattern for monthly stipend, handles INR amounts
3. `parse_dates.py` — parses notice date strings, creates typed `notice_date` column and standardizes `offer_type_standardized` to `FTE/INTERN/PPO/INTERN_TO_FTE/UNKNOWN`
4. `normalize_roles.py` — 3-step lookup: exact map (120 entries) → rapidfuzz fuzzy match (threshold 82) → keyword family detection → fallback to `Other`
5. `normalize_branches.py` — exact map to standard codes, builds the bridge table
6. `extract_notes.py` — regex rules over 4 note fields to extract location, work mode, duration, and gross CTC signal

---

**Q: What did the data profiling phase tell you?**

Three things that mattered most. One: the CTC field has 6 distinct formats — this meant the parser needed explicit cases, not a single regex. Two: 98 of 461 parent records had `branchesAllowed` at the parent level instead of inside each offer — a schema inconsistency I had to handle in flattening rather than cleaning. Three: 17.2% of CTC values are either missing or explicitly undisclosed — which means any compensation analysis must be framed as "of offers with known CTC" to be honest.

---

**Q: What is the `ctc_status` field and what are its possible values?**

It's the result of CTC parsing and has 5 values:
- `KNOWN` — single numeric value, fully parsed (406 offers, 62%)
- `RANGE` — min/max pair, midpoint used as normalized (135 offers, 21%)
- `MISSING` — empty string or null (68 offers, 10%)
- `UNKNOWN` — explicit "Not disclosed" or equivalent (24 offers, 4%)
- `PENDING` — "To be notified" or equivalent (21 offers, 3%)

`KNOWN` and `RANGE` are the analytically usable statuses. All compensation metrics filter to `ctc_status IN ('KNOWN', 'RANGE')`.

---

### Quality Scoring Questions

**Q: Tell me about your quality scoring system.**

Six automated checks, each returning a 0–1 score:
- `ctc_parseability`: proportion of offers with `ctc_status IN (KNOWN, RANGE)` = 0.827
- `stipend_parseability`: same for stipend = 0.699
- `branch_coverage`: proportion with at least one non-UNKNOWN branch = 0.992
- `role_standardization`: proportion with `job_family != 'Unknown'` = 0.960
- `date_validity`: proportion with a parsed `notice_date` = 1.000
- `cgpa_numeric_rate`: proportion with a numeric CGPA threshold = 0.670

The scorer aggregates them into an overall score (0.858) and flags any check below 0.75. Every run appends to a `quality_history.jsonl` file, so you can chart quality trend over pipeline iterations.

---

**Q: Why is the stipend parseability only 70%?**

Intentional. Most FTE (full-time employment) offers don't have a stipend — that's expected. A "missing" stipend for an FTE offer is not a data quality failure. The 70% score reflects this — roughly 30% of offers are pure FTE with no intern component. If I wanted a purer measure, I'd filter to intern-type offers only before running the check. I chose not to, because the global score gives a conservative view of the entire dataset.

---

**Q: How would you improve data quality over time?**

Three ways: (1) The `quality_history.jsonl` file already supports trend analysis — if a new batch of data degrades CTC parseability, the drop shows up immediately. (2) Add a pipeline gate — if overall score drops below 0.80, fail the pipeline run and alert before the new data reaches the app. (3) Feed the anomaly flags back to the data entry team — the most actionable use of this system is closing the loop with whoever creates the records.

---

### DuckDB & Analytical Model Questions

**Q: Why do you use views instead of creating more tables?**

Views are lazy — they compute at query time. For a 654-row dataset queried by at most a few concurrent Streamlit sessions, computation is instant (~5ms per view). The benefit of views is that they always reflect the current state of the underlying tables — if the pipeline re-runs and updates `fact_offers`, all views auto-refresh. Pre-computing them into tables would require explicit re-creation on every pipeline run.

---

**Q: What does `CREATE OR REPLACE TABLE` mean and why is it important?**

It drops and recreates the table if it already exists. This makes `build_tables.py` idempotent — you can run it 10 times on the same database and get the same result. Without `OR REPLACE`, the second run would fail with "table already exists." Idempotent pipeline steps are essential in data engineering — you want to be able to safely re-run any step after a fix.

---

**Q: How does DuckDB read Parquet files?**

DuckDB has a native Parquet reader — `SELECT * FROM read_parquet('path.parquet')` is a first-class DuckDB function that streams from the file with column pruning and predicate pushdown. In `build_tables.py`, `CREATE OR REPLACE TABLE fact_offers AS SELECT * FROM read_parquet(...)` materializes the Parquet scan into a DuckDB table. After that, all queries run purely against in-memory DuckDB structures.

---

**Q: What window functions did you use and why?**

In the `ctc_status_breakdown` metric: `ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)` — the `OVER ()` makes `SUM(COUNT(*))` the grand total, allowing you to compute a percentage of total in a single pass without a subquery. Similarly in several other metrics, `OVER (PARTITION BY job_family)` computes proportions within each family. Window functions are essential here because SQL aggregations otherwise collapse the granularity you need.

---

### Metrics Layer Questions

**Q: What problem does the metrics layer solve?**

Without it, the same SQL query appears in three places: the Streamlit chart, the agent's context prompt, and the analysis notebook. When the business definition changes ("high package is now 12 LPA, not 10 LPA"), you find the three different copies and update them — and inevitably miss one. The metrics layer is a single source of truth: the `high_package_rate` metric definition lives in `compensation.yaml` and is consumed by the executor everywhere. One change propagates everywhere.

---

**Q: Walk me through how a metric actually executes.**

1. `MetricExecutor(registry=load_registry()).run("high_package_rate")`
2. `load_registry()` scans `metrics/definitions/*.yaml`, parses each YAML file, and creates a `MetricDefinition` frozen dataclass for each entry.
3. `registry.get("high_package_rate")` returns the `MetricDefinition` with name, label, SQL, tags, version, owner.
4. `_execute(metric)` calls `connect(DB_PATH, read_only=True)`, runs `con.execute(metric.sql).df()`, closes the connection, returns the DataFrame.
5. Total time: ~10ms for this metric.

---

**Q: What's a `MetricDefinition` dataclass?**

A `frozen=True` dataclass with fields: `name`, `label`, `description`, `sql`, `version`, `owner`, `tags`, `category`. `frozen=True` means instances are immutable — once a metric is loaded from YAML, its SQL can't be accidentally overwritten in a running process. It also makes the object hashable, allowing it to be used as a dict key if needed.

---

### Anomaly Detection Questions

**Q: Walk me through the 5 anomaly detectors.**

1. **CTC z-score outliers** (`detect_ctc_outliers`): Groups offers by `job_family`. Within each group with ≥5 observations, computes scipy `zscore` on `ctc_lpa_normalized`. Flags anything with |z| > 2.5. Severity HIGH if |z| > 3.5.
2. **Stipend exceeds CTC** (`detect_stipend_exceeds_ctc`): Merges intern offers (with known stipend) against FTE offers from the same company. Flags any intern where `stipend_monthly * 12 / 100000 > fte_ctc`. These are either data entry errors or unit mismatches (rupees vs LPA).
3. **Implausible student count** (`detect_implausible_student_count`): IQR method on `students_selected_num`. Upper fence = Q3 + 3×IQR. Flags outliers as MEDIUM.
4. **No compensation** (`detect_no_compensation`): Rule-based. Both `ctc_status` and `stipend_status` are MISSING/UNKNOWN, AND `has_ctc = False` AND `has_stipend = False`. These are structurally incomplete records.
5. **Rare role names** (`detect_rare_roles`): Any raw role that appears exactly once AND was not mapped to a known job family (`job_family = 'Other'`). This pattern strongly suggests a typo or a non-standard entry.

---

**Q: Why z-score within job family rather than globally?**

A 40 LPA offer is not a global outlier (Software Engineering averages around 20 LPA and some offers reach 100+), but it might be an outlier within Core Engineering (which averages 8 LPA). Global z-score would miss the family-level signal. Computing z-score per family means "unusual compared to peers in the same role category" — a much more meaningful anomaly definition.

---

**Q: Why IQR for student count and not z-score?**

Student counts are not normally distributed. A few mass-recruiters (large companies hiring 20+ students) create a strongly right-skewed distribution. Z-score assumes a Gaussian distribution — on skewed data, the mean and standard deviation are pulled by the outliers you're trying to detect, making the method circular. IQR is non-parametric: it uses the median and quartiles, which are resistant to the skew.

---

### LangGraph Agent Questions

**Q: Explain the agent architecture in detail.**

The agent is a LangGraph `StateGraph` with 5 nodes and shared `AgentState`:

1. **Planner node**: Calls Claude with the schema context and user question. The prompt instructs Claude to decompose into 1–3 sub-questions, each answerable with one SQL query. Returns a JSON array. If this is a re-plan pass, the prompt appends a note explaining that the previous SQL returned empty results.

2. **SQL Generator node**: For each sub-question, calls Claude with the DuckDB schema and SQL generation rules. Returns bare SQL (no markdown fences, no semicolons). One LLM call per sub-question.

3. **Executor node**: Calls `execute_sql()` for each generated SQL. This function: (a) checks for write keywords — blocks if found; (b) opens a read-only DuckDB connection in a daemon thread; (c) joins with a 10-second timeout; (d) returns a structured dict with `{sql, data, columns, row_count, error}`.

4. **Validator node**: Checks if all results are empty. If empty AND the graph hasn't replanned yet, sets `routing = "replan"` and `replanned = True`. Otherwise sets `routing = "synthesize"`. This prevents infinite loops — the second pass always proceeds to synthesis.

5. **Synthesizer node**: Calls Claude with the original question plus all sub-question results. Writes a direct, data-grounded answer in under 150 words.

The graph has a conditional edge: `validator → planner` (if routing=replan) or `validator → synthesizer` (if routing=synthesize). The `synthesizer → END` edge terminates the graph.

---

**Q: How do you prevent the agent from modifying the database?**

Two independent layers:
1. **Connection-level**: `connect(db_path, read_only=True)` — DuckDB's read-only mode physically prevents any write operation at the connection level. This is enforced by DuckDB, not by our code.
2. **Application-level**: `validate_sql()` checks the SQL string for 8 write keywords (`insert`, `update`, `delete`, `drop`, `create`, `alter`, `truncate`, `replace`) before execution. This catches attempts before they even reach DuckDB.

Defense in depth: if the application-level check were somehow bypassed, the connection-level protection would still block the write.

---

**Q: What is `AgentState` and why is it a TypedDict?**

`AgentState` is the shared mutable dictionary that every node reads from and writes to. Using `TypedDict` (with `total=False` — all keys optional) gives: (1) static type checking via mypy/pyright — if a node tries to write a key that doesn't exist in the state schema, it's a type error; (2) documentation — the state schema is the interface contract between nodes; (3) LangGraph compatibility — LangGraph's `StateGraph` expects a TypedDict subclass for its state annotation.

---

**Q: Why did you cap at 3 sub-questions?**

Three reasons: (1) Each sub-question is one LLM call (SQL generator) plus one DuckDB query. At 3 sub-questions, the total round-trip is under 5 seconds. At 10, it would be 15+ seconds for a Streamlit interaction. (2) Most analytical questions about this dataset decompose into at most 2–3 atomic queries. (3) The synthesizer prompt caps context at 10 rows per result — adding more sub-questions doesn't add useful context, just cost.

---

**Q: What happens when the agent gets an adversarial input like "DROP TABLE fact_offers"?**

The input passes through the planner (which might generate something like "What happens if we drop the table?"). The SQL generator, following its prompt rules, might generate `DROP TABLE fact_offers`. Then `validate_sql()` checks `"drop"` in the lowercased SQL — it does find it, returns the error string `"Write operation 'drop' is not allowed."`. The executor gets back `{error: "Write operation...", row_count: 0}`. The validator sees 0 rows (with an error) — but the error flag prevents treating this as an empty-result case. The synthesizer receives the error and reports "the data does not contain enough information."

---

### Streamlit App Questions

**Q: How does the app connect to DuckDB?**

Through a cached helper in `src/app/components.py`:

```python
@st.cache_resource
def qdb() -> duckdb.DuckDBPyConnection:
    return connect(DB_PATH, read_only=True)
```

`@st.cache_resource` means the connection is created once and reused across all widget interactions in the session. Without caching, every widget change would create a new connection — that's fine at low concurrency but wasteful. `read_only=True` — the app can only read, never accidentally mutate the database.

---

**Q: Why 8 pages and how did you decide what goes where?**

The page structure follows user intent: someone comparing branches doesn't want company data mixed in. Each page answers a different question: Compensation (what does it pay?), Roles (what kinds of roles?), Branches (who can apply?), Companies (who's offering?), Insights (what did the data reveal?), Quality (how trustworthy is this?), Query Console (can I ask my own question?). The Overview page gives the KPI summary for someone who needs the 30-second version.

---

### General Software Engineering Questions

**Q: What design patterns did you use?**

- **Registry pattern**: `MetricRegistry` — a central catalog that other components look up by name. No component holds a direct reference to another; they look up through the registry.
- **Dataclass as value object**: `MetricDefinition` is a `frozen=True` dataclass — immutable, hashable, equality by value. The right tool for a read-only configuration object.
- **Explicit state machine**: The LangGraph graph is literally a state machine — a finite set of states (nodes), transitions (edges), and a shared state object.
- **Separation of concerns**: Each phase has its own module directory. The app layer imports from the modeling and metrics layers but knows nothing about how data was cleaned. The agent imports tools but not the app.
- **Idempotent pipeline**: Every `build_*` step uses `CREATE OR REPLACE` — safe to re-run at any point.

---

**Q: How would you add a new page to the Streamlit app?**

Create `src/app/pages/08_NewPage.py`. Streamlit discovers pages alphabetically from the `pages/` directory. The number prefix controls sort order. Import `qdb()` from `components.py` for the database connection, call `MetricExecutor().run("metric_name")` for pre-defined metrics, or write direct DuckDB SQL via `qdb().execute(sql).df()`.

---

**Q: How is the code organized for testability?**

Every module that does significant work has a pure functional core. `parse_ctc(raw_string) → dict` — no database, no filesystem, no side effects. `normalize_role(raw_string) → dict` — same. This makes unit testing trivial: provide input, assert output, no setup or teardown. The quality scorer takes a DataFrame and returns a dict — the test constructs a minimal DataFrame inline. The only tests that require a real database are the metrics executor tests, and those use the actual `data/processed/placelytics.duckdb` file (not a mock).

---

**Q: Why 93% coverage instead of 100%?**

The 7% gap is entirely in `main()` CLI entry point functions — the `if __name__ == "__main__": main()` blocks that exist in each module to allow running it directly from the terminal. These are script entry points, not application logic. Testing them would require mocking the filesystem or running a full end-to-end execution. The application logic they call (the functions they invoke) is fully covered. 93% on application logic is effectively 100% on the meaningful code.

---

### Behavioral / Process Questions

**Q: How did you approach building this? What was your process?**

I started with a written implementation plan before writing a single line of code. The plan forced me to think through the data shape, the schema design, and the technology choices before committing to them. Then I followed the phases strictly — profiling before flattening, flattening before cleaning, cleaning before modeling. This matters because the alternative — jumping to the dashboard and cleaning as you go — produces code that's impossible to test and impossible to explain.

---

**Q: What would you do differently?**

Two things. First, I'd add a schema validation step between ingestion and cleaning — a tool like `pandera` or `pydantic` that asserts column presence, types, and value ranges before the cleaning pipeline runs. Right now, a schema change in the source JSON would silently produce wrong outputs. Second, I'd add execution time logging to every pipeline step so I can see which step is slowest and optimize it first when the data volume grows.

---

**Q: How long did this take?**

Roughly 20 focused development days across 12 phases. The cleaning pipeline (Phase 3) took 3 days because the CTC parser alone required 26 test cases. The insight report (Phase 8) took 2 days — 1 full day just exploring the data and asking real questions before writing any code. The LangGraph agent (Phase 9) took 2–3 days because the prompt engineering for reliable SQL generation required multiple iterations.

---

**Q: What's the most defensible technical decision you made?**

Keeping raw values and adding parallel cleaned columns, never overwriting. This is the right call in data engineering regardless of dataset size. It means: every downstream assertion is traceable to its source; pipeline bugs are fixable without re-ingestion; data auditors can see exactly what was in the original source vs what the pipeline decided. The naming convention (`ctc_raw`, `ctc_lpa_normalized`, `ctc_status`) makes the lineage self-documenting in the column names.

---

## 5. Numbers to Have Ready

| Fact | Value |
|---|---|
| Raw records | 461 parent → 654 offers |
| Unique companies | 386 |
| Raw role variants | 118 → 11 job families |
| Raw branch codes | 21 → 6 groups |
| Bridge table rows | 3,639 |
| CTC parseability | 82.7% (406 KNOWN + 135 RANGE) |
| Overall quality score | 0.858 / 1.0 |
| Anomaly flags | 100 across 97 offers |
| Named metrics | 24 across 4 YAML files |
| Agent nodes | 5 (planner, sql_gen, executor, validator, synthesizer) |
| Agent guardrails | 4 (read-only DB, write keyword block, 10s timeout, replan-once) |
| App pages | 8 |
| Tests | 305 passing, 1 skipped |
| Coverage | 93% total |
| Biggest finding | CTC drops 74% peak to trough across placement season |
| Most anomalies by type | RARE_ROLE (54), implausible student count (28) |
