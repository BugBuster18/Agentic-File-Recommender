# Agentic File Recommender

An intelligent local system that recommends related files based on file content and user activity patterns - entirely offline and private.

## Architecture Overview

### Core Components

1. **FastAPI Backend** (app.py)
   - RESTful API service
   - Handles file scanning, recommendations, and activity logging
   - Async-first design for better performance

2. **Database** (db.py)
   - SQLite with WAL mode for better concurrency
   - Tables:
     - `files`: Core file metadata
     - `file_content`: File text and embeddings
     - `file_activity`: Usage tracking
     - `file_cooccurrence`: Related file patterns

3. **Intelligent Agents**

#### File Agent (agents/file_agent.py)
- Handles file system operations
- Scans directories incrementally
- Extracts text content
- Computes file hashes for change detection
- Manages file metadata in database

#### Recommendation Agent (agents/recommendation_agent.py)
- Uses SentenceTransformers ("all-MiniLM-L6-v2")
  - Why this model?
    - Efficient: 384-dimension embeddings
    - Fast inference on CPU
    - Good balance of accuracy vs resource usage
    - Works entirely offline
- Implements multi-factor ranking:
  - Semantic similarity (α): Content-based matching
  - Recency (β): Favors recently accessed files
  - Co-occurrence (γ): Files often used together
- Uses Annoy index for fast similarity search

#### Activity Agent (agents/activity_agent.py)
- Tracks file usage patterns
- Records file access timestamps
- Builds co-occurrence relationships
- Enables activity-based recommendations

### API Endpoints

#### /health
- GET: System health check
- Response: Status and config state

#### /scan
- POST: Initiate directory scan
  ```bash
  curl -X POST "http://localhost:8000/scan?path=/path/to/dir"
  ```
- GET: Same functionality as POST
- Processes:
  1. Recursively finds files
  2. Extracts content from text files
  3. Computes embeddings
  4. Updates database
  5. Rebuilds search index

#### /recommend_from_file
- GET: Get recommendations for a file
  ```bash
  curl "http://localhost:8000/recommend_from_file?path=/path/to/file&limit=5"
  ```
- Parameters:
  - path: Source file path
  - limit: Max recommendations (default: 5)
- Returns ranked recommendations with:
  - Similar content
  - Recent files
  - Co-accessed files
  - Explanation scores

#### /activity/log
- POST: Log file access
  ```bash
  curl -X POST "http://localhost:8000/activity/log?path=/path/to/file"
  ```
- Updates activity patterns
- Builds co-occurrence data

### Text Processing (utils.py)
- Smart text extraction
- Encoding detection (with chardet fallback)
- MIME type handling
- File hashing for changes

### Configuration (config.yaml)
```yaml
scan:
  default_roots: ["C:/Users/Public/Documents"]
  snippet_bytes: 8192
  allowed_exts: [".txt", ".md", ".py", ".json", ".csv", ".pdf"]
embeddings:
  model_name: "all-MiniLM-L6-v2"
  dim: 384
ranking:
  alpha: 0.6  # Content similarity weight
  beta: 0.2   # Recency weight
  gamma: 0.15 # Co-occurrence weight
```

## Setup and Running

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Initialize database:
   ```bash
   python backend/db.py
   ```

4. Start server:
   ```bash
   python run.py
   ```

5. Access API docs:
   - http://127.0.0.1:8000/docs

## Key Features

1. **Intelligent Recommendations**
   - Content-based similarity
   - Usage pattern awareness
   - Multi-factor ranking

2. **Privacy-First**
   - Fully offline operation
   - No data leaves your system
   - Local embeddings computation

3. **Efficient Processing**
   - Incremental scanning
   - Fast vector similarity search
   - Concurrent database access

4. **Activity Learning**
   - Learns from file usage
   - Tracks related files
   - Improves over time

5. **Developer Friendly**
   - OpenAPI documentation
   - Async-first design
   - Modular architecture

## Extensibility

The system is designed for easy extension:
- Add new embedding models
- Implement additional ranking factors
- Support more file types
- Add new recommendation strategies

## Best Practices

1. Regular scanning of active directories
2. Allow activity tracking for better recommendations
3. Configure ranking weights based on usage patterns
4. Monitor logs for potential issues

## Metadata and Activity Tracking

### File Metadata Extraction
1. **Basic Metadata**
   - Last modified time (from filesystem)
   - File type (via mimetypes)
   - File size and path
   - SHA-256 hash for change detection

2. **Activity Metadata** (file_activity table)
   - Last accessed timestamp
   - Access count
   - Usage patterns
   - Co-occurrence relationships

3. **Content Metadata** (file_content table)
   - Text snippets (first 8KB by default)
   - Content embeddings
   - MIME type detection
   - Encoding detection (using chardet)

### Activity Tracking System
1. **Access Logging**
   ```sql
   -- Example activity query
   SELECT f.path, fa.last_accessed, fa.access_count
   FROM file_activity fa
   JOIN files f ON fa.file_id = f.id
   ORDER BY fa.last_accessed DESC
   ```

2. **Co-occurrence Tracking**
   - Files accessed within 5-minute windows
   - Builds relationship graph
   - Used for contextual recommendations

3. **Usage Analytics**
   - Most frequently accessed files
   - Common file pairs
   - Peak usage times
   - File relevance decay

4. **Time-based Features**
   - Recency scoring using exponential decay
   - Co-occurrence windowing (5-minute default)
   - Access frequency normalization
   - Temporal usage patterns

### Metadata Integration in Recommendations
1. **Ranking Factors**
   - Content similarity (embeddings)
   - Recent access (activity logs)
   - Usage frequency (access count)
   - Co-occurrence patterns

2. **Scoring Example**
   ```python
   final_score = (
       α * content_similarity +
       β * recency_score +     # from last_accessed
       γ * cooccurrence_score  # from activity patterns
   )
   ```

3. **Activity Weight Adaptation**
   - More recent = higher weight
   - More co-occurrences = stronger relationship
   - Automatic relevance decay
   - Usage pattern learning
