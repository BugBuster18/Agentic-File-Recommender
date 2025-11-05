from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import yaml
import logging
from pathlib import Path
from .agents.file_agent import FileAgent
from .agents.recommendation_agent import RecommendationAgent
from .agents.activity_agent import ActivityAgent
from .db import init_db, is_db_initialized, get_db

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
if not is_db_initialized():
    try:
        init_db()
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        raise RuntimeError("Database initialization failed")

# Initialize agents
recommendation_agent = RecommendationAgent(config)
file_agent = FileAgent(config)
file_agent.set_recommendation_agent(recommendation_agent)
activity_agent = ActivityAgent(config)

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
        if not Path(path).exists():
            raise HTTPException(404, "File not found")
            
        # Log the access
        await activity_agent.record_access(path)
        
        # Get recommendations
        results = await recommendation_agent.recommend_similar(path, limit)
        return {"recommendations": results}
    except Exception as e:
        logging.error(f"Recommendation error: {e}")
        raise HTTPException(500, str(e))

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
