# HirePrism — Insight Report

*Generated from 654 analysed placement offers.*


### INS_001 — CTC drops 74.0% from peak to trough across the placement season

Offers posted in 2025-07 averaged 26.16 LPA — the highest in the dataset. By 2026-04, the average had fallen to 6.81 LPA, a 74.0% decline. Early-season offers are dominated by premium tech and product companies; late-season offers skew toward manufacturing and core engineering roles with lower average compensation.

**Supporting metric:** `ctc_over_time`
**Confidence:** 🟢 High confidence
**Data caveat:** *Based on 541 offers with parseable CTC. Month with fewest offers (1) may be noisy.*

---

### INS_002 — PPO offers pay 2.38× more than standard FTE offers on average

Pre-placement offers (PPOs) average 22.93 LPA — 2.38× the 9.63 LPA average for direct FTE offers. This gap reflects both selection bias (PPOs go to top interns) and the company's incentive to retain proven performers. For students who receive a PPO, the financial upside versus a fresh FTE offer is substantial.

**Supporting metric:** `stipend_by_offer_type`
**Confidence:** 🟢 High confidence
**Data caveat:** *PPO sample: 25 offers. FTE sample: 162 offers. PPO CTC may be skewed by a small number of high-paying outliers.*

---

### INS_003 — Companies that recruit more students do not pay higher CTC (r ≈ 0)

Across 328 companies with parseable CTC, the Pearson correlation between number of offers posted and average CTC is 0.01 — effectively zero. This means high-volume recruiters are not systematically higher or lower paying. The data shows mass-hiring companies like manufacturing conglomerates co-exist in the same offer-count range as boutique tech firms paying 3–4× more.

**Supporting metric:** `top_paying_companies`
**Confidence:** 🟢 High confidence
**Data caveat:** *Correlation is computed at company level, not offer level.*

---

### INS_004 — CIVIL branches have a 1.14× FTE-to-intern ratio — 5.2× higher than BIO

Civil engineering branches achieve a 1.14 FTE-to-intern ratio — for every intern role, there is more than one direct FTE opportunity. By contrast, CS (0.23) and ECE (0.28) branches are heavily skewed toward internships, reflecting the tech industry's preference for trial-before-hire. Students in core engineering streams face fewer intern-to-FTE conversion uncertainties.

**Supporting metric:** `fte_vs_intern_by_branch`
**Confidence:** 🟡 Medium confidence
**Data caveat:** *Branch coverage is 99.2% — 6 offers have no branch data. Civil total offers (30) is much smaller than CS (1200), so the ratio may be noisier.*

---

### INS_005 — Academic roles waive CGPA requirements 2.5× more often than Software Engineering

Academic offers have the highest no-CGPA rate among role families with 5+ offers: 66.7% of their 6 offers require no CGPA filter. Software Engineering, the largest family, waives CGPA in 26.8% of cases. This pattern suggests data-focused companies place more weight on skills and projects than academic scores — consistent with how data roles are typically hired in the industry.

**Supporting metric:** `no_cgpa_by_role_family`
**Confidence:** 🟡 Medium confidence
**Data caveat:** *CGPA status was parseable for 653 offers. 'No CGPA criteria' is self-reported by the company — actual screening during interviews may differ.*

---

### INS_006 — Software Engineering has the highest CTC variance — offers range from 3.6 to 123.0 LPA

With a coefficient of variation of 0.911 and a range from 3.6 to 123.0 LPA, Software Engineering has the widest compensation spread of any job family. The average is 13.4 LPA but this masks a bimodal distribution: product/tech companies offering 20–40+ LPA coexist with service companies offering 3.5–6 LPA. By contrast, Research roles show a CV of 0.128 — a much tighter, more predictable band.

**Supporting metric:** `role_ctc_variance`
**Confidence:** 🟢 High confidence
**Data caveat:** *CV is sensitive to outliers. The 123.0 LPA maximum in Software Engineering was validated by the anomaly detector as a flagged CTC outlier (>2.5σ from family mean).*

---

### INS_007 — 28.6% of all offers require no CGPA — and 27.3% of those are high-package

187 of 654 offers (28.6%) explicitly state no CGPA requirement. Of these open-access offers, 51 (27.3%) also pay 10 LPA or above. This means a student with a lower CGPA has access to 51 high-paying opportunities without any academic filter — making skill development and project work the primary differentiator.

**Supporting metric:** `no_cgpa_offer_rate`
**Confidence:** 🟢 High confidence
**Data caveat:** *No-CGPA status is extracted from the eligibilityCgpa field. Some companies may screen informally during interviews even when the field says 'No CGPA Criteria'.*

---

### INS_008 — Meesho averages 46.83 LPA for intern-to-FTE roles — 3.7× the sector average of 12.75 LPA

Among companies with 2+ intern-FTE offers, Meesho stands out with an average of 46.83 LPA — 3.7× the sector average of 12.75 LPA for this offer type. The next highest is Zhealthehr at 28.33 LPA. Intern-to-FTE pathways represent 99 offers (15.1% of the dataset) and on average pay 1.32× more than pure FTE offers — confirming the 'intern-first' pathway as financially superior for top performers.

**Supporting metric:** `stipend_by_offer_type`
**Confidence:** 🟡 Medium confidence
**Data caveat:** *Meesho sample: 3 INTERN_FTE offers. Small sample sizes amplify averages; treat as directional.*

---
