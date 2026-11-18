"""Intelligent Normalization & Categorization Engine.

Normalizes raw crawled job and scholarship texts into standardized, production-grade
filters:
- Experience Level: 'Junior / Entry', 'Mid-Level', 'Senior / Lead'
- Job Category: 'IT & Software', 'Data & AI', 'Finance & Accounting', 'Engineering',
                'Healthcare & Medical', 'Marketing & Sales', 'Operations & HR', 'General / Other'
- Job Type: 'Full-time', 'Contract / Freelance', 'Internship', 'Part-time', 'Remote'
- Scholarship Country: 'Ethiopia', 'USA', 'UK', 'Germany', 'Canada', 'Australia', 'Europe', 'Asia', 'Global'
- Academic Level: 'Undergraduate', "Master's", 'PhD / Doctoral', 'Fellowship / Postdoc', 'All Levels'
- Funding Type: 'Fully Funded', 'Partial / Tuition', 'Research Grant / Stipend'
"""

import re
from typing import Optional


# =============================================================================
# JOB NORMALIZERS
# =============================================================================

JUNIOR_PATTERNS = [
    r"\bjunior\b",
    r"\bentry\s*level\b",
    r"\bfresh\s*grad(uate)?s?\b",
    r"\bintern(ship)?\b",
    r"\btrainee\b",
    r"\bapprentice\b",
    r"\bassociate\b",
    r"\b0[-–]1\s*(year|yr)s?\b",
    r"\b0[-–]2\s*(year|yr)s?\b",
    r"\bno\s+experience\b",
    r"\blevel\s*1\b",
    r"\bjr\.?\b",
]

SENIOR_PATTERNS = [
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\blead\b",
    r"\bprincipal\b",
    r"\bstaff\b",
    r"\bhead\s+of\b",
    r"\bdirector\b",
    r"\barchitect\b",
    r"\bmanager\b",
    r"\bchief\b",
    r"\bvp\b",
    r"\bexecutive\b",
    r"\b5\+\s*(year|yr)s?\b",
    r"\b6\+\s*(year|yr)s?\b",
    r"\b7\+\s*(year|yr)s?\b",
    r"\b8\+\s*(year|yr)s?\b",
    r"\b10\+\s*(year|yr)s?\b",
    r"\bexpert\b",
]

MID_PATTERNS = [
    r"\bmid[- ]?level\b",
    r"\bintermediate\b",
    r"\b2[-–]4\s*(year|yr)s?\b",
    r"\b2[-–]5\s*(year|yr)s?\b",
    r"\b3[-–]5\s*(year|yr)s?\b",
    r"\blevel\s*2\b",
    r"\bofficer\b",
    r"\bspecialist\b",
]


def normalize_experience_level(title: str, text: str = "") -> str:
    """Classifies job seniority into 'Junior / Entry', 'Mid-Level', or 'Senior / Lead'."""
    combined = f"{title} {text}".lower()

    # 1. Check title first (highest precision)
    title_lower = title.lower()
    for pat in JUNIOR_PATTERNS:
        if re.search(pat, title_lower):
            return "Junior / Entry"
    for pat in SENIOR_PATTERNS:
        if re.search(pat, title_lower):
            return "Senior / Lead"
    for pat in MID_PATTERNS:
        if re.search(pat, title_lower):
            return "Mid-Level"

    # 2. Check full text context
    for pat in JUNIOR_PATTERNS:
        if re.search(pat, combined):
            return "Junior / Entry"
    for pat in SENIOR_PATTERNS:
        if re.search(pat, combined):
            return "Senior / Lead"
    for pat in MID_PATTERNS:
        if re.search(pat, combined):
            return "Mid-Level"

    return "Mid-Level"


def normalize_job_category(title: str, text: str = "") -> str:
    """Classifies job into standard vertical categories with strict domain prioritization."""
    combined = f"{title} {text}".lower()

    # 1. Healthcare & Medical (Check first so medical/health roles aren't misclassified)
    if re.search(
        r"\b(doctor|physician|nurse|nursing|pharmacist|pharmacy|clinical|medical|medicine|hospital|laboratory|"
        r"radiologist|midwife|health officer|public health|epidemiologist|biomedical|therapist|surgeon|dental|dentist)\b",
        combined,
    ):
        return "Healthcare & Medical"

    # 2. Engineering & Architecture (Check before IT so Civil/Electrical/Mechanical engineers aren't labeled as software)
    if re.search(
        r"\b(civil|structural|mechanical|electrical|electronics|electromechanical|architect|architecture|"
        r"construction|surveyor|surveying|draftsman|drafting|site engineer|autocad|solidworks|hvac|"
        r"plumbing|sanitary engineer|irrigation|hydrology|geotechnical|piping|plant engineer)\b",
        combined,
    ):
        return "Engineering"

    # 3. Finance & Accounting
    if re.search(
        r"\b(accountant|accounting|finance|financial|auditor|audit|banker|banking|cashier|"
        r"credit|treasury|tax|payroll|economist|economics|cpa|accas?|bookkeeper|cost accounting)\b",
        combined,
    ):
        return "Finance & Accounting"

    # 4. Journalism, Media & Communications
    if re.search(
        r"\b(journalist|journalism|reporter|news|editorial|editor|copy editor|broadcast|"
        r"media officer|press|communications officer|correspondent)\b",
        combined,
    ):
        return "Journalism & Media"

    # 5. Data & AI
    if re.search(
        r"\b(data scientist|data analyst|machine learning|deep learning|ai engineer|mlops|"
        r"artificial intelligence|bi analyst|business intelligence|data engineer|database|"
        r"big data|nlp|computer vision)\b",
        combined,
    ):
        return "Data & AI"

    # 6. IT & Software (Specific tech patterns, avoiding broad generic 'engineer')
    if re.search(
        r"\b(developer|software|frontend|backend|fullstack|full-stack|devops|cloud|"
        r"mobile|flutter|react|python|java|javascript|typescript|golang|rust|node|c\+\+|c#|"
        r"qa|tester|system admin|sysadmin|network|cybersecurity|security|ict|it specialist|"
        r"web designer|ui/ux|ui designer|ux designer|product designer|tech support|webmaster|"
        r"software engineer|systems engineer|network engineer|cloud engineer|devops engineer)\b",
        combined,
    ):
        return "IT & Software"

    # 7. Marketing & Sales
    if re.search(
        r"\b(marketing|sales|business development|seo|sem|social media|copywriter|content creator|"
        r"account executive|brand manager|public relations|pr officer)\b",
        combined,
    ):
        return "Marketing & Sales"

    # 8. HR & Operations
    if re.search(
        r"\b(human resources|hr|recruiter|talent acquisition|operations manager|logistics|"
        r"supply chain|procurement|administrative|admin assistant|secretary|receptionist)\b",
        combined,
    ):
        return "Operations & HR"

    return "General / Other"


