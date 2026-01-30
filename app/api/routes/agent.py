"""
Agent Gateway API routes.

Provides a single entry point for AI agents to interact with the system.
Handles natural language instructions and orchestrates actions automatically.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.property import Property, PropertyContact
from app.models.agent_task import AgentTask, AgentTaskStep, TaskStatus, TaskType
from app.api.deps import get_current_user
from app.services.agent_gateway import get_agent_gateway


router = APIRouter(prefix="/agent", tags=["agent-gateway"])


# ============ Schemas ============

class AgentExecuteRequest(BaseModel):
    """Request to execute an agent task."""
    instruction: str = Field(..., description="Natural language instruction for the agent")
    property_id: Optional[int] = Field(None, description="Property context for the action")
    contact_id: Optional[int] = Field(None, description="Contact context for the action")
    auto_execute: bool = Field(True, description="Execute immediately (false = preview only)")


class AgentExecuteResponse(BaseModel):
    """Response from agent execution."""
    task_id: int
    status: TaskStatus
    status_message: Optional[str] = None
    task_type: TaskType
    parsed_intent: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    call_id: Optional[int] = None
    sms_id: Optional[int] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime


class AgentContextPreview(BaseModel):
    """Preview of context that would be used for an action."""
    property: Optional[Dict[str, Any]] = None
    contact: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    memories: List[Dict[str, Any]] = []
    recent_conversations: List[Dict[str, Any]] = []
    open_commitments: List[Dict[str, Any]] = []
    system_instructions: List[str] = []
    formatted_prompt: str = ""


class AgentTaskResponse(BaseModel):
    """Full task response."""
    id: int
    task_type: TaskType
    instruction: str
    status: TaskStatus
    status_message: Optional[str] = None
    parsed_intent: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    call_id: Optional[int] = None
    sms_id: Optional[int] = None
    property_id: Optional[int] = None
    contact_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentTaskList(BaseModel):
    """List of agent tasks."""
    tasks: List[AgentTaskResponse]
    total: int


# Tool definition for function calling
class ToolDefinition(BaseModel):
    """OpenAI/Claude compatible tool definition."""
    name: str
    description: str
    parameters: Dict[str, Any]


# ============ Helper Functions ============

async def verify_property_access(
    property_id: int,
    user: User,
    db: AsyncSession
) -> Property:
    """Verify user has access to property."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )

    if user.role != UserRole.ADMIN and property.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this property"
        )

    return property


