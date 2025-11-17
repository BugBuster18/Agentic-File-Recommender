import logging
from typing import Any, Dict, Callable
from pathlib import Path
from ..agents.file_agent import FileAgent
from ..agents.recommendation_agent import RecommendationAgent
from ..agents.activity_agent import ActivityAgent
from ..db import get_db

class ToolRegistry:
    """Registry of available tools (agents) that can be called."""
    
    def __init__(self, file_agent: FileAgent, recommendation_agent: RecommendationAgent, activity_agent: ActivityAgent, config: Dict):
        self.file_agent = file_agent
        self.recommendation_agent = recommendation_agent
        self.activity_agent = activity_agent
        self.config = config
        self.tools = self._register_tools()
        
    def _register_tools(self) -> Dict[str, Callable]:
        """Register all available tools."""
        return {
            "scan": self.tool_scan,
            "recommend": self.tool_recommend,
            "log_activity": self.tool_log_activity,
            "get_files": self.tool_get_files,
            "analyze_activity": self.tool_analyze_activity,
        }
    
    async def tool_scan(self, path: str) -> Dict[str, Any]:
        """Scan a directory for files."""
        try:
            await self.file_agent.scan_directory(path)
            return {
                "success": True,
                "message": f"Successfully scanned directory: {path}",
                "path": path
            }
        except Exception as e:
            logging.error(f"Scan tool error: {e}")
            return {"success": False, "error": str(e)}
    
    async def tool_recommend(self, file_path: str, limit: int = 5) -> Dict[str, Any]:
        """Get recommendations for a file."""
        try:
            recommendations = await self.recommendation_agent.recommend_similar(file_path, limit)
            return {
                "success": True,
                "file_path": file_path,
                "recommendations": recommendations,
                "count": len(recommendations)
            }
        except Exception as e:
            logging.error(f"Recommend tool error: {e}")
            return {"success": False, "error": str(e)}
    
    async def tool_log_activity(self, file_path: str) -> Dict[str, Any]:
        """Log file access activity."""
        try:
            success = await self.activity_agent.record_access(file_path)
            return {
                "success": success,
                "file_path": file_path,
                "message": f"Activity logged for {file_path}" if success else "Failed to log activity"
            }
        except Exception as e:
            logging.error(f"Log activity tool error: {e}")
            return {"success": False, "error": str(e)}
    
    async def tool_get_files(self, directory: str = None) -> Dict[str, Any]:
        """Get list of files in directory or scanned files."""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT path FROM files ORDER BY last_scanned DESC LIMIT 100")
                files = [row[0] for row in cursor.fetchall()]
            
            return {
                "success": True,
                "files": files,
                "count": len(files),
                "message": f"Found {len(files)} files in database"
            }
        except Exception as e:
            logging.error(f"Get files tool error: {e}")
            return {"success": False, "error": str(e)}
    
    async def tool_analyze_activity(self) -> Dict[str, Any]:
        """Analyze user activity patterns."""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                
                # Get most accessed files
                cursor.execute("""
                    SELECT f.path, fa.access_count, fa.last_accessed
                    FROM file_activity fa
                    JOIN files f ON fa.file_id = f.id
                    ORDER BY fa.access_count DESC
                    LIMIT 10
                """)
                most_accessed = [
                    {
                        "path": row[0],
                        "access_count": row[1],
                        "last_accessed": row[2]
                    }
                    for row in cursor.fetchall()
                ]
                
                # Get top co-occurrence pairs
                cursor.execute("""
                    SELECT f1.path, f2.path, co_count
                    FROM file_cooccurrence
                    JOIN files f1 ON file_id_1 = f1.id
                    JOIN files f2 ON file_id_2 = f2.id
                    ORDER BY co_count DESC
                    LIMIT 10
                """)
                top_pairs = [
                    {
                        "file1": row[0],
                        "file2": row[1],
                        "co_count": row[2]
                    }
                    for row in cursor.fetchall()
                ]
                
                return {
                    "success": True,
                    "most_accessed_files": most_accessed,
                    "top_cooccurrence_pairs": top_pairs,
                    "analysis": "Activity analysis complete"
                }
        except Exception as e:
            logging.error(f"Analyze activity tool error: {e}")
            return {"success": False, "error": str(e)}
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            tool_func = self.tools[tool_name]
            result = await tool_func(**kwargs)
            return result
        except Exception as e:
            logging.error(f"Tool execution error for {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def get_tool_descriptions(self) -> Dict[str, str]:
        """Get descriptions of all available tools."""
        return {
            "scan": "Scan a directory for files and index them",
            "recommend": "Get recommendations for a file based on similarity",
            "log_activity": "Log file access activity for workflow learning",
            "get_files": "Get list of scanned files from database",
            "analyze_activity": "Analyze user activity patterns and workflows"
        }
