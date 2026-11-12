"""AI Resume Parser, Dynamic Matcher & Recommendation Engine.

Provides zero-cost, open AI resume parsing, dynamic profile calibration,
grade/GPA extraction, and tailored recommendation generation.

Supports:
1. Free Google Gemini API (gemini-1.5-flash / gemini-2.0-flash free tier).
2. Built-in zero-dependency Offline Semantic AI Parser (heuristic NLP).
"""

import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pypdf import PdfReader

from services.matcher import ProfileMatcher
from storage.db import OpportunityDB

logger = logging.getLogger("ai_resume")

# Taxonomy of recognizable technical & domain skills
SKILL_TAXONOMY = [
    # Languages
    "Python", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++", "C#", "Java", "SQL",
    "R", "Ruby", "PHP", "Swift", "Kotlin", "HTML", "CSS", "Bash", "Shell",
    # Frameworks & Libraries
    "FastAPI", "Django", "Flask", "React", "Next.js", "Vue.js", "Angular", "Node.js", "Express",
    "PyTorch", "TensorFlow", "Scikit-Learn", "Pandas", "NumPy", "Tailwind CSS", "Bootstrap",
    # Data & AI
    "Machine Learning", "Deep Learning", "Natural Language Processing", "NLP", "Computer Vision",
    "Data Scraping", "Web Scraping", "Data Engineering", "Data Analysis", "ETL", "Vector Databases",
    "LLM", "Generative AI", "Bioinformatics", "Data Visualization",
    # Infrastructure & Tools
    "Docker", "Kubernetes", "AWS", "Google Cloud", "GCP", "Azure", "Git", "GitHub", "CI/CD",
    "Linux", "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQLite", "GraphQL", "REST API",
    "Microservices", "Distributed Systems", "Cloud Architecture", "Terraform",
    # Soft & Academic Skills
    "Scientific Writing", "Research Methodology", "Project Management", "Agile", "Scrum",
    "Technical Leadership", "System Design", "Mentorship", "Public Speaking",
]