async def verify_contact_access(
    contact_id: int,
    user: User,
    db: AsyncSession
) -> PropertyContact:
    """Verify user has access to contact's property."""
    result = await db.execute(
        select(PropertyContact).where(PropertyContact.id == contact_id)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    await verify_property_access(contact.property_id, user, db)
    return contact


# ============ Main Execution Endpoint ============

@router.post("/execute", response_model=AgentExecuteResponse)
async def execute_agent_task(
    request: AgentExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute an agent task from natural language instruction.

    This is the main entry point for AI agents. It:
    1. Parses the instruction to understand intent
    2. Gathers all relevant context (memories, preferences, history)
    3. Executes the appropriate action (call, SMS, etc.)
    4. Returns the result

    Examples:
    - "Call John about the property inspection"
    - "Send a text to Sarah confirming our meeting tomorrow"
    - "Follow up with the contractor about the repair estimate"
    """
    # Verify access
    if request.property_id:
        await verify_property_access(request.property_id, current_user, db)
    if request.contact_id:
        await verify_contact_access(request.contact_id, current_user, db)

    gateway = get_agent_gateway(db)

    if not gateway.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent gateway not available (Anthropic not configured)"
        )

    try:
        task = await gateway.execute(
            instruction=request.instruction,
            property_id=request.property_id,
            contact_id=request.contact_id,
            user_id=current_user.id,
            auto_execute=request.auto_execute
        )

        import json
        return AgentExecuteResponse(
            task_id=task.id,
            status=task.status,
            status_message=task.status_message,
            task_type=task.task_type,
            parsed_intent=json.loads(task.parsed_intent) if task.parsed_intent else None,
            result_summary=task.result_summary,
            result_data=json.loads(task.result_data) if task.result_data else None,
            call_id=task.call_id,
            sms_id=task.sms_id,
            execution_time_ms=task.execution_time_ms,
            created_at=task.created_at
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}"
        )


# ============ Context Preview ============

@router.post("/context/preview", response_model=AgentContextPreview)
async def preview_agent_context(
    property_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    purpose: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview the context that would be injected for an agent action.

    Useful for debugging and understanding what the AI will know.
    """
    if property_id:
        await verify_property_access(property_id, current_user, db)
    if contact_id:
        await verify_contact_access(contact_id, current_user, db)

    gateway = get_agent_gateway(db)
    context = await gateway.build_context(
        property_id=property_id,
        contact_id=contact_id,
        purpose=purpose
    )

    formatted = gateway.format_context_for_prompt(context)

    return AgentContextPreview(
        property=context.get("property"),
        contact=context.get("contact"),
        preferences=context.get("preferences"),
        memories=context.get("memories", []),
        recent_conversations=context.get("recent_conversations", []),
        open_commitments=context.get("open_commitments", []),
        system_instructions=context.get("system_instructions", []),
        formatted_prompt=formatted
    )


# ============ Intent Parsing ============

@router.post("/parse")
async def parse_instruction(
    instruction: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Parse a natural language instruction without executing.

    Returns the parsed intent showing how the system understood the request.
    """
    gateway = get_agent_gateway(db)

    if not gateway.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent gateway not available"
        )

    intent = await gateway.parse_intent(instruction)
    return {
        "instruction": instruction,
        "parsed_intent": intent
    }


# ============ Task Management ============

@router.get("/tasks", response_model=AgentTaskList)
async def list_agent_tasks(
    property_id: Optional[int] = None,
    status_filter: Optional[TaskStatus] = None,
    limit: int = 50,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List agent tasks for the current user."""
    query = select(AgentTask).where(AgentTask.initiated_by_id == current_user.id)

    if property_id:
        await verify_property_access(property_id, current_user, db)
        query = query.where(AgentTask.property_id == property_id)

    if status_filter:
        query = query.where(AgentTask.status == status_filter)

    query = query.order_by(AgentTask.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()

    import json
    task_responses = []
    for t in tasks:
        task_responses.append(AgentTaskResponse(
            id=t.id,
            task_type=t.task_type,
            instruction=t.instruction,
            status=t.status,
            status_message=t.status_message,
            parsed_intent=json.loads(t.parsed_intent) if t.parsed_intent else None,
            result_summary=t.result_summary,
            result_data=json.loads(t.result_data) if t.result_data else None,
            call_id=t.call_id,
            sms_id=t.sms_id,
            property_id=t.property_id,
            contact_id=t.contact_id,
            started_at=t.started_at,
            completed_at=t.completed_at,
            execution_time_ms=t.execution_time_ms,
            created_at=t.created_at,
            updated_at=t.updated_at
        ))

    return AgentTaskList(tasks=task_responses, total=len(task_responses))


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific agent task."""
    result = await db.execute(
        select(AgentTask).where(AgentTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.initiated_by_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    import json
    return AgentTaskResponse(
        id=task.id,
        task_type=task.task_type,
        instruction=task.instruction,
        status=task.status,
        status_message=task.status_message,
        parsed_intent=json.loads(task.parsed_intent) if task.parsed_intent else None,
        result_summary=task.result_summary,
        result_data=json.loads(task.result_data) if task.result_data else None,
        call_id=task.call_id,
        sms_id=task.sms_id,
        property_id=task.property_id,
        contact_id=task.contact_id,
        started_at=task.started_at,
        completed_at=task.completed_at,
        execution_time_ms=task.execution_time_ms,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_agent_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending agent task."""
    result = await db.execute(
        select(AgentTask).where(AgentTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.initiated_by_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task"
        )

    if task.status not in [TaskStatus.PENDING, TaskStatus.WAITING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel pending or waiting tasks"
        )

    task.status = TaskStatus.CANCELLED
    task.status_message = "Cancelled by user"
    await db.commit()
    return None


# ============ Tool Registry ============

@router.get("/tools", response_model=List[ToolDefinition])
async def get_agent_tools(
    current_user: User = Depends(get_current_user)
):
    """
    Get available agent tools in function-calling format.

    Returns tool definitions compatible with OpenAI/Claude function calling.
    """
    return [
        ToolDefinition(
            name="execute_task",
            description="Execute an agent task from natural language instruction. Automatically gathers context and executes actions.",
            parameters={
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "Natural language instruction (e.g., 'Call John about the inspection')"
                    },
                    "property_id": {
                        "type": "integer",
                        "description": "Optional property ID for context"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Optional contact ID for context"
                    }
                },
                "required": ["instruction"]
            }
        ),
        ToolDefinition(
            name="get_context",
            description="Get the current context (memories, preferences, history) for a property or contact",
            parameters={
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "integer",
                        "description": "Property ID"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Contact ID"
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional semantic search query for relevant memories"
                    }
                }
            }
        ),
        ToolDefinition(
            name="remember",
            description="Store a fact, preference, or commitment about a contact or property",
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The memory content to store"
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["fact", "preference", "commitment", "context"],
                        "description": "Type of memory"
                    },
                    "property_id": {
                        "type": "integer",
                        "description": "Property this memory relates to"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Contact this memory relates to"
                    }
                },
                "required": ["content", "memory_type"]
            }
        ),
        ToolDefinition(
            name="search_memories",
            description="Search memories using semantic similarity",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "property_id": {
                        "type": "integer",
                        "description": "Filter by property"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Filter by contact"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)"
                    }
                },
                "required": ["query"]
            }
        ),
        ToolDefinition(
            name="make_call",
            description="Initiate an AI-powered phone call to a contact",
            parameters={
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "integer",
                        "description": "Property ID"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Contact ID (will use their phone number)"
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number (if not using contact)"
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Purpose of the call"
                    }
                },
                "required": ["purpose"]
            }
        ),
        ToolDefinition(
            name="send_sms",
            description="Send an SMS message to a contact",
            parameters={
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "integer",
                        "description": "Property ID"
                    },
                    "contact_id": {
                        "type": "integer",
                        "description": "Contact ID"
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number (if not using contact)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to send"
                    }
                },
                "required": ["message"]
            }
        )
    ]


