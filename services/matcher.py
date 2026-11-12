"""Profile Matching Engine for Opportunities and Jobs.

Evaluates user skills, degree, target roles, and location preferences against
scraped listings to compute dynamic fit scores (0-100%) and personalized match reasons.
"""

import re
from typing import Any, Dict, List, Optional


class ProfileMatcher:
    """Computes fit scores, matched skills, and matching justifications between user profiles and listings."""

    @staticmethod
    def _normalize_tokens(text: str) -> str:
        """Lowercases and cleans punctuation for reliable keyword matching."""
        return re.sub(r"[^\w\s\+\#]", " ", text.lower())

    @classmethod
    def match_item(
        cls,
        profile: Dict[str, Any],
        item: Dict[str, Any],
        item_type: str = "job",
    ) -> Dict[str, Any]:
        """
        Computes the fit score (0-100%) for a single job or scholarship opportunity.
        
        Returns a dictionary containing:
            - score (int 0-100)
            - grade (str)
            - color (str)
            - matched_skills (List[str])
            - reasons (List[str])
            - role_fit (str)
        """
        if not profile:
            return {
                "score": 50,
                "grade": "Uncalibrated",
                "color": "neutral",
                "matched_skills": [],
                "reasons": ["Set up your user profile to unlock AI matching."],
                "role_fit": "Neutral",
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
        # 1. Skill Matching (Up to 45 Points)
        # -------------------------------------------------------------
        matched_skills = []
        for skill in skills_list:
            s_clean = skill.strip().lower()
            if not s_clean:
                continue
            # Regex word boundary for short skills (e.g. 'sql', 'r', 'c#', 'ai')
            if len(s_clean) <= 4:
                pattern = rf"\b{re.escape(s_clean)}\b"
                if re.search(pattern, corpus):
                    matched_skills.append(skill)
            else:
                if s_clean in corpus:
                    matched_skills.append(skill)

        if matched_skills:
            # Scale proportionally to matched count (max 45)
            skill_pts = min(45, int(15 + (len(matched_skills) * 10)))
        else:
            # Baseline credit if general technical/domain keywords align
            broad_matches = [
                kw for kw in ["software", "tech", "data", "engineer", "research", "digital", "system", "science"]
                if kw in corpus
            ]
            skill_pts = 12 if broad_matches else 5

        # -------------------------------------------------------------
        # 2. Role & Title Alignment (Up to 30 Points)
        # -------------------------------------------------------------
        title_lower = title.lower()
        role_pts = 0
        role_fit_label = "Moderate"

        all_roles_to_check = target_roles + ([user_title] if user_title else [])
        for role in all_roles_to_check:
            r_lower = role.lower()
            # Direct phrase match
            if r_lower in title_lower or title_lower in r_lower:
                role_pts = 30
                role_fit_label = f"Direct Target ({role})"
                break
            # Word token overlap
            role_words = set(re.findall(r"\w+", r_lower))
            title_words = set(re.findall(r"\w+", title_lower))
            overlap = role_words.intersection(title_words)
            # Ignore stop words
            overlap.discard("and")
            overlap.discard("of")
            overlap.discard("the")
            overlap.discard("in")
            overlap.discard("for")
            if overlap:
                pts = min(25, 15 + len(overlap) * 5)
                if pts > role_pts:
                    role_pts = pts
                    role_fit_label = f"Related Role ({list(overlap)[0].title()})"

        if role_pts == 0:
            # Baseline role points if common position keyword present
            if any(term in title_lower for term in ["engineer", "developer", "specialist", "fellow", "researcher", "scholarship", "master", "phd"]):
                role_pts = 14
                role_fit_label = "Domain General"
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
            # Scholarship level
            if "phd" in degree and ("phd" in corpus or "doctoral" in corpus):
                level_pts = 10
            elif "master" in degree and ("master" in corpus or "msc" in corpus):
                level_pts = 10
            elif "bsc" in degree or "bachelor" in degree:
                level_pts = 8
            else:
                level_pts = 7

        # -------------------------------------------------------------
        # Total Score & Reasons Compilation
        # -------------------------------------------------------------
        total_raw = skill_pts + role_pts + loc_pts + level_pts
        final_score = max(20, min(97, total_raw))

        # Dynamic work-life score boost for 4dayweek jobs
        if item_type == "job" and item.get("work_life_score") and int(item.get("work_life_score")) >= 85:
            final_score = min(98, final_score + 2)

        # Build justifications
        reasons = []
        if matched_skills:
            top_skills = ", ".join(matched_skills[:3])
            more = f" (+{len(matched_skills) - 3} more)" if len(matched_skills) > 3 else ""
            reasons.append(f"Matches {len(matched_skills)} core skills: {top_skills}{more}.")
        else:
            reasons.append("Relevant to your technical engineering profile.")

        if role_pts >= 20:
            reasons.append(f"Strong role alignment ({role_fit_label}).")

        if is_remote and "remote" in preferred_locs:
            reasons.append("Fully remote flexibility matches your work preference.")
        elif item_type == "job" and item.get("salary"):
            reasons.append(f"Verified compensation: {item.get('salary')}.")

        if item_type == "job" and item.get("work_life_score"):
            reasons.append(f"High work-life balance score: {item.get('work_life_score')}/100.")

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
        }

    @classmethod
    def enrich_items(
        cls,
        profile: Dict[str, Any],
        items: List[Dict[str, Any]],
        item_type: str = "job",
    ) -> List[Dict[str, Any]]:
        """Attaches a 'match' metadata dictionary to every item in the list."""
        for item in items:
            item["match"] = cls.match_item(profile, item, item_type=item_type)
        return items
