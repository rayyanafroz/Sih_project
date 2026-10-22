from sqlalchemy.orm import Session

from .models import AuditLog, User


def log(db: Session, action: str, summary: str, *, actor: User | None = None, entity_type: str | None = None,
        entity_id=None, application_id: int | None = None, details: dict | None = None) -> AuditLog:
    """Append an audit entry. The caller owns the transaction (commit happens with the action itself)."""
    entry = AuditLog(
        actor_type="user" if actor else "system",
        actor_id=actor.id if actor else None,
        actor_name=actor.name if actor else "VerifyAI system",
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        application_id=application_id,
        summary=summary,
        details=details or {},
    )
    db.add(entry)
    return entry
