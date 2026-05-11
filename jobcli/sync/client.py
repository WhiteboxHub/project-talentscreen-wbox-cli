import os
import requests
import logging
from typing import Dict, Any, List, Optional
from datetime import date

logger = logging.getLogger(__name__)

class SyncClient:
    def __init__(self):
        self.base_url = self._get_server_url()
        self.token = None
        self.candidate_id = None
        self.job_types = []

    def _get_server_url(self) -> str:
        """Get the FastAPI server URL from environment or use default production URL."""
        url = os.getenv("JOBCLI_SYNC_SERVER_URL")
        if not url:
            url = os.getenv("NEXT_PUBLIC_API_URL")
        if not url:
            url = "https://whitebox-learning.com/api"
        
        return url.rstrip("/")

    def login(self) -> bool:
        """Authenticate with the central server and store token/candidate_id."""
        username = os.getenv("JOBCLI_USERNAME")
        password = os.getenv("JOBCLI_PASSWORD")
        
        if not username or not password:
            logger.warning("JOBCLI_USERNAME or JOBCLI_PASSWORD not set. Sync will be limited.")
            return False
            
        login_url = f"{self.base_url}/login"
        
        try:
            response = requests.post(
                login_url, 
                data={"username": username, "password": password},
                timeout=10
            )
            response.raise_for_status()
            token_data = response.json()
            self.token = token_data.get("access_token")
            self.candidate_id = token_data.get("candidate_id")
            
            if self.token:
                logger.info(f"Successfully authenticated as {username} (Candidate ID: {self.candidate_id})")
                return True
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            
        return False

    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers. Logs in if token is missing."""
        if not self.token:
            self.login()
            
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def fetch_job_types(self) -> List[Dict[str, Any]]:
        """Fetch available job types from the server for mapping."""
        headers = self.get_auth_headers()
        if not headers:
            return []
            
        url = f"{self.base_url}/job-types"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            self.job_types = response.json()
            return self.job_types
        except Exception as e:
            logger.error(f"Failed to fetch job types: {str(e)}")
            return []

    def map_job_to_type_id(self, job_title: str) -> Optional[int]:
        """Try to map a job title to an existing job_type_id."""
        if not self.job_types:
            self.fetch_job_types()
            
        if not self.job_types:
            return None
            
        # 1. Exact match
        for jt in self.job_types:
            if jt["name"].lower() == job_title.lower():
                return jt["id"]
                
        # 2. Partial match
        for jt in self.job_types:
            if jt["name"].lower() in job_title.lower() or job_title.lower() in jt["name"].lower():
                return jt["id"]
                
        # 3. Default to "Automation" if it exists
        for jt in self.job_types:
            if "automation" in jt["name"].lower():
                return jt["id"]
                
        # 4. Just return the first one as fallback if any exist
        return self.job_types[0]["id"] if self.job_types else None

    def upload_knowledge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upload field answers and locators to the central server."""
        url = f"{self.base_url}/sync_cli/knowledge_sync"
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def download_updates(self, current_version: str) -> Dict[str, Any]:
        """Download the latest aggregated locators and field answers."""
        url = f"{self.base_url}/sync_cli/knowledge_updates"
        params = {"current_version": current_version}
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def upload_activity_logs(self, raw_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Upload job activity logs to the central server."""
        if not raw_logs:
            return {"status": "skipped", "message": "No logs to upload"}
            
        headers = self.get_auth_headers()
        if "Authorization" not in headers:
            return {"status": "error", "message": "Authentication required for activity sync"}
            
        if not self.candidate_id:
            return {"status": "error", "message": "Candidate ID not found for current user"}

        formatted_logs = []
        for log in raw_logs:
            job_type_id = self.map_job_to_type_id(log.get("title", ""))
            if not job_type_id:
                logger.warning(f"Could not map job '{log.get('title')}' to any backend job type. Skipping.")
                continue
                
            formatted_logs.append({
                "job_id": job_type_id,
                "candidate_id": self.candidate_id,
                "activity_date": date.today().isoformat(),
                "activity_count": 1,
                "notes": f"Applied via JobCLI: {log.get('title')} at {log.get('company')}. Status: {log.get('status')}"
            })
            
        if not formatted_logs:
            return {"status": "skipped", "message": "No valid logs after mapping"}

        url = f"{self.base_url}/job_activity_logs/bulk"
        headers["Content-Type"] = "application/json"
        
        payload = {"logs": formatted_logs}
        
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()

# Singleton instance for easy access
_client = None

def get_client():
    global _client
    if _client is None:
        _client = SyncClient()
    return _client

# Legacy function wrappers for backward compatibility
def upload_knowledge(payload: Dict[str, Any]) -> Dict[str, Any]:
    return get_client().upload_knowledge(payload)

def download_updates(current_version: str) -> Dict[str, Any]:
    return get_client().download_updates(current_version)

def upload_activity_logs(logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return get_client().upload_activity_logs(logs)