def normalize_job_type(title: str, text: str = "", is_remote: bool = False) -> str:
    """Classifies job into 'Full-time', 'Contract / Freelance', 'Internship', 'Part-time', or 'Remote'."""
    combined = f"{title} {text}".lower()

    if re.search(r"\b(intern|internship|trainee|apprentice)\b", combined):
        return "Internship"
    if re.search(r"\b(contract|freelance|gig|consultant|temporary|short[- ]?term)\b", combined):
        return "Contract / Freelance"
    if re.search(r"\b(part[- ]?time|half[- ]?day)\b", combined):
        return "Part-time"
    # Inherently in-person roles (clinical, surgical, nursing, site construction, athletics) cannot be remote
    if re.search(r"\b(doctor|physician|nurse|nursing|surgeon|pharmacist|pharmacy|clinical|hospital|site engineer|construction|surveyor|athletic coach)\b", combined):
        return "Full-time"
    if is_remote or "remote" in combined or "work from home" in combined:
        return "Remote"

    return "Full-time"


# =============================================================================
# SCHOLARSHIP NORMALIZERS
# =============================================================================

def normalize_country(title: str, text: str = "") -> str:
    """Extracts standardized target or host country/region for scholarships."""
    combined = f"{title} {text}".lower()

    if re.search(r"\b(ethiopia|ethiopian|addis ababa)\b", combined):
        return "Ethiopia"
    if re.search(r"\b(united states|usa|u\.s\.a?|america|american|caltech|harvard|mit|fulbright)\b", combined):
        return "USA"
    if re.search(r"\b(united kingdom|uk|u\.k\.|britain|british|england|oxford|cambridge|chevening|commonwealth)\b", combined):
        return "UK"
    if re.search(r"\b(germany|german|daad|deutschland|berlin|munich)\b", combined):
        return "Germany"
    if re.search(r"\b(canada|canadian|toronto|mcgill|ubc)\b", combined):
        return "Canada"
    if re.search(r"\b(australia|australian|melbourne|sydney|australia awards)\b", combined):
        return "Australia"
    if re.search(r"\b(erasmus|erasmus mundus|europe|european|france|french|netherlands|holland|dutch|sweden|swedish|switzerland|swiss|italy|italian|spain|spanish|belgium|austria|norway|finland|denmark|crg)\b", combined):
        return "Europe"
    if re.search(r"\b(japan|japanese|mext|china|chinese|csc|south korea|korean|gks|kgsp|singapore)\b", combined):
        return "Asia"

    return "Global"


def normalize_academic_level(title: str, text: str = "") -> str:
    """Classifies academic degree level: 'Undergraduate', 'Master's', 'PhD / Doctoral', 'Fellowship / Postdoc'."""
    combined = f"{title} {text}".lower()

    # PhD / Doctoral
    if re.search(r"\b(phd|ph\.d|doctorate|doctoral|dphil)\b", combined):
        return "PhD / Doctoral"

    # Master's
    if re.search(r"\b(master|masters|master's|msc|m\.sc|ma\b|m\.a\.|postgraduate|post-graduate|mba|llm)\b", combined):
        return "Master's"

    # Fellowship / Postdoc / Research
    if re.search(r"\b(fellowship|postdoctoral|postdoc|post-doc|researcher in residence|visiting scholar|research grant)\b", combined):
        return "Fellowship / Postdoc"

    # Undergraduate / Bachelor's
    if re.search(r"\b(undergraduate|bachelor|bachelors|bachelor's|bsc|b\.sc|ba\b|freshman|college)\b", combined):
        return "Undergraduate"

    return "All Levels"


def normalize_funding_type(title: str, text: str = "") -> str:
    """Classifies funding level: 'Fully Funded', 'Partial / Tuition', 'Research Grant / Stipend'."""
    combined = f"{title} {text}".lower()

    if re.search(r"\b(fully[- ]funded|full\s+scholarship|full\s+ride|100%\s+tuition|stipend\s+\+\s+flight|free\s+tuition)\b", combined):
        return "Fully Funded"

    if re.search(r"\b(partial|tuition\s+waiver|tuition\s+discount|50%\s+fee|half\s+tuition|fee\s+reduction)\b", combined):
        return "Partial / Tuition"

    if re.search(r"\b(grant|stipend|research\s+allowance|living\s+allowance|seed\s+fund)\b", combined):
        return "Research Grant / Stipend"

    return "Fully Funded"
