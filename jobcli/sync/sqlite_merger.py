from sqlalchemy.orm import Session
from jobcli.storage.models import FieldAnswerModel, LearnedLocatorModel, SyncMetadataModel
from jobcli.core.schemas import ATSType, SelectorType

def merge_server_updates(session: Session, payload: dict) -> None:
    """Merge downloaded updates from the central sync server into the local SQLite database."""
    
    # Process field answers
    for fa_data in payload.get("field_answers", []):
        try:
            ats_val = ATSType(fa_data["ats_type"]) if fa_data.get("ats_type") else ATSType.UNKNOWN
        except ValueError:
            ats_val = ATSType.UNKNOWN

        existing = session.query(FieldAnswerModel).filter_by(
            ats_type=ats_val,
            normalized_label=fa_data["normalized_label"]
        ).first()

        if not existing:
            new_fa = FieldAnswerModel(
                ats_type=ats_val,
                normalized_label=fa_data["normalized_label"],
                field_label=fa_data.get("field_label", fa_data["normalized_label"]), # Use normalized as fallback
                value=fa_data["value"],
                success_count=fa_data["total_success"],
                failure_count=fa_data["total_failure"],
                confidence=fa_data["confidence"],
                source="auto" # Merged from server
            )
            session.add(new_fa)
        else:
            if fa_data["confidence"] > existing.confidence:
                existing.value = fa_data["value"]
                existing.success_count = fa_data["total_success"]
                existing.failure_count = fa_data["total_failure"]
                existing.confidence = fa_data["confidence"]
                existing.source = "auto"
                
    # Process locators
    for loc_data in payload.get("locators", []):
        # Ignore weak data from server
        if loc_data.get("total_success", 0) < 3:
            continue
            
        try:
            ats_val = ATSType(loc_data["ats_type"]) if loc_data.get("ats_type") else ATSType.UNKNOWN
        except ValueError:
            ats_val = ATSType.UNKNOWN
            
        try:
            sel_type = SelectorType(loc_data.get("selector_type", "css"))
        except ValueError:
            sel_type = SelectorType.CSS

        existing = session.query(LearnedLocatorModel).filter_by(
            ats_type=ats_val,
            purpose=loc_data["purpose"],
            selector=loc_data["selector"]
        ).first()

        if not existing:
            new_loc = LearnedLocatorModel(
                ats_type=ats_val,
                purpose=loc_data["purpose"],
                selector=loc_data["selector"],
                selector_type=sel_type,
                domain_pattern=loc_data.get("domain_pattern"),
                success_count=loc_data["total_success"],
                failure_count=loc_data["total_failure"],
                confidence_score=loc_data["confidence"],
                created_by="server_sync"
            )
            session.add(new_loc)
        else:
            if loc_data["confidence"] > existing.confidence_score:
                existing.success_count = loc_data["total_success"]
                existing.failure_count = loc_data["total_failure"]
                existing.confidence_score = loc_data["confidence"]
                if "domain_pattern" in loc_data:
                    existing.domain_pattern = loc_data["domain_pattern"]

