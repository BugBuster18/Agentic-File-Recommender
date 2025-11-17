import logging
from typing import Dict, List, Tuple
from .schemas import IntentType, ToolCall, ToolName
import re

class AgentBrain:
    """LLM-based reasoning layer for intent parsing and planning."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.llm_model = config.get("agentic", {}).get("llm_model", "llama2")
        self.use_local_llm = config.get("agentic", {}).get("use_local_llm", True)
        
    def parse_intent(self, query: str) -> Tuple[IntentType, str]:
        """
        Parse user intent from natural language query.
        Uses heuristic-based parsing (lightweight, no external LLM required).
        """
        query_lower = query.lower()
        
        # Intent matching heuristics
        if any(keyword in query_lower for keyword in ["scan", "index", "search directory"]):
            return IntentType.SCAN_DIRECTORY, "User wants to scan and index files"
        
        if any(keyword in query_lower for keyword in ["related", "similar", "find files"]):
            return IntentType.FIND_RELATED, "User wants to find files related to a specific file"
        
        if any(keyword in query_lower for keyword in ["recent", "last week", "yesterday", "new files"]):
            return IntentType.GET_RECENT, "User wants to see recently accessed or modified files"
        
        if any(keyword in query_lower for keyword in ["workflow", "together", "co-occurrence", "pattern"]):
            return IntentType.ANALYZE_WORKFLOW, "User wants to analyze workflow and file patterns"
        
        if any(keyword in query_lower for keyword in ["filter", "find", "search"]):
            return IntentType.FILTER_FILES, "User wants to filter or search files"
        
        return IntentType.UNKNOWN, "Could not determine intent"
    
    def plan_tools(self, intent: IntentType, query: str) -> List[ToolCall]:
        """
        Generate a plan of tools to execute based on intent.
        """
        tools = []
        reasoning = "Tool selection based on intent analysis"
        
        if intent == IntentType.SCAN_DIRECTORY:
            # Extract path from query
            path = self._extract_path(query) or "."
            tools.append(ToolCall(
                tool=ToolName.SCAN,
                parameters={"path": path},
                reasoning="Scanning directory to index files"
            ))
        
        elif intent == IntentType.FIND_RELATED:
            # Extract file path from query
            file_path = self._extract_file_path(query)
            if file_path:
                tools.append(ToolCall(
                    tool=ToolName.RECOMMEND,
                    parameters={"file_path": file_path, "limit": 5},
                    reasoning="Finding files related to the specified file"
                ))
            else:
                # First get files list, then show options
                tools.append(ToolCall(
                    tool=ToolName.GET_FILES,
                    parameters={},
                    reasoning="Getting available files to find related ones"
                ))
        
        elif intent == IntentType.GET_RECENT:
            # First get files, could be enhanced with filtering
            tools.append(ToolCall(
                tool=ToolName.GET_FILES,
                parameters={},
                reasoning="Getting recently accessed files from database"
            ))
        
        elif intent == IntentType.ANALYZE_WORKFLOW:
            tools.append(ToolCall(
                tool=ToolName.ANALYZE_ACTIVITY,
                parameters={},
                reasoning="Analyzing workflow patterns and co-occurrence"
            ))
        
        elif intent == IntentType.FILTER_FILES:
            tools.append(ToolCall(
                tool=ToolName.GET_FILES,
                parameters={},
                reasoning="Getting files to apply filtering"
            ))
        
        else:
            # Default: get files
            tools.append(ToolCall(
                tool=ToolName.GET_FILES,
                parameters={},
                reasoning="Unknown intent, retrieving available files"
            ))
        
        return tools
    
    def _extract_path(self, query: str) -> str:
        """Extract file path from query."""
        # Simple heuristic: look for quoted strings or common path patterns
        import re
        
        # Look for quoted paths
        quoted = re.findall(r'"([^"]*)"', query)
        if quoted:
            return quoted[0]
        
        # Look for paths starting with ./ or /
        paths = re.findall(r'[\./][^\s]+', query)
        if paths:
            return paths[0]
        
        return None
    
    def _extract_file_path(self, query: str) -> str:
        """Extract file path for recommendation from query."""
        # Similar to _extract_path
        return self._extract_path(query)
    
    def evaluate_results(self, results: Dict, intent: IntentType) -> Tuple[float, str]:
        """
        Evaluate tool execution results and return confidence score.
        confidence: 0.0 to 1.0
        """
        if not results:
            return 0.0, "No results returned"
        
        if results.get("error"):
            return 0.3, f"Error occurred: {results['error']}"
        
        if not results.get("success"):
            return 0.4, "Tool execution was not successful"
        
        # Calculate confidence based on result quality
        if intent == IntentType.SCAN_DIRECTORY:
            if results.get("message"):
                return 0.95, "Successfully scanned directory"
        
        elif intent == IntentType.FIND_RELATED:
            recs = results.get("recommendations", [])
            if len(recs) > 0:
                return 0.9, f"Found {len(recs)} related files"
            else:
                return 0.6, "No related files found"
        
        elif intent == IntentType.GET_RECENT:
            files = results.get("files", [])
            if len(files) > 0:
                return 0.85, f"Retrieved {len(files)} files"
            else:
                return 0.5, "No files in database"
        
        elif intent == IntentType.ANALYZE_WORKFLOW:
            if results.get("most_accessed_files") or results.get("top_cooccurrence_pairs"):
                return 0.9, "Successfully analyzed workflow patterns"
            else:
                return 0.6, "Limited activity data available"
        
        return 0.7, "Results retrieved successfully"
    
    def generate_next_steps(self, intent: IntentType, results: Dict, confidence: float) -> str:
        """Generate suggestions for next steps based on results."""
        if confidence < 0.5:
            return "Please provide more specific information or check the system status"
        
        if intent == IntentType.SCAN_DIRECTORY:
            return "You can now get recommendations for any scanned file"
        
        elif intent == IntentType.FIND_RELATED:
            recs_count = len(results.get("recommendations", []))
            if recs_count > 0:
                return f"Review the {recs_count} related files, or refine your search criteria"
            else:
                return "Try scanning more files or searching for different content"
        
        elif intent == IntentType.GET_RECENT:
            files_count = len(results.get("files", []))
            return f"You can log activity on any of these {files_count} files to build workflow patterns"
        
        elif intent == IntentType.ANALYZE_WORKFLOW:
            return "Based on workflow analysis, you can optimize your file organization"
        
        return "Explore other queries or refine your current search"
