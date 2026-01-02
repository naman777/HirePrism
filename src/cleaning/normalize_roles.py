from __future__ import annotations

from rapidfuzz import process as fz_process

# (standardized_role, job_family)
# Key is the normalized (lowercased, stripped) raw role string.
ROLE_MAP: dict[str, tuple[str, str]] = {
    # ── Software Engineering ────────────────────────────────────────────────
    "software engineer": ("Software Engineer", "Software Engineering"),
    "software engineer 1": ("Software Engineer", "Software Engineering"),
    "software engineer - intern": ("Software Engineer Intern", "Software Engineering"),
    "software developer": ("Software Developer", "Software Engineering"),
    "software development": ("Software Developer", "Software Engineering"),
    "software development engineer": ("Software Development Engineer", "Software Engineering"),
    "software development engineer (sde)": ("SDE", "Software Engineering"),
    "software development intern": ("Software Developer Intern", "Software Engineering"),
    "software trainee": ("Software Trainee", "Software Engineering"),
    "software compiler verification": ("Software Engineer", "Software Engineering"),
    "sde": ("SDE", "Software Engineering"),
    "sde intern": ("SDE Intern", "Software Engineering"),
    "backend intern": ("Backend Engineer Intern", "Software Engineering"),
    "backend engineer": ("Backend Engineer", "Software Engineering"),
    "frontend intern": ("Frontend Engineer Intern", "Software Engineering"),
    "frontend engineer": ("Frontend Engineer", "Software Engineering"),
    "front end engineer": ("Frontend Engineer", "Software Engineering"),
    "full stack engineer": ("Full Stack Engineer", "Software Engineering"),
    "full stack development": ("Full Stack Engineer", "Software Engineering"),
    "full stack developer": ("Full Stack Engineer", "Software Engineering"),
    "mobile robotics - software (navigators)": ("Software Engineer", "Software Engineering"),
    "software (digital jedi)": ("Software Engineer", "Software Engineering"),
    "tdp software development associate": ("Software Developer", "Software Engineering"),
    "associate software development engineer": ("SDE", "Software Engineering"),
    "junior software engineer artificial intelligence & data science": (
        "Software Engineer",
        "Software Engineering",
    ),
    "product intern": ("Product Intern", "Software Engineering"),
    "product manager": ("Product Manager", "Software Engineering"),
    "devops engineer": ("DevOps Engineer", "Software Engineering"),
    "site reliability engineer": ("SRE", "Software Engineering"),
    "cloud engineer": ("Cloud Engineer", "Software Engineering"),
    "platform engineer": ("Platform Engineer", "Software Engineering"),
    "embedded systems engineer": ("Embedded Systems Engineer", "Software Engineering"),
    "firmware engineer": ("Firmware Engineer", "Software Engineering"),
    # ── Data Engineering ────────────────────────────────────────────────────
    "data engineer": ("Data Engineer", "Data Engineering"),
    "associate data engineer": ("Data Engineer", "Data Engineering"),
    "data engineering intern": ("Data Engineer Intern", "Data Engineering"),
    # ── Data Science / Analytics ────────────────────────────────────────────
    "data analyst": ("Data Analyst", "Data / Analytics"),
    "data analyst intern (remote)": ("Data Analyst Intern", "Data / Analytics"),
    "data analyst intern": ("Data Analyst Intern", "Data / Analytics"),
    "data science": ("Data Scientist", "Data / Analytics"),
    "data scientist": ("Data Scientist", "Data / Analytics"),
    "data science intern": ("Data Scientist Intern", "Data / Analytics"),
    "ai engineer": ("AI Engineer", "Data / Analytics"),
    "a.i. - m.l. intern": ("ML Engineer Intern", "Data / Analytics"),
    "ml engineer": ("ML Engineer", "Data / Analytics"),
    "machine learning engineer": ("ML Engineer", "Data / Analytics"),
    "deep learning engineer": ("ML Engineer", "Data / Analytics"),
    "research scientist": ("Research Scientist", "Data / Analytics"),
    "analyst (data science and new age technology)": ("Data Scientist", "Data / Analytics"),
    "apprenticeship program (data and ai-driven roles) 12 months": (
        "Data / AI Apprentice",
        "Data / Analytics",
    ),
    "junior software engineer artificial intelligence & data science": (
        "AI / Data Engineer",
        "Data / Analytics",
    ),
    # ── Business Analysis / Consulting ──────────────────────────────────────
    "business analyst": ("Business Analyst", "Business Analysis"),
    "business analyst intern": ("Business Analyst Intern", "Business Analysis"),
    "analyst / consultant": ("Analyst / Consultant", "Business Analysis"),
    "associate consultant": ("Associate Consultant", "Business Analysis"),
    "consultant": ("Consultant", "Business Analysis"),
    "management trainee": ("Management Trainee", "Business Analysis"),
    "trainee analyst": ("Trainee Analyst", "Business Analysis"),
    "analyst t&t - customer - sales and service": ("Business Analyst", "Business Analysis"),
    "digital specialist engineer (trainee)": ("Management Trainee", "Business Analysis"),
    # ── Engineering Trainee (GET / core manufacturing) ───────────────────────
    "get": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "graduate engineer trainee": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "graduate engineer trainee (get)": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "graduate engineer trainees (gets)": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "graduate engineer trainees": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "get/ trainee engineer": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "industrial engineer (graduate trainee)": ("Graduate Engineer Trainee", "Engineering Trainee"),
    "intern": ("Intern (Generic)", "Engineering Trainee"),
    "graduate engineer trainee (mechanical)": ("Graduate Engineer Trainee", "Engineering Trainee"),
    # ── Core / Mechanical / Electrical Engineering ───────────────────────────
    "mechanical engineer": ("Mechanical Engineer", "Core Engineering"),
    "electrical engineer": ("Electrical Engineer", "Core Engineering"),
    "civil engineer": ("Civil Engineer", "Core Engineering"),
    "chemical engineer": ("Chemical Engineer", "Core Engineering"),
    "production engineer": ("Production Engineer", "Core Engineering"),
    "design engineer": ("Design Engineer", "Core Engineering"),
    "process engineer": ("Process Engineer", "Core Engineering"),
    "quality engineer": ("Quality Engineer", "Core Engineering"),
    "r&d mechanical (design evangelist)": ("Mechanical Design Engineer", "Core Engineering"),
    "project (expediter)": ("Project Engineer", "Core Engineering"),
    # ── Research ────────────────────────────────────────────────────────────
    "research analyst": ("Research Analyst", "Research"),
    "patent analyst intern": ("Patent Analyst Intern", "Research"),
    "patent search analyst": ("Patent Search Analyst", "Research"),
    "patent search analyst ": ("Patent Search Analyst", "Research"),
    "patent research analyst": ("Patent Research Analyst", "Research"),
    # ── Finance ─────────────────────────────────────────────────────────────
    "financial analyst": ("Financial Analyst", "Finance"),
    "quantitative analyst": ("Quantitative Analyst", "Finance"),
    # ── Academic ────────────────────────────────────────────────────────────
    "assistant professor": ("Assistant Professor", "Academic"),
    "lecturer": ("Lecturer", "Academic"),
    # ── Unknown / missing ────────────────────────────────────────────────────
    "": ("Unknown", "Unknown"),
    "-": ("Unknown", "Unknown"),
    "not known": ("Unknown", "Unknown"),
    "not declared": ("Unknown", "Unknown"),
    "not announced": ("Unknown", "Unknown"),
}

