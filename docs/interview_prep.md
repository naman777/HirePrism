# Interview Prep — HirePrism

Q&A for explaining design decisions under technical interview pressure. Keep this updated as the project evolves.

---

## Data & Pipeline Questions

**Q: Walk me through the data.**

461 parent company records from a campus placement system, each containing 1–3 offer objects. After flattening, that's 654 offer rows. The data is messy JSON — CTC values appear in at least 6 different formats (bare integers like `920000`, `"10 LPA"`, ranges like `"12-16 LPA"`, and text signals like `"Not disclosed"`), branch fields carry 21 raw codes, and 98 parent records have spillover fields that shouldn't exist at that level.

---

**Q: Why Parquet instead of CSV?**

Parquet is typed — I don't lose int vs string distinctions. It's also compressed by default (the processed file is ~60% smaller than an equivalent CSV) and reads natively into DuckDB. For a pipeline that runs repeatedly, it also prevents silent type coercion bugs that CSV loads introduce.

---

**Q: Why did you keep raw values and add cleaned columns instead of overwriting?**

If a parsing rule is wrong, I can fix it and re-derive without re-ingesting. More importantly, auditors and interviewers can see exactly what the original data said and exactly what the pipeline decided. The convention I used — `ctc_raw`, `ctc_lpa_normalized`, `ctc_status` — makes the lineage explicit in the column names.

---

**Q: How did you handle CTC parsing?**

Explicit case-by-case rules, not a generic regex. The parser returns a structured dict with `min`, `max`, `normalized`, `status`, and `raw`. For ranges like `"12-16 LPA"`, `normalized` is the midpoint. For text signals, `status` is `PENDING`, `UNKNOWN`, or `MISSING` and the numeric fields are null. There are 26 test cases covering edge cases including raw integer rupees, LPA decimals, and nil strings.

---

**Q: What's the bridge table for?**

Each offer can be open to multiple branches — the source field is a list. Storing a list directly in `fact_offers` makes branch-level aggregations require array unnesting in every query. The `bridge_offer_branches` table is a standard junction: one row per offer-branch pair (3,639 rows from 654 offers). That means branch analytics are just a clean join, not a function call.

---

**Q: How did you handle the spillover fields at the parent record level?**

98 parent records had `branchesAllowed` and `eligibilityCgpa` at the parent level instead of the offer level — a data entry inconsistency in the source system. During flattening, if an offer has an empty branches list, I check the parent record and inherit from there, setting `branches_from_parent = True`. This is documented in `docs/assumptions.md` and flagged in the data dictionary. The flag lets downstream consumers exclude or separately analyze inherited values.

---

## Quality & Anomaly Questions

**Q: How did you measure data quality?**

Six automated checks, each returning a 0–1 completeness ratio: CTC parseability, stipend parseability, branch coverage, role standardization rate, date validity, and CGPA numeric rate. A scorer aggregates them into an overall score (current: 0.858) and flags any check below 0.75. Every pipeline run appends to a history JSONL file, so you can show a quality trend chart over iterations.

---

**Q: What anomalies did you detect?**

Five detector types: CTC z-score outliers per role family (z > 2.5), stipend higher than FTE CTC for the same company, implausibly high student counts (IQR method), offers with no compensation of any kind, and rare role names below a frequency threshold. The real data produced 100 flags across 97 offers. The most common type was rare role names (54 flags, LOW severity) and implausible student counts (28, MEDIUM).

---

**Q: Why Z-score and IQR instead of something more sophisticated?**

With 654 offers spread across 11 job families, the average group has ~60 rows. A neural autoencoder would be both over-fitted and unexplainable. Z-score on CTC per role family is a clean story: "I standardized within each family because a 40 LPA software role is not an anomaly even though 40 LPA is a statistical outlier overall." IQR for student counts avoids the Gaussian assumption that z-score requires. Both methods have defensible answers to "why did you flag this record?"

---

## Modeling & Metrics Questions

