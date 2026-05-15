"""Central constants for JobCLI."""

# Domains that are officially supported by the automation engine (Phase 1 & 2)
# These are used to calculate the "CLI Friendly" count.
SUPPORTED_DOMAINS = [
    "lever.co", 
    "greenhouse.io", 
    "ashbyhq.com", 
    "breezy.hr", 
    "workable.com",
    "recruitee.com", 
    "pinpointhq.com", 
    "rippling-ats.com", 
    "rippling.com", 
    "smartrecruiters.com",
    "jobvite.com", 
    "applytojob.com", 
    "linkedin.com",
    "bamboohr.com"
]

# Dashboard reporting settings
DASHBOARD_SUMMARY_DAYS = 7
REFERENCE_LINKS_COUNT = 100


def job_url_is_cli_friendly(url: str) -> bool:
    """True if the job URL is on a supported ATS host (excludes Workday portals)."""
    if not url:
        return False
    u = url.lower()
    if "myworkdayjobs.com" in u:
        return False
    return any(domain in u for domain in SUPPORTED_DOMAINS)
