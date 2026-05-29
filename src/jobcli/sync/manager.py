import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from jobcli.storage.models import Database, SyncMetadataModel
from jobcli.storage.repositories import JobRepository
from jobcli.sync import client, extractor, sqlite_merger
from jobcli.analytics.service import flush_usage_events

logger = logging.getLogger(__name__)

class SyncManager:
    """Orchestrates the synchronization process between local SQLite and Central DB."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._metadata = self._get_or_create_metadata()

    def _get_or_create_metadata(self) -> SyncMetadataModel:
        """Fetch or initialize the single sync_metadata row."""
        meta = self.session.query(SyncMetadataModel).filter_by(id=1).first()
        if not meta:
            meta = SyncMetadataModel(id=1, last_version="0.0.0", apps_since_sync=0)
            self.session.add(meta)
            self.session.commit()
        return meta

    def _sync_activity(self) -> Dict[str, Any]:
        """Sync recent job application activity to the central DB."""
        logger.info("Synchronizing job activity logs...")
        
        job_repo = JobRepository(self.session)
        since = self._metadata.last_sync_at
        
        # If never synced, look back 7 days
        if not since:
            from datetime import timedelta
            since = datetime.now() - timedelta(days=7)
            
        recent_jobs = job_repo.list_recent_activity(since=since)
        
        if not recent_jobs:
            logger.info("No recent job activity to sync.")
            return {"activity_sync_status": "skipped", "activity_count": 0}
            
        logger.info(f"Syncing {len(recent_jobs)} recent job activities...")
        
        # Convert models to dicts for the client
        logs = []
        for job in recent_jobs:
            logs.append({
                "title": job.title,
                "company": job.company,
                "status": job.status,
                "applied_at": job.updated_at.isoformat() if job.updated_at else datetime.now().isoformat()
            })
            
        try:
            sync_result = client.upload_activity_logs(logs)
            return {
                "activity_sync_status": sync_result.get("status", "success"),
                "activity_count": len(recent_jobs)
            }
        except Exception as e:
            logger.error(f"Activity sync failed: {e}")
            return {"activity_sync_status": "failed", "activity_error": str(e)}

    def perform_sync(self) -> Dict[str, Any]:
        """Execute a full upload/download sync cycle."""
        logger.info("Starting knowledge synchronization...")
        
        results = {
            "uploaded_answers": 0,
            "uploaded_locators": 0,
            "downloaded_updates": 0,
            "status": "success",
            "error": None
        }

        try:
            # 0. Sync Job Activity (Applications)
            activity_results = self._sync_activity()
            results.update(activity_results)

            # 1. Extract local knowledge (non-PII)
            answers = extractor.extract_field_answers(self.session)
            locators = extractor.extract_locators(self.session)
            
            results["uploaded_answers"] = len(answers)
            results["uploaded_locators"] = len(locators)

            # 2. Upload to Central DB (non-fatal — analytics flush must still run)
            if answers or locators:
                logger.info(f"Uploading {len(answers)} field patterns and {len(locators)} locators...")
                payload = {
                    "field_answers": answers,
                    "locators": locators
                }
                try:
                    client.upload_knowledge(payload)
                    results["knowledge_sync_status"] = "success"
                except Exception as e:
                    logger.error(f"Knowledge sync failed: {e}")
                    results["knowledge_sync_status"] = "failed"
                    results["knowledge_sync_error"] = str(e)

            # 3. Download global updates
            logger.info(f"Checking for updates from server (current version: {self._metadata.last_version})...")
            updates = client.download_updates(self._metadata.last_version)
            
            # 4. Merge updates into local SQLite
            new_version = updates.get("version")
            downloaded = 0
            if new_version and new_version != self._metadata.last_version:
                logger.info(f"Merging updates for version {new_version}...")
                sqlite_merger.merge_server_updates(self.session, updates)
                downloaded = len(updates.get("field_answers", [])) + len(updates.get("locators", []))
                results["downloaded_updates"] = downloaded
            
            # 5. Finalize metadata
            from jobcli.storage.repositories import SyncMetadataRepository
            SyncMetadataRepository(self.session).record_sync(
                version=new_version or self._metadata.last_version,
                downloaded_count=downloaded
            )

            usage_results = flush_usage_events(Database(str(self.session.bind.url)))
            results["usage_sync_status"] = usage_results.get("status")
            results["usage_event_count"] = usage_results.get("count", 0)

            logger.info("Synchronization complete.")
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            self.session.rollback()
            results["status"] = "failed"
            results["error"] = str(e)
            raise e

        return results
