"""Profile Matching Engine for Opportunities and Jobs.

Evaluates user skills, degree, target roles, and location preferences against
scraped listings to compute dynamic fit scores (0-100%) and personalized match reasons.
Includes comprehensive Academic Field & Degree Taxonomy matching across Journalism,
Accounting, Sports Science, Electrical Engineering, Business, Computer Science, and more.
"""

import re
from typing import Any, Dict, List, Optional


DOMAIN_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "journalism": {
        "label": "Journalism & Media",
        "keywords": [
            "journalism", "journalist", "reporter", "reporting", "editor", "editorial",
            "news", "broadcast", "media", "writer", "writing", "columnist", "investigative",
            "communication", "communications", "press", "pr", "public relations",
            "content creator", "storyteller", "publishing", "copywriter", "photojournalism",
            "media officer", "correspondent", "anchor"
        ],
        "degree_keywords": [
            "journalism", "mass communication", "media studies", "broadcast journalism",
            "communication", "english", "literature", "creative writing", "public relations",
            "media and communication"
        ]
    },
    "accounting": {
        "label": "Accounting & Finance",
        "keywords": [
            "accounting", "accountant", "audit", "auditing", "auditor", "finance",
            "financial", "tax", "taxation", "cpa", "bookkeeper", "bookkeeping",
            "payroll", "budget", "ledger", "controller", "treasury", "banking",
            "economist", "economics", "ifrs", "gaap", "quickbooks", "financial analyst",
            "credit analyst", "actuary"
        ],
        "degree_keywords": [
            "accounting", "finance", "banking", "financial management", "commerce",
            "economics", "applied finance", "accounting and finance"
        ]
    },
    "business": {
        "label": "Business & Management",
        "keywords": [
            "business", "management", "manager", "operations", "administration",
            "administrator", "marketing", "sales", "strategy", "consultant", "consulting",
            "project manager", "human resources", "hr", "recruiter", "recruitment",
            "supply chain", "logistics", "executive", "analyst", "business development",
            "procurement"
        ],
        "degree_keywords": [
            "business", "business administration", "mba", "management", "marketing",
            "human resources", "commerce", "entrepreneurship", "supply chain",
            "international business"
        ]
    },
    "sports": {
        "label": "Sports & Kinesiology",
        "keywords": [
            "sports", "sport", "athletic", "athletics", "coach", "coaching",
            "fitness", "kinesiology", "physical education", "gym", "trainer", "training",
            "recreation", "exercise", "physiotherapy", "wellness", "biomechanics",
            "referee", "sports management"
        ],
        "degree_keywords": [
            "sports science", "kinesiology", "physical education", "sports management",
            "athletic training", "exercise science", "sports coaching", "physical therapy"
        ]
    },
    "electrical_engineering": {
        "label": "Electrical Engineering",
        "keywords": [
            "electrical", "electrician", "electronics", "circuit", "circuits",
            "power systems", "high voltage", "embedded", "plc", "scada",
            "telecommunications", "pcb", "microcontroller", "rf", "semiconductor",
            "hardware engineer", "signal processing", "autocad electrical", "grid",
            "substation", "instrumentation"
        ],
        "degree_keywords": [
            "electrical engineering", "electronics engineering", "telecommunications",
            "electrical and electronics", "power engineering", "microelectronics",
            "control systems"
        ]
    },
    "mechanical_engineering": {
        "label": "Mechanical Engineering",
        "keywords": [
            "mechanical", "cad", "solidworks", "thermodynamics", "manufacturing",
            "hvac", "automotive", "aerospace", "machinery", "robotics", "mechanic",
            "piping", "fluid dynamics", "mechatronics"
        ],
        "degree_keywords": [
            "mechanical engineering", "manufacturing engineering", "mechatronics",
            "aerospace engineering", "automotive engineering"
        ]
    },
    "civil_engineering": {
        "label": "Civil Engineering & Architecture",
        "keywords": [
            "civil", "structural", "construction", "site engineer", "surveyor",
            "surveying", "geotechnical", "concrete", "infrastructure", "architect",
            "architecture", "urban planning", "bim", "revit", "road", "bridge"
        ],
        "degree_keywords": [
            "civil engineering", "structural engineering", "architecture",
            "urban planning", "construction management"
        ]
    },
    "computer_science": {
        "label": "Computer Science & IT",
        "keywords": [
            "software", "developer", "programmer", "frontend", "backend", "full stack",
            "fullstack", "python", "javascript", "react", "node", "java", "c++",
            "ai", "machine learning", "data science", "data engineer", "cloud", "aws",
            "devops", "cybersecurity", "network", "web developer", "mobile developer",
            "database", "sql", "typescript", "golang", "flutter", "docker", "kubernetes"
        ],
        "degree_keywords": [
            "computer science", "software engineering", "information technology",
            "computer engineering", "data science", "informatics", "cybersecurity",
            "computing", "information systems"
        ]
    },
    "healthcare": {
        "label": "Healthcare & Medicine",
        "keywords": [
            "health", "healthcare", "nurse", "nursing", "medical", "medicine",
            "doctor", "physician", "clinical", "hospital", "patient", "pharmacy",
            "pharmacist", "pharmacology", "public health", "epidemiology", "dentist",
            "laboratory", "biomedical", "pathology", "midwife", "surgeon"
        ],
        "degree_keywords": [
            "medicine", "nursing", "public health", "pharmacy", "biomedical",
            "dentistry", "clinical medicine", "health science"
        ]
    },
    "law": {
        "label": "Law & Legal Studies",
        "keywords": [
            "law", "legal", "lawyer", "attorney", "counsel", "paralegal",
            "litigation", "compliance", "regulatory", "contracts", "jurist", "court",
            "judge", "advocate", "human rights", "policy"
        ],
        "degree_keywords": [
            "law", "llb", "llm", "juris doctor", "legal studies", "criminology",
            "international law"
        ]
    },
    "education": {
        "label": "Education & Teaching",
        "keywords": [
            "teacher", "teaching", "education", "educator", "school", "instructor",
            "lecturer", "professor", "pedagogy", "curriculum", "tutor", "academic",
            "classroom", "faculty"
        ],
        "degree_keywords": [
            "education", "teaching", "pedagogy", "curriculum and instruction",
            "linguistics", "educational leadership"
        ]
    },
    "sciences": {
        "label": "Natural & Applied Sciences",
        "keywords": [
            "biology", "biologist", "chemistry", "chemist", "physics", "physicist",
            "mathematics", "statistician", "statistics", "geology", "agriculture",
            "agronomy", "environmental", "biochem", "microbiology"
        ],
        "degree_keywords": [
            "biology", "chemistry", "physics", "mathematics", "statistics",
            "biochemistry", "environmental science", "agricultural science"
        ]
    }
}


