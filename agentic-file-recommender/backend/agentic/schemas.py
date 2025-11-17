from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from enum import Enum

class ToolName(str, Enum):
    """Available tools in the registry."""
    SCAN = "scan"
    RECOMMEND = "recommend"
    LOG_ACTIVITY = "log_activity"
    GET_FILES = "get_files"
    ANALYZE_ACTIVITY = "analyze_activity"

class ToolCall(BaseModel):
    """Represents a single tool call."""
    tool: ToolName
    parameters: Dict[str, Any]
    reasoning: str

class AgentRequest(BaseModel):
    """User request to the agent."""
    query: str
    require_confirmation: bool = True
    max_planning_steps: int = 3

class AgentResponse(BaseModel):
    """Agent response with planning trace."""
    query: str
    intent: str
    reasoning: str
    tool_calls: List[ToolCall]
    results: Dict[str, Any]
    confidence: float
    user_confirmation_needed: bool
    next_steps: Optional[str] = None
    error: Optional[str] = None

class IntentType(str, Enum):
    """Types of user intents."""
    SCAN_DIRECTORY = "scan_directory"
    FIND_RELATED = "find_related_files"
    GET_RECENT = "get_recent_files"
    ANALYZE_WORKFLOW = "analyze_workflow"
    FILTER_FILES = "filter_files"
    UNKNOWN = "unknown"
