from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import yaml
import logging
from pathlib import Path
from .db import init_db, is_db_initialized, get_db
from .agents.file_agent import FileAgent
from .agents.recommendation_agent import RecommendationAgent
from .agents.activity_agent import ActivityAgent
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="Agentic File Recommender")

# Load config with proper error handling
try:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
        
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    if not config:
        raise ValueError("Config file is empty")
        
    required_keys = ["scan", "embeddings", "ranking"]
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ValueError(f"Missing required config keys: {missing_keys}")
        
except Exception as e:
    logging.error(f"Config loading error: {e}")
    raise RuntimeError(f"Failed to load config: {e}")

# Initialize database if needed
try:
    if not is_db_initialized():
        logging.info("Database not initialized, initializing now...")
        init_db()
        logging.info("Database initialized successfully")
    else:
        logging.info("Database already initialized")
except RuntimeError as e:
    logging.error(f"Failed to initialize database: {e}")
    logging.info("Attempting to reinitialize database...")
    try:
        init_db(force=True)
    except Exception as e2:
        logging.error(f"Database reinitialization failed: {e2}", exc_info=True)
        raise
except Exception as e:
    logging.error(f"Unexpected error during database initialization: {e}", exc_info=True)
    raise

# Initialize agents
recommendation_agent = RecommendationAgent(config)
file_agent = FileAgent(config)
file_agent.set_recommendation_agent(recommendation_agent)
activity_agent = ActivityAgent(config)

# Import agentic layer
from .agentic import ToolRegistry, AgentBrain, PlannerAgent, AgentRequest, AgentResponse

# Initialize agentic components (after existing agent initialization)
tool_registry = ToolRegistry(file_agent, recommendation_agent, activity_agent, config)
agent_brain = AgentBrain(config)
planner_agent = PlannerAgent(config, tool_registry, agent_brain)

@app.get("/health")
async def health_check():
    return {"status": "ok", "config_loaded": bool(config)}

# @app.post("/scan")
@app.get("/scan")
async def scan_directory(path: str = None):
    try:
        root = path or config["scan"]["default_roots"][0]
        logging.info(f"Starting scan of directory: {root}")
        await file_agent.scan_directory(root)
        return {"status": "ok", "message": f"Scanned {root}"}
    except Exception as e:
        logging.error(f"Scan error: {e}")
        raise HTTPException(500, str(e))

@app.post("/activity/log")
async def log_activity(path: str):
    """Log file access event."""
    if not Path(path).exists():
        raise HTTPException(404, "File not found")
        
    success = await activity_agent.record_access(path)
    if not success:
        raise HTTPException(500, "Failed to log activity")
        
    return {"status": "logged", "path": path}

@app.get("/recommend_from_file")
async def recommend_from_file(path: str, limit: int = 5):
    try:
        # normalize and resolve path without strict existence check
        raw = path or ""
        p = Path(raw).expanduser()
        try:
            abs_path = p.resolve(strict=False)
        except Exception:
            abs_path = p

        # If file doesn't exist on disk, try to find record in DB (case-insensitive)
        if not abs_path.exists():
            logging.info(f"File not found on disk: {abs_path}. Trying DB lookup.")
            db_path = None
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    # try exact match first
                    cursor.execute("SELECT path FROM files WHERE path = ?", (str(abs_path),))
                    r = cursor.fetchone()
                    if r:
                        db_path = r[0]
                    else:
                        # fallback: case-insensitive match using lower()
                        cursor.execute("SELECT path FROM files")
                        for row in cursor.fetchall():
                            try:
                                candidate = row[0]
                                if candidate and os.path.normcase(candidate) == os.path.normcase(str(abs_path)):
                                    db_path = candidate
                                    break
                            except Exception:
                                continue
            except Exception as e:
                logging.error(f"DB lookup error for path {abs_path}: {e}", exc_info=True)

            if db_path:
                logging.info(f"Using DB path for recommendation: {db_path}")
                abs_path = Path(db_path)
            else:
                raise HTTPException(status_code=404, detail=f"File not found (disk and DB): {path}")

        if not abs_path.is_file():
            raise HTTPException(status_code=400, detail="Path must be a file, not a directory")

        # optional extension check, but tolerate if not listed
        allowed = config.get("scan", {}).get("allowed_exts", [])
        if allowed and abs_path.suffix.lower() not in allowed:
            logging.warning(f"File type {abs_path.suffix} not in allowed_exts, continuing (may still recommend)")
            # do not raise; allow recommendation for non-listed types if DB contains content

        # Log access (activity) before recommending
        try:
            await activity_agent.record_access(str(abs_path))
        except Exception as e:
            logging.warning(f"Failed to log activity for {abs_path}: {e}")

        results = await recommendation_agent.recommend_similar(str(abs_path), limit)
        return {"recommendations": results}
    except HTTPException as he:
        logging.error(f"Recommendation error: {he.detail}")
        raise he
    except Exception as e:
        logging.error(f"Recommendation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
async def list_files():
    """List all scanned files in the system."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM files")
            files = [row[0] for row in cursor.fetchall()]
            return {"files": files}
    except Exception as e:
        logging.error(f"Error listing files: {e}")
        raise HTTPException(500, str(e))

@app.post("/agent_query", response_model=AgentResponse)
async def agent_query(request: AgentRequest):
    """
    Natural language query endpoint for agentic planning.
    
    Example:
    POST /agent_query
    {
        "query": "Find Python files I've worked on recently",
        "require_confirmation": true,
        "max_planning_steps": 3
    }
    """
    try:
        logging.info(f"Agent query received: {request.query}")
        result = await planner_agent.execute(request)
        return result
    except Exception as e:
        logging.error(f"Agent query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
