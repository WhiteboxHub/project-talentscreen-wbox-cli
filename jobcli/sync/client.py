import os
import requests
from typing import Dict, Any

def get_server_url() -> str:
    """Get the FastAPI server URL from environment or use default localhost."""
    return os.getenv("JOBCLI_SYNC_SERVER_URL", "http://localhost:8000")

def upload_knowledge(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Upload field answers and locators to the central server."""
    url = f"{get_server_url()}/api/sync_cli/knowledge_sync"
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def download_updates(current_version: str) -> Dict[str, Any]:
    """Download the latest aggregated locators and field answers."""
    url = f"{get_server_url()}/api/sync_cli/knowledge_updates"
    params = {
        "current_version": current_version
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()