_FUZZY_KEYS = list(ROLE_MAP.keys())
_FUZZY_THRESHOLD = 82  # minimum similarity score (0–100)


def normalize_role(raw: str | None) -> dict[str, str]:
    """Return standardized role name and job family for a raw jobRole string.

    Lookup order:
      1. Exact match (case-insensitive)
      2. Fuzzy match against ROLE_MAP keys via rapidfuzz (threshold 82)
      3. Keyword-based family detection
      4. Fallback: ("Other", "Other")
    """
    if raw is None:
        return {"role_standardized": "Unknown", "job_family": "Unknown"}

    key = str(raw).strip().lower()

    # 1. Exact match
    if key in ROLE_MAP:
        std, family = ROLE_MAP[key]
        return {"role_standardized": std, "job_family": family}

    # 2. Fuzzy match
    result = fz_process.extractOne(key, _FUZZY_KEYS, score_cutoff=_FUZZY_THRESHOLD)
    if result is not None:
        matched_key = result[0]
        std, family = ROLE_MAP[matched_key]
        return {"role_standardized": std, "job_family": family}

    # 3. Keyword fallback
    family = _keyword_family(key)
    return {"role_standardized": raw.strip(), "job_family": family}


def _keyword_family(lower: str) -> str:
    if any(t in lower for t in ("data engineer", "etl", "pipeline")):
        return "Data Engineering"
    if any(t in lower for t in ("data science", "data analyst", "machine learning", "ml ", "ai ", "deep learning", "analytics")):
        return "Data / Analytics"
    if any(t in lower for t in ("software", "sde", "backend", "frontend", "full stack", "fullstack", "devops", "cloud")):
        return "Software Engineering"
    if any(t in lower for t in ("business analyst", "consultant", "management trainee", "strategy")):
        return "Business Analysis"
    if any(t in lower for t in ("graduate engineer", "get", "trainee engineer", "industrial engineer")):
        return "Engineering Trainee"
    if any(t in lower for t in ("mechanical", "electrical", "civil", "chemical", "production", "process", "quality")):
        return "Core Engineering"
    if any(t in lower for t in ("research", "patent", "r&d")):
        return "Research"
    if any(t in lower for t in ("finance", "quant", "financial")):
        return "Finance"
    if any(t in lower for t in ("professor", "lecturer", "faculty")):
        return "Academic"
    return "Other"
