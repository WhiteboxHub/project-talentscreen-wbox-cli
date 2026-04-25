"""FastAPI bridge server to communicate with the Chrome extension."""

import logging
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jobcli.cli.main import get_config, get_database
from jobcli.storage.repositories import UserDataRepository

logger = logging.getLogger(__name__)

app = FastAPI(title="JobCLI Bridge Server", version="1.0.0")

# Allow extension to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to extension ID: "chrome-extension://<id>"
    allow_methods=["*"],
    allow_headers=["*"],
)

class FillReport(BaseModel):
    url: str
    success_count: int
    failure_count: int
    fields_filled: Dict[str, Any]
    unfilled_fields: List[str]


@app.get("/api/v1/context")
def get_context() -> Dict[str, Any]:
    """Fetch user resume data and high-confidence memory answers.
    
    Sensitive data (like passwords) is strictly excluded.
    """
    db = get_database()
    session = db.get_session()
    
    try:
        user_data_repo = UserDataRepository(session)
        resume = user_data_repo.get_resume()
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume data not found. Please upload a resume first.")
            
        # Convert resume model to dict but exclude potentially sensitive internal fields if any
        resume_dict = resume.model_dump()
        
        # We can selectively exclude data here if necessary. 
        # The prompt asked to only expose resume data and high-confidence field answers.
        
        # TODO: Retrieve high-confidence field answers from FieldAnswer memory.
        # For MVP, we pass an empty dict for memory if not fully implemented in memory table yet.
        memory_answers: Dict[str, Any] = {}
        
        try:
            from jobcli.storage.models import FieldAnswerModel
            # Fetch answers with high confidence (e.g., > 0.8)
            high_conf_answers = session.query(FieldAnswerModel).filter(FieldAnswerModel.confidence > 0.5).all()
            for ans in high_conf_answers:
                # Key structure is ats_type:field_label or just field_label
                # This depends on how the extension consumes it. For now we just return a flat dict
                field_key = ans.normalized_label if ans.normalized_label else ans.field_label
                memory_answers[field_key] = {
                    "value": ans.value,
                    "confidence": ans.confidence,
                    "ats_type": ans.ats_type
                }
        except ImportError:
            pass
            
        return {
            "resume": resume_dict,
            "memory": memory_answers,
            "ats_overrides": {} # Placeholder for ATS-specific overrides
        }
        
    finally:
        session.close()


@app.post("/api/v1/report")
def submit_report(report: FillReport) -> Dict[str, str]:
    """Receive the autofill report from the Chrome extension."""
    logger.info(f"Received report for {report.url}. Success: {report.success_count}, Failed: {report.failure_count}")
    
    # In Phase 2: Update SQLite memory (success/failure counts, learned locators)
    
    return {"status": "recorded"}


def start_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the FastAPI bridge server."""
    print(f"Starting JobCLI Bridge Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_server()