class AIResumeService:
    """Zero-cost AI resume parsing, grade extraction, and dynamic matching service."""

    @staticmethod
    def extract_text(file_bytes: bytes, filename: str) -> str:
        """
        Extracts clean plain text from an uploaded resume file (PDF, TXT, MD).
        """
        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                text_pages = []
                for idx, page in enumerate(reader.pages):
                    extracted = page.extract_text()
                    if extracted:
                        text_pages.append(extracted)
                full_text = "\n\n".join(text_pages)
                if full_text.strip():
                    return full_text
            except Exception as e:
                logger.warning("PDF extraction with pypdf failed, attempting raw decode: %s", e)

        # Fallback to text decoding
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue

        return file_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def parse_resume(
        cls,
        resume_text: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses resume text into a rich structured candidate profile.
        Tries Gemini Free API first if a key is provided or found in env,
        otherwise uses the offline semantic NLP engine.
        """
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")

        if api_key:
            try:
                gemini_result = cls._parse_with_gemini(resume_text, api_key)
                if gemini_result and gemini_result.get("full_name"):
                    gemini_result["parser_used"] = "Google Gemini 1.5 Flash (Free Tier)"
                    return gemini_result
            except Exception as e:
                logger.warning("Gemini API parsing encountered an error, falling back to offline engine: %s", e)

        offline_result = cls._parse_offline(resume_text)
        offline_result["parser_used"] = "Built-in Free Heuristic AI Engine"
        return offline_result

    # =========================================================================
    # Free Google Gemini API Parser
    # =========================================================================

    @classmethod
    def _parse_with_gemini(cls, resume_text: str, api_key: str) -> Dict[str, Any]:
        """Calls Google Gemini Free Tier API to parse resume text into JSON."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        system_instruction = (
            "You are an expert talent acquisition and academic admissions AI. "
            "Analyze the following resume/CV text and extract structured candidate profile data. "
            "Return strictly valid JSON with no markdown formatting or backticks. "
            "JSON structure: {\n"
            '  "full_name": "string",\n'
            '  "email": "string",\n'
            '  "title": "string (e.g. Full-Stack Engineer, AI Researcher)",\n'
            '  "gpa_grades": "string (e.g. 3.90/4.0, First Class Honours, Magna Cum Laude, or null if none)",\n'
            '  "degree": "string (e.g. BSc in Computer Science, PhD in Data Science)",\n'
            '  "skills": "string (comma-separated list of top technical and professional skills)",\n'
            '  "experience_years": number (integer estimate of years of experience),\n'
            '  "preferred_locations": "string (e.g. Remote, Europe, Global)",\n'
            '  "target_roles": "string (comma-separated list of best fitting job or fellowship titles)",\n'
            '  "bio": "string (a concise 2-3 sentence executive bio highlighting unique background and standout achievements)",\n'
            '  "key_achievements": ["string", "string"],\n'
            '  "academic_honors": ["string", "string"],\n'
            '  "strengths_for_scholarships": "string",\n'
            '  "strengths_for_jobs": "string"\n'
            "}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {"text": f"Candidate Resume Text:\n\n{resume_text[:12000]}"},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }

        with httpx.Client(timeout=25.0) as client:
            resp = client.post(endpoint, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text}")
            data = resp.json()
            raw_content = data["candidates"][0]["content"]["parts"][0]["text"]
            # Clean possible markdown wrap
            clean_json = re.sub(r"^```json\s*|\s*```$", "", raw_content.strip())
            return json.loads(clean_json)

    # =========================================================================
    # Offline Semantic AI Parser (Zero-Cost, No External Network Needed)
    # =========================================================================

    @classmethod
    def _parse_offline(cls, text: str) -> Dict[str, Any]:
        """
        Robust heuristic extraction of candidate credentials, grades, degrees,
        and experience without external network dependencies.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Extract Email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        email = email_match.group(0) if email_match else ""

        # 2. Extract Name (typically within the first 4 non-empty lines)
        name = "Applicant"
        for line in lines[:5]:
            # Skip lines with email, urls, or phone numbers
            if "@" in line or "http" in line or "resume" in line.lower() or "curriculum" in line.lower():
                continue
            # Plausible name: 2-4 words, capitalized letters
            words = line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w.isalpha()):
                name = line
                break

        # 3. Extract GPA / Grades / Academic Standing
        gpa_grades = cls._extract_grades(text)

        # 4. Extract Degree & Institution
        degree = cls._extract_degree(text)

        # 5. Extract Skills
        matched_skills = cls._extract_skills(text)
        skills_str = ", ".join(matched_skills[:12]) if matched_skills else "Software Engineering, Problem Solving, Research"

        # 6. Extract Experience Years
        exp_years = cls._extract_experience_years(text)

        # 7. Extract Title & Target Roles
        title = cls._extract_title(text, matched_skills)
        target_roles = cls._extract_target_roles(title, matched_skills, degree)

        # 8. Extract Standout Achievements / Publications
        achievements = cls._extract_achievements(text)

        # 9. Construct Executive Bio
        bio = cls._build_bio(name, title, degree, gpa_grades, exp_years, matched_skills)

        return {
            "full_name": name,
            "email": email,
            "title": title,
            "gpa_grades": gpa_grades,
            "degree": degree,
            "skills": skills_str,
            "experience_years": exp_years,
            "preferred_locations": "Remote, Global, Europe, North America",
            "target_roles": target_roles,
            "bio": bio,
            "key_achievements": achievements,
            "academic_honors": [gpa_grades] if gpa_grades else [],
            "strengths_for_scholarships": (
                f"Possesses a strong academic foundation ({degree}) with recognized standing ({gpa_grades or 'Solid Track Record'}), "
                f"well suited for competitive fellowships and graduate research."
            ),
            "strengths_for_jobs": (
                f"Demonstrates hands-on capability across {len(matched_skills)} core technical competencies ({', '.join(matched_skills[:4])}) "
                f"with approximately {exp_years}+ years of practical delivery."
            ),
        }

    @staticmethod
    def _extract_grades(text: str) -> Optional[str]:
        """Detects and extracts GPA numbers, Latin honors, British honors, or percentages."""
        # GPA patterns: e.g. "GPA: 3.85 / 4.0", "3.9 GPA", "cGPA 3.75/4.00"
        gpa_patterns = [
            r"\b(?:c?gpa|grade\s*point\s*average)\s*[:=-]?\s*([0-4]\.\d{1,2}(?:\s*\/\s*4(?:\.0)?)?)\b",
            r"\b([34]\.\d{1,2})\s*(?:\/\s*4(?:\.0)?)\s*(?:gpa)?\b",
            r"\b([0-4]\.\d{1,2})\s+gpa\b",
        ]
        for pat in gpa_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                gpa_val = m.group(1).strip()
                if "/" not in gpa_val:
                    gpa_val += " / 4.0"
                # Check for honors in the same sentence
                if re.search(r"first\s*class", text, re.IGNORECASE):
                    return f"{gpa_val} (First Class Honours)"
                if re.search(r"magna\s*cum\s*laude", text, re.IGNORECASE):
                    return f"{gpa_val} (Magna Cum Laude)"
                if re.search(r"summa\s*cum\s*laude", text, re.IGNORECASE):
                    return f"{gpa_val} (Summa Cum Laude)"
                return gpa_val

        # Latin Honors standalone
        if re.search(r"\bsumma\s*cum\s*laude\b", text, re.IGNORECASE):
            return "Summa Cum Laude (Top 1-5%)"
        if re.search(r"\bmagna\s*cum\s*laude\b", text, re.IGNORECASE):
            return "Magna Cum Laude (Top 10%)"
        if re.search(r"\bcum\s*laude\b", text, re.IGNORECASE):
            return "Cum Laude (Honors Standing)"

        # UK Honors standalone
        if re.search(r"\bfirst\s*class\s*(?:honou?rs|degree)?\b", text, re.IGNORECASE):
            return "First Class Honours (1st)"
        if re.search(r"\bupper\s*second|2:1\s*honou?rs\b", text, re.IGNORECASE):
            return "Upper Second Class Honours (2:1)"

        # Percentage score: e.g. "Grade: 88%" or "Aggregate: 91%"
        pct_match = re.search(r"\b(?:grade|score|aggregate|marks?)\s*[:=-]?\s*([89]\d(?:\.\d{1,2})?%)\b", text, re.IGNORECASE)
        if pct_match:
            return f"Top Decile ({pct_match.group(1)})"

        # Dean's list
        if re.search(r"dean'?s\s*list", text, re.IGNORECASE):
            return "Dean's List / High Academic Standing"

        return "Good Academic Standing"

    @staticmethod
    def _extract_degree(text: str) -> str:
        """Finds degrees like PhD, MSc, BSc, Bachelor, Master, etc."""
        degree_patterns = [
            r"\b(Ph\.?D\.?(?:\s+in\s+[\w\s]+)?)\b",
            r"\b(Master(?:\s*of\s*[\w\s]+|\s*'?s\s*(?:degree)?\s*(?:in\s+[\w\s]+)?))\b",
            r"\b(M\.?Sc\.?(?:\s+in\s+[\w\s]+)?)\b",
            r"\b(Bachelor(?:\s*of\s*[\w\s]+|\s*'?s\s*(?:degree)?\s*(?:in\s+[\w\s]+)?))\b",
            r"\b(B\.?Sc\.?(?:\s+in\s+[\w\s]+)?)\b",
            r"\b(B\.?Eng\.?(?:\s+in\s+[\w\s]+)?)\b",
        ]
        for pat in degree_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                clean_degree = re.sub(r"\s+", " ", m.group(0)).strip()
                # Cap length to avoid greedy grabs
                return clean_degree[:50]
        return "BSc in Computer Science"

    @staticmethod
    def _extract_skills(text: str) -> List[str]:
        """Matches skills against our comprehensive skill taxonomy."""
        found = []
        lower_text = text.lower()
        for skill in SKILL_TAXONOMY:
            s_clean = skill.lower()
            if len(s_clean) <= 4:
                # Word boundary for short acronyms like 'r', 'sql', 'go', 'gcp'
                if re.search(rf"\b{re.escape(s_clean)}\b", lower_text):
                    found.append(skill)
            else:
                if s_clean in lower_text:
                    found.append(skill)
        return found

    @staticmethod
    def _extract_experience_years(text: str) -> int:
        """Estimates years of experience from year ranges or explicit mentions."""
        # Check explicit mentions: "5+ years", "4 years of experience"
        m = re.search(r"\b(\d{1,2})\+?\s*years?(?:\s+of)?\s+(?:experience|work|industry)\b", text, re.IGNORECASE)
        if m:
            return min(25, max(1, int(m.group(1))))

        # Detect year ranges like "2019 - 2024", "2021 to Present"
        years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", text)]
        if len(years) >= 2:
            span = max(years) - min(years)
            if 1 <= span <= 20:
                return span

        return 3

    @staticmethod
    def _extract_title(text: str, skills: List[str]) -> str:
        """Infers professional title from resume headings or dominant skills."""
        title_candidates = [
            "Machine Learning Engineer", "AI Researcher", "Full-Stack Developer",
            "Software Engineer", "Backend Engineer", "Data Scientist",
            "Data Engineer", "Frontend Developer", "DevOps Engineer",
            "Distributed Systems Engineer", "Research Fellow"
        ]
        for candidate in title_candidates:
            if re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE):
                return candidate

        # Infer from skills
        if "PyTorch" in skills or "TensorFlow" in skills or "Machine Learning" in skills:
            return "AI & Machine Learning Engineer"
        if "FastAPI" in skills or "Go" in skills or "Distributed Systems" in skills:
            return "Backend & Distributed Systems Engineer"
        if "React" in skills and "Python" in skills:
            return "Full-Stack Software Engineer"
        return "Software Engineer"

    @staticmethod
    def _extract_target_roles(title: str, skills: List[str], degree: str) -> str:
        """Constructs target roles list based on title, skills, and degree level."""
        roles = [title]
        if "phd" in degree.lower() or "research" in title.lower():
            roles.append("Research Fellow")
            roles.append("Applied Scientist")
        if "ai" in title.lower() or "machine learning" in [s.lower() for s in skills]:
            roles.append("AI Backend Engineer")
            roles.append("ML Platform Engineer")
        if "full-stack" not in title.lower():
            roles.append("Full-Stack Engineer")
        roles.append("Senior Software Developer")

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for r in roles:
            if r.lower() not in seen:
                seen.add(r.lower())
                deduped.append(r)
        return ", ".join(deduped[:4])

    @staticmethod
    def _extract_achievements(text: str) -> List[str]:
        """Extracts bulleted standout achievements or project highlights."""
        achievements = []
        bullet_matches = re.findall(r"(?:•|\*|-|\d+\.)\s*([A-Z][^.\n]{20,140}\.)", text)
        for b in bullet_matches[:4]:
            achievements.append(b.strip())

        if not achievements:
            achievements = [
                "Engineered resilient automated data pipelines reducing processing latency.",
                "Designed and deployed modern microservices with robust test coverage.",
                "Published technical research or contributed to open-source software libraries.",
            ]
        return achievements

    @staticmethod
    def _build_bio(
        name: str,
        title: str,
        degree: str,
        gpa: Optional[str],
        exp: int,
        skills: List[str],
    ) -> str:
        """Composes an executive candidate biography."""
        gpa_phrase = f" with strong academic standing ({gpa})" if gpa else ""
        skills_phrase = f" and core proficiencies in {', '.join(skills[:3])}" if skills else ""
        return (
            f"{title} holding a {degree}{gpa_phrase} and {exp}+ years of practical engineering experience. "
            f"Proven track record of designing reliable systems{skills_phrase}, "
            f"driven by high impact, analytical discipline, and clean architecture."
        )

    # =========================================================================
    # Dynamic Recommendations & Matching Engine
    # =========================================================================

    @classmethod
    def get_dynamic_recommendations(
        cls,
        profile: Dict[str, Any],
        db: OpportunityDB,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        """
        Dynamically analyzes user profile (grades, skills, target roles, experience)
        against all active scholarships, jobs, and grants in the database.
        Returns top recommendations ranked by multi-dimensional match score.
        """
        opps = db.get_all(limit=50)
        jobs = db.get_jobs(limit=50)
        grants = db.get_grants(limit=50)

        # Score all items
        scored_opps = []
        for o in opps:
            match = ProfileMatcher.match_item(profile, o, item_type="opportunity")
            # Academic bonus for high GPA / honors on scholarships
            gpa_grades = profile.get("gpa_grades") or ""
            if any(term in gpa_grades.lower() for term in ["3.8", "3.9", "4.0", "first class", "summa", "magna"]):
                match["score"] = min(99, match["score"] + 6)
                match["reasons"].insert(0, f"🎓 Academic Merit Match: Your high GPA / Honors ({gpa_grades}) matches merit criteria.")
            scored_opps.append({**o, "match": match})

        scored_jobs = []
        for j in jobs:
            match = ProfileMatcher.match_item(profile, j, item_type="job")
            scored_jobs.append({**j, "match": match})

        scored_grants = []
        for g in grants:
            match = ProfileMatcher.match_item(profile, g, item_type="grant")
            scored_grants.append({**g, "match": match})

        # Sort descending by match score
        scored_opps.sort(key=lambda x: x["match"]["score"], reverse=True)
        scored_jobs.sort(key=lambda x: x["match"]["score"], reverse=True)
        scored_grants.sort(key=lambda x: x["match"]["score"], reverse=True)

        top_opps = scored_opps[:top_k]
        top_jobs = scored_jobs[:top_k]
        top_grants = scored_grants[:top_k]

        # Build personalized strategic summary
        gpa = profile.get("gpa_grades") or "Strong Academic Profile"
        skills = profile.get("skills_list") or []
        summary = (
            f"Based on your calibrated profile ({profile.get('degree') or 'Degree'} • {gpa}), "
            f"we identified {len(top_opps)} top scholarships/fellowships where your academic standing provides an edge, "
            f"{len(top_jobs)} high-fit 4-day remote roles aligning with your {len(skills)} verified skills, "
            f"and {len(top_grants)} active tech grants to fund your projects."
        )

        return {
            "summary": summary,
            "candidate_highlights": {
                "name": profile.get("full_name"),
                "academic_standing": gpa,
                "degree": profile.get("degree"),
                "experience_years": profile.get("experience_years"),
                "verified_skills_count": len(skills),
                "target_roles": profile.get("target_roles"),
            },
            "scholarships": top_opps,
            "jobs": top_jobs,
            "grants": top_grants,
        }
