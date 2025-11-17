import logging
from typing import Dict, Any
from .schemas import AgentRequest, AgentResponse, ToolCall
from .tool_registry import ToolRegistry
from .agent_brain import AgentBrain

class PlannerAgent:
    """ReAct-style planner that orchestrates reasoning and tool execution."""
    
    def __init__(self, config: Dict, tool_registry: ToolRegistry, agent_brain: AgentBrain):
        self.config = config
        self.tool_registry = tool_registry
        self.brain = agent_brain
        self.max_steps = config.get("agentic", {}).get("planning_steps", 3)
        self.hitl_enabled = config.get("agentic", {}).get("hitl_enabled", True)
    
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute the ReAct planning loop.
        
        Loop:
        1. REASON: Parse intent with Agent Brain
        2. PLAN: Generate tool calls
        3. ACT: Execute tools
        4. OBSERVE: Collect results
        5. HITL: Ask for confirmation if needed
        """
        try:
            # Step 1: REASON - Parse intent
            logging.info(f"Processing query: {request.query}")
            intent, intent_reasoning = self.brain.parse_intent(request.query)
            logging.info(f"Detected intent: {intent.value}")
            
            # Step 2: PLAN - Generate tool calls
            tool_calls = self.brain.plan_tools(intent, request.query)
            logging.info(f"Planned {len(tool_calls)} tool calls")
            
            # Step 3 & 4: ACT & OBSERVE - Execute tools
            results = {}
            execution_success = True
            for idx, tool_call in enumerate(tool_calls):
                if idx >= self.max_steps:
                    logging.warning(f"Reached max planning steps ({self.max_steps})")
                    break
                
                try:
                    logging.info(f"Executing tool: {tool_call.tool.value}")
                    result = await self.tool_registry.execute_tool(
                        tool_call.tool.value,
                        **tool_call.parameters
                    )
                    results[tool_call.tool.value] = result
                    
                    if not result.get("success"):
                        execution_success = False
                        logging.warning(f"Tool {tool_call.tool.value} failed: {result.get('error')}")
                except Exception as e:
                    logging.error(f"Tool execution error: {e}", exc_info=True)
                    execution_success = False
                    results[tool_call.tool.value] = {"success": False, "error": str(e)}
            
            # Step 5: Evaluate and get confidence
            confidence, eval_message = self.brain.evaluate_results(results, intent)
            next_steps = self.brain.generate_next_steps(intent, results, confidence)
            
            # Determine if HITL confirmation is needed
            user_confirmation_needed = (
                request.require_confirmation and 
                self.hitl_enabled and 
                confidence < 0.85
            )
            
            # Build response
            response = AgentResponse(
                query=request.query,
                intent=intent.value,
                reasoning=f"{intent_reasoning}. {eval_message}",
                tool_calls=tool_calls,
                results=results,
                confidence=confidence,
                user_confirmation_needed=user_confirmation_needed,
                next_steps=next_steps,
                error=None if execution_success else "Some tools failed during execution"
            )
            
            logging.info(f"Agent response ready. Confidence: {confidence:.2f}")
            return response
            
        except Exception as e:
            logging.error(f"Planner agent error: {e}", exc_info=True)
            return AgentResponse(
                query=request.query,
                intent="error",
                reasoning="Failed to process request",
                tool_calls=[],
                results={},
                confidence=0.0,
                user_confirmation_needed=False,
                next_steps="Please try again or contact support",
                error=str(e)
            )
