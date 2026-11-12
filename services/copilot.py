"""Application Copilot Engine for 1-Click Tailored Documents.

Generates customized, high-converting Cover Letters (for jobs) and Statements of Purpose
(for scholarships/fellowships) directly aligned with scraped listings and user profile data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from services.matcher import ProfileMatcher


class ApplicationCopilot:
    """Generates personalized application documents for jobs and scholarship opportunities."""

    @classmethod
    def generate_document(
        cls,
        profile: Dict[str, Any],
        item: Dict[str, Any],
        item_type: str = "job",
        tone: str = "professional",
    ) -> Dict[str, Any]:
        """
        Orchestrates document generation based on item_type ('job' or 'opportunity').
        Returns structured dict with markdown, plain_text, title, and metadata.
        """
        if item_type == "job":
            return cls.generate_job_cover_letter(profile, item, tone=tone)
        else:
            return cls.generate_scholarship_statement(profile, item, tone=tone)

    @classmethod
    def generate_job_cover_letter(
        cls,
        profile: Dict[str, Any],
        job: Dict[str, Any],
        tone: str = "professional",
    ) -> Dict[str, Any]:
        """Generates a tailored Cover Letter for a job listing."""
        candidate_name = profile.get("full_name") or "Applicant"
        candidate_email = profile.get("email") or "applicant@example.com"
        candidate_title = profile.get("title") or "Software Engineer"
        candidate_bio = profile.get("bio") or ""
        experience_years = profile.get("experience_years") or 3

        job_title = job.get("title") or "the advertised role"
        company = job.get("company") or "your company"
        location = job.get("location") or "Remote"
        salary = job.get("salary")
        schedule = job.get("schedule") or "4-Day Work Week"
        work_life = job.get("work_life_score")

        # Compute skill overlap for deep tailoring
        match_info = ProfileMatcher.match_item(profile, job, item_type="job")
        matched_skills = match_info.get("matched_skills") or []
        primary_skills = ", ".join(matched_skills[:3]) if matched_skills else "distributed systems and modern application engineering"

        today_str = datetime.now().strftime("%B %d, %Y")

        # Construct markdown content
        md_lines = [
            f"**{candidate_name}**",
            f"{candidate_title} | {candidate_email}",
            f"{today_str}\n",
            f"**Hiring Committee & Talent Acquisition**",
            f"{company}",
            f"{location}\n",
            f"**Subject: Application for {job_title} — {candidate_name}**\n",
            f"Dear Hiring Team at {company},\n",
            (
                f"I am writing to express my strong interest in the **{job_title}** position at **{company}**. "
                f"With {experience_years}+ years of focused experience in modern software engineering and technical architecture, "
                f"I have followed {company}'s commitment to thoughtful execution and high-performance culture. "
                f"The combination of your mission and an environment that champions deliberate, high-impact focus "
                f"makes this opportunity an exceptional fit for my background."
            ),
            "",
            (
                f"Throughout my career, I have specialized in building robust, maintainable systems and delivering tangible product value. "
                f"My core competencies directly align with your requirements in **{primary_skills}**. "
                f"In my previous work, {candidate_bio.strip() if candidate_bio else 'I have consistently designed scalable backends and resilient automated workflows that improved operational efficiency and user outcomes.'}"
            ),
            "",
            (
                f"What specifically excites me about {company} is your progressive workplace design—especially your {schedule} structure "
                + (f"and top-tier work-life balance rating ({work_life}/100). " if work_life else ". ")
                + "I thrive in asynchronous, autonomy-driven environments where quality of output and intentional communication take precedence over friction and noise."
            ),
            "",
            (
                f"I would welcome the opportunity to discuss how my technical expertise in {primary_skills} and disciplined execution "
                f"can help {company} achieve its next milestones for the {job_title} role. "
                f"Thank you very much for your time and consideration."
            ),
            "",
            "Sincerely,",
            f"**{candidate_name}**",
            f"{candidate_email}",
        ]

        markdown_doc = "\n".join(md_lines)
        plain_text = markdown_doc.replace("**", "").replace("*", "")

        return {
            "title": f"Cover Letter — {job_title} at {company}",
            "item_type": "job",
            "item_id": job.get("id"),
            "target_role": job_title,
            "organization": company,
            "markdown": markdown_doc,
            "plain_text": plain_text,
            "matched_skills": matched_skills,
            "score": match_info.get("score", 85),
            "created_at": datetime.now().isoformat(),
        }

    @classmethod
    def generate_scholarship_statement(
        cls,
        profile: Dict[str, Any],
        opp: Dict[str, Any],
        tone: str = "academic",
    ) -> Dict[str, Any]:
        """Generates a tailored Statement of Purpose / Motivation Letter for an academic opportunity."""
        candidate_name = profile.get("full_name") or "Applicant"
        candidate_email = profile.get("email") or "applicant@example.com"
        candidate_degree = profile.get("degree") or "Bachelor of Science"
        candidate_bio = profile.get("bio") or ""

        opp_title = opp.get("title") or "the academic fellowship opportunity"
        highlights = opp.get("key_highlights") or []
        portal = opp.get("official_portal") or opp.get("apply_url") or "Application Portal"
        deadline = opp.get("deadline_date") or opp.get("deadline") or "Upcoming"

        match_info = ProfileMatcher.match_item(profile, opp, item_type="opportunity")
        matched_skills = match_info.get("matched_skills") or []
        skills_str = ", ".join(matched_skills[:3]) if matched_skills else "rigorous scientific methodology and modern computational tools"

        hl_summary = f"specifically your focus on {highlights[0].lower()}" if highlights else "your world-class research environment"

        today_str = datetime.now().strftime("%B %d, %Y")

        md_lines = [
            f"**{candidate_name}**",
            f"Candidate for Academic & Research Opportunities",
            f"{candidate_email} | Current Credential: {candidate_degree}",
            f"{today_str}\n",
            f"**Admissions Directorate & Academic Selection Committee**",
            f"Regarding: {opp_title}\n",
            f"**Subject: Statement of Purpose — Application for {opp_title}**\n",
            f"Dear Members of the Selection Committee,\n",
            (
                f"I am writing to formally submit my application for the prestigious **{opp_title}**. "
                f"Holding a background in {candidate_degree}, I have long dedicated my academic trajectory "
                f"toward addressing critical problems through structured inquiry, continuous learning, and rigorous technical execution. "
                f"This opportunity represents the ideal environment to further my academic development and contribute meaningfully to the program's vision."
            ),
            "",
            (
                f"My preparation is grounded in both foundational theory and practical computational acumen. "
                f"Through sustained work in **{skills_str}**, I have developed the ability to synthesize complex concepts into actionable solutions. "
                f"{candidate_bio.strip() if candidate_bio else 'My academic and professional journey has been defined by curiosity, self-directed research, and active collaboration across multidisciplinary teams.'}"
            ),
            "",
            (
                f"The distinctive character of {opp_title}—{hl_summary}—presents an unparalleled opportunity "
                f"to deepen my expertise under the mentorship of leading scholars. I am particularly eager to leverage my skills "
                f"to advance high-impact research initiatives, collaborate with international cohorts, and uphold the academic excellence of the institution."
            ),
            "",
            (
                f"Thank you for reviewing my application materials and dossier. I welcome the opportunity to discuss my qualifications, "
                f"research objectives, and enthusiasm for this program in greater detail during the interview phase."
            ),
            "",
            "With highest regards,",
            f"**{candidate_name}**",
            f"{candidate_email}",
        ]

        markdown_doc = "\n".join(md_lines)
        plain_text = markdown_doc.replace("**", "").replace("*", "")

        return {
            "title": f"Statement of Purpose — {opp_title}",
            "item_type": "opportunity",
            "item_id": opp.get("id"),
            "target_role": opp_title,
            "organization": "Academic Selection Committee",
            "markdown": markdown_doc,
            "plain_text": plain_text,
            "matched_skills": matched_skills,
            "score": match_info.get("score", 85),
            "created_at": datetime.now().isoformat(),
        }
