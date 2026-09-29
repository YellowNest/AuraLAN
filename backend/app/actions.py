"""Foundation for future privileged changes; no executable privileged actions exist in the current release."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ActionStage(str, Enum):
    READ_CURRENT = "read_current"
    VALIDATE = "validate"
    BACKUP = "backup"
    PREVIEW = "preview"
    APPLY = "apply"
    HEALTH_CHECK = "health_check"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class ActionPreview(BaseModel):
    action_id: str
    stage: ActionStage = ActionStage.PREVIEW
    diff: str
    reversible: bool


class ActionRequest(BaseModel):
    """Marker contract only. Future action IDs must be whitelist-validated server-side."""

    action_id: str
