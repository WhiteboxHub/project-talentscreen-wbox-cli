"""Zero-token API-based ATS scanning module.

Inspired by career-ops, this efficiently discovers open roles directly
from ATS APIs without needing browser automation or LLMs.
"""

import logging
import urllib.parse
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from jobcli.profile.schemas import ATSType, Job


class ATSScanner:
    """Scanner for discovering jobs via ATS APIs/Feeds."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the scanner."""
        self.logger = logger or logging.getLogger(__name__)
        # Shared headers to mimic a normal browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }

    def scan_greenhouse(self, company_id: str) -> list[Job]:
        """Scan Greenhouse via their boards API."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{company_id}/jobs"
        return self._fetch_json_api(
            url=url,
            company_id=company_id,
            ats_type=ATSType.GREENHOUSE,
            parse_callback=self._parse_greenhouse_jobs,
        )

    def scan_lever(self, company_id: str) -> list[Job]:
        """Scan Lever via their postings API."""
        url = f"https://api.lever.co/v0/postings/{company_id}?mode=json"
        return self._fetch_json_api(
            url=url,
            company_id=company_id,
            ats_type=ATSType.LEVER,
            parse_callback=self._parse_lever_jobs,
        )

    def scan_ashby(self, company_id: str) -> list[Job]:
        """Scan Ashby via their public API."""
        url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": company_id},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id title locationName employmentType isRemote jobUrl presentation } } }"
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            postings = data.get("data", {}).get("jobBoard", {}).get("jobPostings", [])
            for post in postings:
                jobs.append(
                    Job(
                        url=post.get("jobUrl", ""),
                        title=post.get("title", ""),
                        company=company_id,
                        location=post.get("locationName", "Remote" if post.get("isRemote") else ""),
                        ats_type=ATSType.ASHBY,
                        scan_source="api"
                    )
                )
            return jobs
        except Exception as e:
            self.logger.error(f"Failed to scan Ashby for {company_id}: {str(e)}")
            return []

    def scan_bamboohr(self, company_id: str) -> list[Job]:
        """Scan BambooHR via XML feed."""
        url = f"https://{company_id}.bamboohr.com/jobs/view.php"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "xml")
            jobs = []
            for item in soup.find_all("item"):
                title_tag = item.find("title")
                link_tag = item.find("link")
                if title_tag and link_tag:
                    jobs.append(
                        Job(
                            url=link_tag.text.strip(),
                            title=title_tag.text.strip(),
                            company=company_id,
                            ats_type=ATSType.BAMBOO_HR,
                            scan_source="xml"
                        )
                    )
            return jobs
        except Exception as e:
            self.logger.error(f"Failed to scan BambooHR for {company_id}: {str(e)}")
            return []

    # --- Internal Helpers ---

    def _fetch_json_api(self, url: str, company_id: str, ats_type: ATSType, parse_callback) -> list[Job]:
        """Helper to fetch from generic GET JSON APIs."""
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return parse_callback(data, company_id)
        except Exception as e:
            self.logger.error(f"Failed to scan {ats_type.value} for {company_id}: {str(e)}")
            return []

    def _parse_greenhouse_jobs(self, data: dict, company: str) -> list[Job]:
        jobs = []
        for post in data.get("jobs", []):
            jobs.append(
                Job(
                    url=post.get("absolute_url", ""),
                    title=post.get("title", ""),
                    location=post.get("location", {}).get("name", ""),
                    company=company,
                    ats_type=ATSType.GREENHOUSE,
                    scan_source="api"
                )
            )
        return jobs

    def _parse_lever_jobs(self, data: list, company: str) -> list[Job]:
        jobs = []
        for post in data:
            jobs.append(
                Job(
                    url=post.get("hostedUrl", ""),
                    title=post.get("text", ""),
                    company=company,
                    location=post.get("categories", {}).get("location", ""),
                    ats_type=ATSType.LEVER,
                    scan_source="api"
                )
            )
        return jobs