**Q: Why DuckDB?**

It reads Parquet files natively with no data loading step. It runs full analytical SQL (window functions, CTEs, lateral joins) without a server. At 654 rows with 3,639 in the bridge table, query times are under 20ms. For a portfolio project, the absence of a running database process is also a deployment advantage — the DB file ships with the repo.

---

**Q: What's the metrics layer?**

24 named metrics defined in YAML files, each with a name, label, description, SQL, version, owner, tags, and category. A `MetricRegistry` loads them into a catalog; a `MetricExecutor` takes a name and returns a DataFrame. The motivation: if the same metric appears in the dashboard, the agent, and a notebook, it should be defined once. Any SQL change propagates everywhere. That's what analytics engineers call a semantic layer — I built a lightweight version of it.

---

**Q: How would you add a new metric?**

Add an entry to the relevant YAML file in `metrics/definitions/`. The registry auto-discovers all `*.yaml` files in that directory. No code changes needed. The metric is immediately available in the Streamlit query console and the agent's tool catalog.

---

## Agent Questions

**Q: Why LangGraph instead of LangChain's SQL agent?**

LangChain's SQL agent is a black box — you can't see what happened between input and output. LangGraph is an explicit state graph: Planner → SQL Generator → Executor → Validator → Synthesizer. Each step is a named function. If the validator detects an empty result, there's a conditional edge back to the Planner for a single re-plan. Every node's output is visible in the reasoning trace shown to the user. That's the story: observable, auditable multi-step reasoning.

---

**Q: What guardrails did you put on the agent?**

Four: (1) read-only DuckDB connection — the connect function explicitly sets `read_only=True`; (2) write keyword blocking in the executor tool — any SQL containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, or `ALTER` is rejected before execution; (3) 10-second query timeout; (4) replan-once loop prevention — a flag in agent state prevents infinite replanning. The agent also always shows the generated SQL to the user.

---

**Q: What happens when the agent gets a question it can't answer?**

The Validator node checks whether the result is empty or structurally wrong. If so, it sets a `needs_replan` flag and routes back to the Planner with a note about what failed. The Planner generates an alternative decomposition. If the second attempt also fails, the Synthesizer returns a structured "insufficient data" response explaining why.

---

## Insight & Analysis Questions

**Q: What's the most interesting finding?**

The CTC drop across the placement season (INS_001). Average CTC falls 74% from the first window to the last. This means companies recruiting early are offering significantly better packages. For a student, the data says: engage in the first wave, not the last. The finding is counterintuitive because students often assume late-season offers are "catch-up" packages — the data shows the opposite.

---

**Q: How do you know PPO pays more?**

INS_002: I queried average CTC by `offer_type_standardized`. PPO offers average 2.38× the FTE average. The confidence is HIGH because the sample is clean (PPO offers all had parseable CTC values) and the magnitude is large enough to survive the ~18% CTC data loss from MISSING/UNKNOWN statuses.

---

**Q: What's the data caveat you'd flag for an executive?**

17.2% of offers have no parseable CTC (MISSING + UNKNOWN + PENDING). All compensation analyses are conditional on the 82.7% of offers with known CTC. If the missing CTC offers skew low (e.g., companies that don't disclose tend to pay less), then the headline averages overstate market compensation. I flag this caveat on every insight card that touches compensation.

---

## Process & Judgment Questions

**Q: What would you do differently with more data?**

With 18k records (the original claim before seeing the actual file), I'd add time-series trend analysis by cohort year. With the current 654, the trend analysis is limited to the window within a single season. More data would also make the anomaly detection more reliable — z-score on groups of 60 is noisier than on groups of 600.

**Q: How long did this take?**

~20 focused development days across 12 phases, following a pre-written implementation plan. The hardest phase was the cleaning pipeline (Phase 3) — the CTC parser alone required 26 test cases to cover all real-data variants. The most valuable phase was the insight report (Phase 8) — that's the phase that turns a pipeline into an analysis.