# ============ Quick Actions ============

@router.post("/call", response_model=AgentExecuteResponse)
async def quick_call(
    property_id: int,
    contact_id: int,
    purpose: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Quick endpoint to make a call with auto-context.

    Shortcut for execute with task_type=call.
    """
    await verify_property_access(property_id, current_user, db)
    await verify_contact_access(contact_id, current_user, db)

    gateway = get_agent_gateway(db)
    task = await gateway.execute(
        instruction=f"Call the contact about: {purpose}",
        property_id=property_id,
        contact_id=contact_id,
        user_id=current_user.id
    )

    import json
    return AgentExecuteResponse(
        task_id=task.id,
        status=task.status,
        status_message=task.status_message,
        task_type=task.task_type,
        parsed_intent=json.loads(task.parsed_intent) if task.parsed_intent else None,
        result_summary=task.result_summary,
        result_data=json.loads(task.result_data) if task.result_data else None,
        call_id=task.call_id,
        sms_id=task.sms_id,
        execution_time_ms=task.execution_time_ms,
        created_at=task.created_at
    )


@router.post("/sms", response_model=AgentExecuteResponse)
async def quick_sms(
    property_id: int,
    contact_id: int,
    message: Optional[str] = None,
    purpose: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Quick endpoint to send SMS with auto-context.

    If message is not provided, AI will generate one based on purpose.
    """
    await verify_property_access(property_id, current_user, db)
    await verify_contact_access(contact_id, current_user, db)

    instruction = message if message else f"Send a text message about: {purpose or 'following up'}"

    gateway = get_agent_gateway(db)
    task = await gateway.execute(
        instruction=instruction,
        property_id=property_id,
        contact_id=contact_id,
        user_id=current_user.id
    )

    import json
    return AgentExecuteResponse(
        task_id=task.id,
        status=task.status,
        status_message=task.status_message,
        task_type=task.task_type,
        parsed_intent=json.loads(task.parsed_intent) if task.parsed_intent else None,
        result_summary=task.result_summary,
        result_data=json.loads(task.result_data) if task.result_data else None,
        call_id=task.call_id,
        sms_id=task.sms_id,
        execution_time_ms=task.execution_time_ms,
        created_at=task.created_at
    )
