"""Unit tests for curated local jobs and scholarship scrapers."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bs4 import BeautifulSoup
from parsers.normalizer import (
    normalize_experience_level,
    normalize_job_category,
    normalize_country,
    normalize_academic_level,
    normalize_funding_type,
)
from parsers.job_parser import JobItem
from parsers.scholarship_parser import OpportunityItem
from storage.db import OpportunityDB


def test_normalizers():
    # Job Seniority
    assert normalize_experience_level("Fresh Graduate Junior Software Engineer") == "Junior / Entry"
    assert normalize_experience_level("Senior Lead Architect", "10+ years experience required") == "Senior / Lead"
    assert normalize_experience_level("Finance Officer", "3 years experience") == "Mid-Level"

    # Job Category
    assert normalize_job_category("React Native & Python Developer") == "IT & Software"
    assert normalize_job_category("Senior Auditor & Accountant") == "Finance & Accounting"
    assert normalize_job_category("Clinical Nurse Supervisor") == "Healthcare & Medical"

    # Scholarship Country & Degree
    assert normalize_country("DAAD Germany Research Scholarship") == "Germany"
    assert normalize_country("Caltech SURF in California, USA") == "USA"
    assert normalize_country("Addis Ababa University Graduate Grant, Ethiopia") == "Ethiopia"
    assert normalize_academic_level("Max Planck PhD Doctoral Fellowship") == "PhD / Doctoral"
    assert normalize_academic_level("Erasmus Mundus Joint Master Degree") == "Master's"
    assert normalize_academic_level("Oxford Postdoctoral Fellowship") == "Fellowship / Postdoc"
    assert normalize_funding_type("Fully Funded Masters with 100% Tuition and Flight") == "Fully Funded"


def test_db_filters(tmp_path):
    db_file = tmp_path / "test_curated.db"
    db = OpportunityDB(str(db_file))

    # Add a junior job and a senior job
    job1 = JobItem(
        title="Junior Backend Developer",
        company="Ethio Telecom",
        location="Addis Ababa",
        is_remote=False,
        salary="$500",
        url="https://example.com/job1",
        source="Reporter Jobs",
        experience_level="Junior / Entry",
        category="IT & Software",
        job_type="Full-time",
    )
    job2 = JobItem(
        title="Senior Cloud Architect",
        company="Global Tech",
        location="Remote",
        is_remote=True,
        salary="$120k",
        url="https://example.com/job2",
        source="RemoteOK",
        experience_level="Senior / Lead",
        category="IT & Software",
        job_type="Remote",
    )

    db.save_job(job1)
    db.save_job(job2)

    # Test filtering by experience level
    juniors = db.filter_jobs(experience_level="Junior / Entry")
    assert len(juniors) == 1
    assert juniors[0]["title"] == "Junior Backend Developer"

    seniors = db.filter_jobs(experience_level="Senior / Lead")
    assert len(seniors) == 1
    assert seniors[0]["title"] == "Senior Cloud Architect"

    # Add a scholarship
    opp = OpportunityItem(
        post_id="opp_101",
        channel_name="Scholars4Dev",
        post_url="https://example.com/opp1",
        date="2026-11-14",
        title="DAAD Study Scholarship in Germany for Ethiopian Students",
        deadline="31 Dec 2026",
        deadline_date="2026-12-31",
        apply_url="https://daad.de",
        is_opportunity=True,
        raw_text="Fully funded masters program in Germany",
        country="Germany",
        academic_level="Master's",
        funding_type="Fully Funded",
    )
    db.save_opportunity(opp)

    germany_opps = db.filter_opportunities(country="Germany")
    assert len(germany_opps) == 1
    assert "DAAD" in germany_opps[0]["title"]

    masters_opps = db.filter_opportunities(level="Master's")
    assert len(masters_opps) == 1


if __name__ == "__main__":
    import pathlib
    import tempfile

    print("Running test_normalizers()...")
    test_normalizers()
    print("✓ test_normalizers passed!")

    print("Running test_db_filters()...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_filters(pathlib.Path(tmp_dir))
    print("✓ test_db_filters passed!")
    print("All tests passed successfully!")