class ProfileMatcher:
    """Computes fit scores, matched skills, and matching justifications between user profiles and listings."""

    @staticmethod
    def _normalize_tokens(text: str) -> str:
        """Lowercases and cleans punctuation for reliable keyword matching."""
        return re.sub(r"[^\w\s\+\#]", " ", text.lower())

    @classmethod
    def detect_domain(cls, text: str) -> Optional[str]:
        """Classifies a text string into its primary academic or career domain."""
        if not text:
            return None
        text_low = text.lower()
        scores: Dict[str, int] = {}
        for dom, data in DOMAIN_TAXONOMY.items():
            score = 0
            # Higher weight for academic degree matches
            for dkw in data.get("degree_keywords", []):
                if dkw in text_low:
                    score += 6
            # Domain terminology matches
            for kw in data.get("keywords", []):
                if f" {kw} " in f" {text_low} " or text_low.startswith(f"{kw} ") or text_low.endswith(f" {kw}"):
                    score += 2
                elif kw in text_low:
                    score += 1
            if score > 0:
                scores[dom] = score
        if not scores:
            return None
        return max(scores, key=scores.get)

    @classmethod
    def get_domain_label(cls, domain_key: Optional[str]) -> str:
        """Returns the human-readable label for a domain key."""
        if not domain_key or domain_key not in DOMAIN_TAXONOMY:
            return "General / Interdisciplinary"
        return DOMAIN_TAXONOMY[domain_key]["label"]

    @classmethod
    def detect_item_domain(cls, item: Dict[str, Any], item_type: str = "job") -> Optional[str]:
        """Extracts the domain classification of a job, scholarship, or grant item."""
        title = item.get("title") or ""
        tags = item.get("tags") or []
        tags_str = " ".join(tags) if isinstance(tags, list) else str(tags)
        category = item.get("category") or ""
        text = f"{title} {tags_str} {category}"
        if item_type == "job":
            company = item.get("company") or ""
            text += f" {company}"
        elif item_type == "grant":
            org = item.get("organization") or ""
            text += f" {org}"
        else:
            raw = (item.get("raw_text") or "")[:300]
            text += f" {raw}"
        return cls.detect_domain(text)

    @classmethod
    def match_item(
        cls,
        profile: Dict[str, Any],
        item: Dict[str, Any],
        item_type: str = "job",
    ) -> Dict[str, Any]:
        """
        Computes the fit score (0-100%) for a single job or scholarship opportunity.
        Includes cross-domain field isolation to prevent mismatching disparate disciplines.
        """
        if not profile:
            return {
                "score": 50,
                "grade": "Uncalibrated",
                "color": "neutral",
                "matched_skills": [],
                "reasons": ["Set up your user profile to unlock AI matching."],
                "role_fit": "Neutral",
                "domain_match": True,
            }

        skills_list = profile.get("skills_list") or [
            s.strip() for s in (profile.get("skills") or "").split(",") if s.strip()
        ]
        target_roles = profile.get("target_roles_list") or [
            r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()
        ]
        user_title = profile.get("title") or ""
        experience_years = int(profile.get("experience_years") or 0)
        degree = (profile.get("degree") or "").lower()
        field_of_study = (profile.get("field_of_study") or "").lower()
        preferred_locs = (profile.get("preferred_locations") or "").lower()

        # Build corpus of text to inspect
        title = item.get("title") or ""
        if item_type == "job":
            company = item.get("company") or ""
            location = item.get("location") or ""
            schedule = item.get("schedule") or ""
            is_remote = bool(item.get("is_remote", 1))
            work_life_score = item.get("work_life_score")
            corpus = f"{title} {company} {location} {schedule}".lower()
        elif item_type == "grant":
            org = item.get("organization") or ""
            stage = item.get("stage") or ""
            location = item.get("location") or "Remote"
            highlights = " ".join(item.get("key_highlights") or [])
            corpus = f"{title} {org} {stage} {location} {highlights}".lower()
            is_remote = "remote" in location.lower() or "global" in location.lower()
        else:
            raw_text = item.get("raw_text") or ""
            highlights = " ".join(item.get("key_highlights") or [])
            corpus = f"{title} {raw_text} {highlights}".lower()
            location = corpus
            is_remote = "online" in corpus or "remote" in corpus

        # -------------------------------------------------------------
        # DOMAIN & FIELD RELEVANCE ASSESSMENT
        # -------------------------------------------------------------
        user_domain_text = f"{field_of_study} {degree} {user_title} {' '.join(target_roles)} {' '.join(skills_list)}"
        user_domain = cls.detect_domain(user_domain_text)
        item_domain = cls.detect_item_domain(item, item_type=item_type)

        user_domain_label = cls.get_domain_label(user_domain)
        item_domain_label = cls.get_domain_label(item_domain)

        # Cross-domain check: if user has a specific field and item is clearly in an unrelated field
        is_direct_domain_match = False
        if user_domain and item_domain:
            if user_domain == item_domain:
                is_direct_domain_match = True
            elif user_domain != item_domain:
                # E.g. Journalism degree viewing a Software Developer job, or Accounting viewing React dev
                return {
                    "score": 28,
                    "grade": "Different Field",
                    "color": "slate",
                    "matched_skills": [],
                    "reasons": [
                        f"Position is in {item_domain_label}, which is outside your background in {user_domain_label}.",
                        f"Tailored filters prioritize opportunities aligned with {user_domain_label}."
                    ],
                    "role_fit": f"Outside Field ({item_domain_label})",
                    "domain_match": False,
                }
        else:
            # Neutral / general domain
            is_direct_domain_match = True

        # -------------------------------------------------------------
        # 1. Skill Matching (Up to 45 Points)
        # -------------------------------------------------------------
        matched_skills = []
        for skill in skills_list:
            s_clean = skill.strip().lower()
            if not s_clean:
                continue
            if len(s_clean) <= 4:
                pattern = rf"\b{re.escape(s_clean)}\b"
                if re.search(pattern, corpus):
                    matched_skills.append(skill)
            else:
                if s_clean in corpus:
                    matched_skills.append(skill)

        if matched_skills:
            skill_pts = min(45, int(15 + (len(matched_skills) * 10)))
        else:
            # Credit if direct domain match
            skill_pts = 15 if is_direct_domain_match else 5

        # -------------------------------------------------------------
        # 2. Role & Title Alignment (Up to 30 Points)
        # -------------------------------------------------------------
        title_lower = title.lower()
        role_pts = 0
        role_fit_label = "Moderate"

        all_roles_to_check = target_roles + ([user_title] if user_title else [])
        for role in all_roles_to_check:
            r_lower = role.lower()
            if r_lower in title_lower or title_lower in r_lower:
                role_pts = 30
                role_fit_label = f"Direct Target ({role})"
                break
            role_words = set(re.findall(r"\w+", r_lower))
            title_words = set(re.findall(r"\w+", title_lower))
            overlap = role_words.intersection(title_words)
            for stop in ["and", "of", "the", "in", "for"]:
                overlap.discard(stop)
            if overlap:
                pts = min(25, 15 + len(overlap) * 5)
                if pts > role_pts:
                    role_pts = pts
                    role_fit_label = f"Related Role ({list(overlap)[0].title()})"

        if role_pts == 0:
            if is_direct_domain_match:
                role_pts = 18
                role_fit_label = f"Field Match ({user_domain_label})"
            else:
                role_pts = 8
                role_fit_label = "Adjacent Field"

        # -------------------------------------------------------------
        # 3. Location & Work Style Alignment (Up to 15 Points)
        # -------------------------------------------------------------
        loc_pts = 0
        if "remote" in preferred_locs and is_remote:
            loc_pts = 15
        elif any(country in location.lower() for country in ["usa", "us", "uk", "spain", "europe", "canada", "germany", "ethiopia"] if country in preferred_locs):
            loc_pts = 15
        elif is_remote:
            loc_pts = 12
        else:
            loc_pts = 7

        # -------------------------------------------------------------
        # 4. Seniority / Academic Level Alignment (Up to 10 Points)
        # -------------------------------------------------------------
        level_pts = 0
        if item_type == "job":
            is_senior = any(w in title_lower for w in ["senior", "lead", "director", "principal", "head", "manager"])
            if is_senior and experience_years >= 3:
                level_pts = 10
            elif not is_senior:
                level_pts = 9
            else:
                level_pts = 6
        else:
            if "phd" in degree and ("phd" in corpus or "doctoral" in corpus):
                level_pts = 10
            elif "master" in degree and ("master" in corpus or "msc" in corpus):
                level_pts = 10
            elif "bsc" in degree or "bachelor" in degree or "ba" in degree:
                level_pts = 8
            else:
                level_pts = 7

        # -------------------------------------------------------------
        # Total Score & Reasons Compilation
        # -------------------------------------------------------------
        total_raw = skill_pts + role_pts + loc_pts + level_pts
        if is_direct_domain_match and user_domain:
            total_raw += 8

        final_score = max(20, min(97, total_raw))

        if item_type == "job" and item.get("work_life_score") and int(item.get("work_life_score")) >= 85:
            final_score = min(98, final_score + 2)

        reasons = []
        if is_direct_domain_match and user_domain:
            reasons.append(f"Direct field match: Aligned with your background in {user_domain_label}.")

        if matched_skills:
            top_skills = ", ".join(matched_skills[:3])
            more = f" (+{len(matched_skills) - 3} more)" if len(matched_skills) > 3 else ""
            reasons.append(f"Matches {len(matched_skills)} core skills: {top_skills}{more}.")

        if role_pts >= 20:
            reasons.append(f"Strong role alignment ({role_fit_label}).")

        if is_remote and "remote" in preferred_locs:
            reasons.append("Fully remote flexibility matches your work preference.")
        elif item_type == "job" and item.get("salary"):
            reasons.append(f"Verified compensation: {item.get('salary')}.")

        if not reasons:
            reasons.append(f"Opportunity matches your general {user_domain_label} profile.")

        # Determine grade and styling
        if final_score >= 82:
            grade = "Exceptional Match"
            color = "emerald"
        elif final_score >= 68:
            grade = "Strong Match"
            color = "lime"
        elif final_score >= 48:
            grade = "Good Fit"
            color = "amber"
        else:
            grade = "Potential Fit"
            color = "neutral"

        return {
            "score": final_score,
            "grade": grade,
            "color": color,
            "matched_skills": matched_skills,
            "reasons": reasons[:3],
            "role_fit": role_fit_label,
            "domain_match": True,
        }

    @classmethod
    def enrich_items(
        cls,
        profile: Dict[str, Any],
        items: List[Dict[str, Any]],
        item_type: str = "job",
        sort_by_relevance: bool = True,
    ) -> List[Dict[str, Any]]:
        """Attaches a 'match' metadata dictionary to every item and optionally sorts by fit score."""
        for item in items:
            match = cls.match_item(profile, item, item_type=item_type)
            item["match"] = match
            item["domain_match"] = match.get("domain_match", True)

        if sort_by_relevance:
            # Sort domain matches first, then by match score descending
            items.sort(
                key=lambda x: (
                    1 if x.get("domain_match", True) else 0,
                    x.get("match", {}).get("score", 0),
                ),
                reverse=True,
            )
        return items
