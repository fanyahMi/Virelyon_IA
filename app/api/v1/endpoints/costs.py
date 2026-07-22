"""Consultation des coûts LLM cumulés par workspace (pour FINANCE)."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.security import verify_caller
from app.gateway.cost_tracker import cost_tracker

router = APIRouter(prefix="/costs", tags=["costs"], dependencies=[Depends(verify_caller)])


@router.get("/{workspace_id}")
def get_costs(workspace_id: UUID) -> dict:
    return {"workspace_id": str(workspace_id), **cost_tracker.get(workspace_id)}
