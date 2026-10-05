from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["catalog"])


class ApprovalDecision(BaseModel):
    reason: str | None = None


@router.get("/agents")
async def list_agents() -> dict:
    return {
        "agents": [
            {"id": "supervisor", "status": "planned"},
            {"id": "analytics", "status": "planned"},
            {"id": "document", "status": "planned"},
            {"id": "security", "status": "planned"},
            {"id": "recommendation", "status": "planned"},
        ]
    }


@router.get("/tools")
async def list_tools() -> dict:
    return {
        "tools": [
            {"name": "execute_read_query", "server": "analytics_mcp", "status": "planned"},
            {"name": "search_documents", "server": "document_mcp", "status": "planned"},
            {"name": "classify_data", "server": "security_mcp", "status": "planned"},
        ]
    }


@router.get("/security/events")
async def list_security_events() -> dict:
    return {
        "inspected": 0,
        "allowed": 0,
        "masked": 0,
        "blocked": 0,
        "human_approval": 0,
        "events": [],
    }


@router.get("/evaluations")
async def list_evaluations() -> dict:
    return {
        "rag": {"recall_at_5": None, "mrr": None},
        "answer_quality": {"faithfulness": None, "citation_accuracy": None},
        "agent_reliability": {"task_success": None, "tool_success": None},
        "security": {
            "prompt_injection_blocked": None,
            "pii_leakage": None,
            "unauthorized_tools_blocked": None,
        },
        "message": "Evaluation metrics are produced in Sprint 8.",
    }


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, _payload: ApprovalDecision | None = None) -> dict:
    raise HTTPException(
        status_code=501,
        detail=f"Human approval is scheduled for Sprint 6 (id={approval_id}).",
    )


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, _payload: ApprovalDecision | None = None) -> dict:
    raise HTTPException(
        status_code=501,
        detail=f"Human approval is scheduled for Sprint 6 (id={approval_id}).",
    )
