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

## Recency Parameter Explanation

### How Recency Works

The recency parameter (β) now uses **both recent modification AND recent access** to determine file relevance:

#### 1. Data Sources for Recency (Updated)

**File Modification Time** (from filesystem) - 40% weight
- Extracted when files are scanned
- Stored in `files.last_modified`
- Indicates when content was last changed
- Updated via `/scan` endpoint
- Why: Reflects content freshness

```sql
SELECT last_modified FROM files WHERE path = ?;
```

**File Access Time** (from activity logging) - 60% weight
- Recorded when files are accessed via `/recommend_from_file` or `/activity/log`
- Stored in `file_activity.last_accessed`
- Updated every time a file is accessed
- Updated via `/activity/log` endpoint
- Why: Reflects current user interest and engagement

```sql
SELECT last_accessed FROM file_activity WHERE file_id = ?;
```

#### 2. Why Dual Sources Matter

```
✓ PREVIOUS: Only used modification time
  Problem: Old files that are frequently used get low scores

✓ NEW: Uses both modification + access times
  Benefit: Balances content freshness with actual usage patterns
```

**Example scenarios:**

```
File A: main.py
  - Last Modified: 30 days ago (old code)
  - Last Accessed: 2 hours ago (actively using it)
  - Old approach: Low recency (0.37)
  - New approach: High recency (0.78) ✓
  
File B: template.py
  - Last Modified: 1 hour ago (just edited)
  - Last Accessed: 90 days ago (never used)
  - Old approach: High recency (0.99)
  - New approach: Medium recency (0.60) ✓
```

#### 3. Recency Scoring Algorithm (Updated)

Uses **exponential decay** for both sources with different decay rates:

```python
# From recommendation_agent.py - UPDATED IMPLEMENTATION
async def _get_recency_score(self, file_path: str) -> float:
    # Modification recency (30-day decay)
    days_since_modified = (now - last_modified).days
    modification_score = exp(-days_since_modified / 30)
    
    # Access recency (15-day decay - faster)
    days_since_accessed = (now - last_accessed).days
    access_score = exp(-days_since_accessed / 15)
    
    # Combined: 40% modification + 60% access
    combined_score = (0.4 * modification_score) + (0.6 * access_score)
    return max(0.0, min(1.0, combined_score))
```

#### 4. Score Examples (Updated)

**Based on combination of modification + access times:**

```
File: python_notes.txt
  Modified 5 days ago (mod_score = 0.85)
  Accessed 1 hour ago (access_score = 0.995)
  Final: 0.4*0.85 + 0.6*0.995 = 0.937 ✓ Very high

File: config.yaml
  Modified 1 hour ago (mod_score = 0.998)
  Accessed 90 days ago (access_score = 0.003)
  Final: 0.4*0.998 + 0.6*0.003 = 0.401 ✓ Medium

File: old_backup.py
  Modified 90 days ago (mod_score = 0.003)
  Accessed 90 days ago (access_score = 0.003)
  Final: 0.4*0.003 + 0.6*0.003 = 0.003 ✓ Very low
```

#### 5. Why Access Time Gets More Weight (60% vs 40%)

**Access recency (60%) reflects:**
- Current user interest
- Active workflow engagement
- What the user is working with now

**Modification recency (40%) reflects:**
- Content freshness
- Recent changes to code/data
- Updated information

**Rationale:** If a user is actively accessing a file, that shows current interest even if it hasn't been modified recently.

#### 6. Now Logging Access DOES Increase Recency!

**Scenario: You log the same file 5 times**
```
14:00 - Log access to main.py
        access_score increased to ~0.99
        Final recency = 0.4*mod_score + 0.6*0.99

14:02 - Log access to main.py again
        access_score still ~0.99
        Final recency = 0.4*mod_score + 0.6*0.99

Result: Recency remains high as long as access is recent ✓
```

#### 7. How to Increase Recency Score (Updated)

**Option 1: Log file access (simplest)**
```bash
# Log access updates last_accessed timestamp
curl -X POST "http://localhost:8000/activity/log?path=./main.py"

# Recency score increases immediately
curl "http://localhost:8000/recommend_from_file?path=./main.py"
```

**Option 2: Get recommendations (auto-logs access)**
```bash
# Getting recommendations automatically logs access
curl "http://localhost:8000/recommend_from_file?path=./main.py"

# Recency score increases for this file
```

**Option 3: Modify the file (updates modification time)**
```bash
# Edit the file
echo "new content" >> main.py

# Rescan directory
curl -X POST "http://localhost:8000/scan?path=./test_files"

# Recency score increases for modification component
```

#### 8. Activity Logs NOW Affect Recency!

```
Activity Logs (file_activity table):
  - Updated: Every time you log access
  - Used for: Recency scoring (60% weight)
  - Affects: β (recency) factor ✓ UPDATED
  - Purpose: Track current user engagement

File Modification Time (files.last_modified):
  - Updated: When file changes + scanned
  - Used for: Recency scoring (40% weight)
  - Affects: β (recency) factor
  - Purpose: Track content freshness
```

#### 9. Decay Rate Differences

**Why different decay rates?**

```
Access decay (15-day half-life - faster):
  - More sensitive to recent access
  - Reflects immediate interest
  - 0 hours ago: 1.0
  - 1 day ago: 0.95
  - 7 days ago: 0.67
  - 15 days ago: 0.37

Modification decay (30-day half-life - slower):
  - Less sensitive to time
  - Reflects code stability
  - 0 hours ago: 1.0
  - 7 days ago: 0.79
  - 15 days ago: 0.61
  - 30 days ago: 0.37
```

#### 10. Workflow for Testing Updated Recency

**Step 1: Create and scan test files**
```bash
echo "Python code" > main.py
curl -X POST "http://localhost:8000/scan?path=./test_files"
# Recency high (just scanned)
```

**Step 2: Log access to keep recency high**
```bash
# Log access multiple times over time
curl -X POST "http://localhost:8000/activity/log?path=./test_files/main.py"
# Recency stays high due to access logging
```

**Step 3: Wait and check recency decay**
```bash
# After 1 day without access
# Recency drops gradually (still high due to modification time)

# After 7 days without access
# Recency becomes moderate (access_score low, mod_score decent)

# After 30+ days without modification or access
# Recency very low
```

**Step 4: Resync with a modification**
```bash
echo "Updated" >> main.py
curl -X POST "http://localhost:8000/scan?path=./test_files"
# Recency jumps back up due to recent modification
```

#### 11. Tuning Recency Weights

To adjust the balance between access and modification, modify `recommendation_agent.py`:

```python
# Current balance (recommended):
combined_score = (0.4 * modification_score) + (0.6 * access_score)

# More emphasis on content freshness:
combined_score = (0.6 * modification_score) + (0.4 * access_score)

# Only access-based (ignore modification):
combined_score = access_score

# Only modification-based (original behavior):
combined_score = modification_score
```

#### 12. Updated Summary Table

| Parameter | Data Source | Updated When | Decay Rate | Weight | Example |
|-----------|------------|--------------|-----------|--------|---------|
| Access recency | `file_activity.last_accessed` | Every access log | 15 days | 60% | Log file → immediate recency boost |
| Modification recency | `files.last_modified` | File modified + scanned | 30 days | 40% | Edit file → recency increases |
| Combined recency (β) | Both sources | Either source updated | Mixed | - | Both factors contribute |

## Co-occurrence Parameter Explanation

### How Co-occurrence Works

The co-occurrence parameter (γ) tracks **pairs of files accessed together**, not individual file frequency. This captures contextual relationships and workflow patterns.

#### 1. Co-occurrence vs Single File Frequency

**IMPORTANT DISTINCTION:**

```
❌ WRONG UNDERSTANDING:
If you access File A 100 times continuously, it should have high co-occurrence.

✓ CORRECT UNDERSTANDING:
Co-occurrence tracks File A being accessed WITH other files (File B, C, D).
Single file frequency doesn't increase co-occurrence scores.
```

#### 2. How Co-occurrence is Recorded

**Time Window: 5-minute sliding window**

When you access File A:
1. System checks what other files were accessed in last 5 minutes
2. Creates/updates pairs with all those files
3. Increments co-count for each pair

```python
# From activity_agent.py
async def record_access(self, file_path: str) -> bool:
    # Find other files accessed recently (within 5 minutes)
    cursor.execute("""
        SELECT file_id FROM file_activity
        WHERE file_id != ? 
        AND last_accessed >= datetime('now', '-5 minutes')
    """, (file_id,))
    
    for row in cursor.fetchall():
        other_id = row[0]
        # Record this pair
        await self.record_cooccurrence(file_id, other_id)
```

**Data Storage:**

```sql
-- file_cooccurrence table
CREATE TABLE file_cooccurrence (
    file_id_1 INTEGER,
    file_id_2 INTEGER,
    co_count INTEGER,  -- Number of times accessed together
    PRIMARY KEY (file_id_1, file_id_2)
);

-- Example data:
file_id_1 | file_id_2 | co_count
    1     |     2     |   15     -- File A & B accessed together 15 times
    1     |     3     |    8     -- File A & C accessed together 8 times
    2     |     3     |    5     -- File B & C accessed together 5 times
```

#### 3. Practical Co-occurrence Examples

**Scenario 1: Different files in workflow**
```
Timeline:
14:00 - Access File A (notes.txt)
14:02 - Access File B (code.py)
↓
Creates pair: (File A, File B) with co_count = 1

14:05 - Access File C (config.json)
↓
Creates pairs: 
  - (File A, File C) with co_count = 1
  - (File B, File C) with co_count = 1

14:15 - Access File A again
↓
No new pairs (outside 5-min window of B, C)
File A single frequency increased, but co-occurrence unchanged
```

**Scenario 2: Files accessed together repeatedly**
```
Timeline:
14:00 - Access File A (report.md)
14:02 - Access File B (data.csv)    ← Within 5 min
        Creates pair (A, B): co_count = 1

14:15 - Access File A again
14:16 - Access File B again         ← Within 5 min
        Updates pair (A, B): co_count = 2

14:30 - Access File A again
14:31 - Access File B again         ← Within 5 min
        Updates pair (A, B): co_count = 3

Result: (A, B) has high co_count = 3 (strong workflow relationship)
```

**Scenario 3: Single file accessed repeatedly**
```
Timeline:
14:00 - Access File A
        [No other files in 5-min window, no co-occurrence created]

14:02 - Access File A again
        [Still no other files, no co-occurrence created]

14:04 - Access File A again
        [Still no other files, no co-occurrence created]

Result: File A accessed 3 times, but co-occurrence remains 0
        (No workflow context recorded)
```

#### 4. Co-occurrence Scoring Algorithm

```python
# From recommendation_agent.py
async def _get_cooccurrence_score(self, query_path, candidate_path) -> float:
    cursor.execute("""
        SELECT co_count FROM file_cooccurrence
        WHERE (file_id_1 = ? AND file_id_2 = ?)
           OR (file_id_1 = ? AND file_id_2 = ?)
    """, (id1, id2, id2, id1))
    
    cooccur = cursor.fetchone()[0]
    # Normalize using sigmoid function
    return 2 / (1 + math.exp(-cooccur / 5)) - 1
```

**Score Examples:**
```
co_count | sigmoid_score | Interpretation
    0    |     -1.0      | Never accessed together
    1    |     -0.76     | Rare co-access
    2    |     -0.46     | Occasional co-access
    5    |      0.52     | Strong relationship
   10    |      0.88     | Very strong relationship
   20    |      0.98     | Extremely strong relationship
```

#### 5. Real-world Workflow Example

**Developer workflow:**
```
File A: main.py (frequently accessed)
File B: config.yaml (used with main.py)
File C: requirements.txt (used with main.py)
File D: notes.txt (rarely used)

Typical usage pattern:
- Open main.py → Open config.yaml (within 5 min) → co_count(A,B) increases
- Open main.py → Open requirements.txt (within 5 min) → co_count(A,C) increases
- Open notes.txt → Not in same 5-min window as others → co_count(A,D) stays low

Result co-occurrence graph:
(A, B): 15   [Strong: main.py + config always used together]
(A, C): 12   [Strong: main.py + requirements often used together]
(B, C):  8   [Moderate: config and requirements sometimes together]
(A, D):  1   [Weak: notes rarely accessed with main.py]
(B, D):  0   [None: config never accessed with notes]
(C, D):  0   [None: requirements never accessed with notes]
```

#### 6. Why Co-occurrence is Better Than Frequency

**Single Frequency Approach (❌ Not used):**
- File A accessed 100 times → High frequency score
- File B accessed 50 times → Medium frequency score
- Recommendation: Always suggest File A
- Problem: Ignores context and workflow

**Co-occurrence Approach (✓ Used here):**
- File A accessed 100 times, but only 5 times with File X
- File B accessed 50 times, 40 times with File X
- When querying File X: File B ranked higher
- Benefit: Understands contextual relationships

#### 7. Co-occurrence Integration with Other Factors

```python
final_score = (
    α * semantic_similarity +      # 0.63 - Content match
    β * recency_score +             # 0.21 - Recently modified/accessed
    γ * cooccurrence_score          # 0.16 - Workflow relationship
)
```

**Combined Ranking Example:**

```
Query File: main.py

Candidate Files:
1. config.yaml
   - Semantic similarity: 0.3 (different types)
   - Recency: 0.95 (accessed yesterday)
   - Co-occurrence: 0.85 (frequently together)
   - Final: 0.63*0.3 + 0.21*0.95 + 0.16*0.85 = 0.529

2. old_code.py
   - Semantic similarity: 0.8 (similar code)
   - Recency: 0.2 (accessed 60 days ago)
   - Co-occurrence: 0.1 (rarely together)
   - Final: 0.63*0.8 + 0.21*0.2 + 0.16*0.1 = 0.558

3. notes.txt
   - Semantic similarity: 0.4 (somewhat related)
   - Recency: 0.9 (modified today)
   - Co-occurrence: 0 (never together)
   - Final: 0.63*0.4 + 0.21*0.9 + 0.16*0 = 0.441

Ranking: old_code.py (0.558) > config.yaml (0.529) > notes.txt (0.441)
```

#### 8. Building Co-occurrence Data

**Start building co-occurrence by:**

1. Regular file usage:
   ```bash
   # Manually log activities
   curl -X POST "http://localhost:8000/activity/log?path=/path/to/file_a"
   sleep 2
   curl -X POST "http://localhost:8000/activity/log?path=/path/to/file_b"
   ```

2. Natural workflow:
   ```bash
   # Get recommendations (auto-logs access)
   curl "http://localhost:8000/recommend_from_file?path=/path/to/file_a"
   sleep 2
   curl "http://localhost:8000/recommend_from_file?path=/path/to/file_b"
   ```

3. Monitor co-occurrence growth:
   ```sql
   SELECT * FROM file_cooccurrence 
   ORDER BY co_count DESC LIMIT 10;
   ```

#### 9. Tuning Co-occurrence Weight

**Adjust γ in config.yaml:**

```yaml
ranking:
  alpha: 0.6      # Content similarity
  beta: 0.2       # Recency
  gamma: 0.15     # Co-occurrence weight
```

- γ = 0.0: Ignore workflow patterns
- γ = 0.1: Slight workflow preference
- γ = 0.2: Strong workflow preference
- γ = 0.3: Very strong workflow preference

## Simulating Co-occurrence on the Application

### How to Build and Test Co-occurrence Data

Since co-occurrence requires actual file access patterns, here are multiple methods to simulate realistic co-occurrence data:

### Method 1: Manual Activity Logging (Simplest)

**Step 1: Create test files**
```bash
cd test_files
echo "Python notes" > python_notes.txt
echo "def hello(): pass" > hello.py
echo "import sys" > config.py
echo "API documentation" > api_docs.txt
```

**Step 2: Scan the directory**
```bash
curl -X POST "http://localhost:8000/scan?path=./test_files"
```

**Step 3: Manually log file accesses in pairs (within 5-minute window)**

```bash
# Access python_notes.txt and hello.py together
curl -X POST "http://localhost:8000/activity/log?path=./test_files/python_notes.txt"
sleep 2  # 2 seconds apart
curl -X POST "http://localhost:8000/activity/log?path=./test_files/hello.py"

# Wait for next window and repeat
sleep 60
curl -X POST "http://localhost:8000/activity/log?path=./test_files/python_notes.txt"
sleep 2
curl -X POST "http://localhost:8000/activity/log?path=./test_files/hello.py"

# Repeat this pattern 3-5 times to build co_count
```

**Expected result:**
```
file_cooccurrence table will have:
(python_notes.txt, hello.py): co_count = 3-5 (depending on repetitions)
```

### Method 2: Python Script (Recommended for testing)

**Create a script: e:\A IIIT DWD\semester 5\agentic\1\simulate_cooccurrence.py**

```python
# filepath: e:\A IIIT DWD\semester 5\agentic\1\simulate_cooccurrence.py
import requests
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEST_DIR = Path("./test_files")

def log_activity(file_path):
    """Log a single file access."""
    response = requests.post(
        f"{BASE_URL}/activity/log",
        params={"path": str(file_path.absolute())}
    )
    return response.status_code == 200

def simulate_workflow(file_pairs, num_iterations=3, delay_between=2, delay_between_iterations=60):
    """
    Simulate a workflow by accessing file pairs together.
    
    Args:
        file_pairs: List of (file1, file2) tuples
        num_iterations: How many times to repeat the workflow
        delay_between: Seconds between files in a pair
        delay_between_iterations: Seconds between workflow iterations
    """
    print(f"Starting co-occurrence simulation with {num_iterations} iterations...")
    
    for iteration in range(num_iterations):
        print(f"\n--- Iteration {iteration + 1}/{num_iterations} ---")
        
        for file1, file2 in file_pairs:
            print(f"Accessing {file1.name} and {file2.name} together...")
            
            # Access file1
            success1 = log_activity(file1)
            print(f"  ✓ {file1.name}: {'Success' if success1 else 'Failed'}")
            
            # Wait 2 seconds (within 5-minute window)
            time.sleep(delay_between)
            
            # Access file2
            success2 = log_activity(file2)
            print(f"  ✓ {file2.name}: {'Success' if success2 else 'Failed'}")
            
            # Create co-occurrence pair
            if success1 and success2:
                print(f"  → Co-occurrence pair created: ({file1.name}, {file2.name})")
        
        # Wait before next iteration
        if iteration < num_iterations - 1:
            print(f"\nWaiting {delay_between_iterations}s before next iteration...")
            time.sleep(delay_between_iterations)
    
    print("\n✓ Simulation complete!")

def main():
    # Define file pairs for typical workflows
    file_pairs = [
        (TEST_DIR / "python_notes.txt", TEST_DIR / "hello.py"),
        (TEST_DIR / "hello.py", TEST_DIR / "config.py"),
        (TEST_DIR / "python_notes.txt", TEST_DIR / "config.py"),
    ]
    
    # Run simulation
    simulate_workflow(
        file_pairs,
        num_iterations=3,  # 3 complete workflow cycles
        delay_between=2,   # 2 seconds between files in pair
        delay_between_iterations=60  # 60 seconds between cycles
    )

if __name__ == "__main__":
    main()
```

**Run the simulation:**
```bash
python simulate_cooccurrence.py
```

### Method 3: Bash Script (Quick testing)

**Create: e:\A IIIT DWD\semester 5\agentic\1\simulate.sh**

```bash
#!/bin/bash
# filepath: e:\A IIIT DWD\semester 5\agentic\1\simulate.sh

BASE_URL="http://localhost:8000"
TEST_DIR="./test_files"

echo "Simulating co-occurrence patterns..."

for i in {1..3}; do
    echo "Iteration $i..."
    
    # Pair 1: python_notes.txt and hello.py
    curl -s -X POST "$BASE_URL/activity/log?path=$TEST_DIR/python_notes.txt" > /dev/null
    sleep 2
    curl -s -X POST "$BASE_URL/activity/log?path=$TEST_DIR/hello.py" > /dev/null
    
    # Pair 2: hello.py and config.py
    sleep 2
    curl -s -X POST "$BASE_URL/activity/log?path=$TEST_DIR/hello.py" > /dev/null
    sleep 2
    curl -s -X POST "$BASE_URL/activity/log?path=$TEST_DIR/config.py" > /dev/null
    
    # Wait before next iteration
    echo "Waiting 60 seconds before next iteration..."
    sleep 60
done

echo "Co-occurrence simulation complete!"
```

**Run it:**
```bash
chmod +x simulate.sh
./simulate.sh
```

### Method 4: API Testing with Swagger UI

**Step 1: Open Swagger UI**
- Navigate to: http://127.0.0.1:8000/docs

**Step 2: Use the `/activity/log` endpoint**
1. Click on `/activity/log` endpoint
2. Click "Try it out"
3. Enter file path: `./test_files/python_notes.txt`
4. Click "Execute"

**Step 3: Repeat for other files within 5 minutes**
1. Wait 2-3 seconds
2. Log another file: `./test_files/hello.py`
3. Repeat pattern multiple times

**Result**: Build co-occurrence data manually through UI

### Verifying Co-occurrence Data

**Method 1: Query Database Directly**

```bash
# Open SQLite shell
sqlite3 data/files.db

# Check co-occurrence table
SELECT f1.path as file1, f2.path as file2, co_count 
FROM file_cooccurrence fc
JOIN files f1 ON fc.file_id_1 = f1.id
JOIN files f2 ON fc.file_id_2 = f2.id
ORDER BY co_count DESC;
```

**Expected output:**
```
file1              | file2         | co_count
python_notes.txt   | hello.py      | 3
hello.py           | config.py     | 3
python_notes.txt   | config.py     | 2
```

**Method 2: Get Recommendations with Co-occurrence**

After simulating co-occurrence, get recommendations:

```bash
curl "http://localhost:8000/recommend_from_file?path=./test_files/hello.py&limit=5"
```

**Example response:**
```json
{
  "recommendations": [
    {
      "path": "./test_files/python_notes.txt",
      "final_score": 0.625,
      "factors": {
        "semantic_similarity": 0.45,
        "recency": 0.92,
        "cooccurrence": 0.85
      },
      "weights": {
        "semantic": 0.63,
        "recency": 0.21,
        "cooccurrence": 0.16
      }
    },
    {
      "path": "./test_files/config.py",
      "final_score": 0.521,
      "factors": {
        "semantic_similarity": 0.65,
        "recency": 0.88,
        "cooccurrence": 0.75
      },
      "weights": {
        "semantic": 0.63,
        "recency": 0.21,
        "cooccurrence": 0.16
      }
    }
  ]
}
```

**Notice:** python_notes.txt ranks higher due to high co-occurrence (0.85)

### Simulation Strategies

#### Strategy 1: Single Workflow Pattern
```
Focus: One pair of files repeatedly

File A ↔ File B (accessed together 5 times)
File B ↔ File C (accessed together 3 times)
File A ↔ File C (accessed together 1 time)

Result: Clear relationship graph
```

#### Strategy 2: Complex Workflow
```
Focus: Multiple files in different patterns

Morning workflow:
  python_notes.txt → hello.py → config.py

Afternoon workflow:
  api_docs.txt → config.py → requirements.txt

Result: Multiple co-occurrence paths
```

#### Strategy 3: Time-based Workflow
```
Focus: Same files, different access patterns

Week 1: A↔B frequently (co_count builds)
Week 2: A↔C frequently (new relationship)
Week 3: A↔B again (reinforces original)

Result: Temporal patterns visible
```

### Tuning Co-occurrence for Your Workflow

**Step 1: Identify your actual workflows**
```
Example developer workflow:
1. Open main.py
2. Open requirements.txt
3. Open config.yaml
```

**Step 2: Simulate those patterns**
```bash
python simulate_cooccurrence.py
```

**Step 3: Adjust weight in config.yaml**
```yaml
ranking:
  alpha: 0.6      # Keep semantic matching
  beta: 0.2       # Keep recency
  gamma: 0.25     # Increase co-occurrence if workflow important
```

**Step 4: Test recommendations**
```bash
curl "http://localhost:8000/recommend_from_file?path=./test_files/main.py"
```

**Step 5: Monitor results**
- High co-occurrence scores → files appear together
- Low scores → files rarely together
- Adjust γ based on recommendations quality

### Common Pitfalls and Solutions

**Problem: Co-occurrence not increasing**
- Solution: Make sure accesses are within 5-minute window
- Solution: Wait 60+ seconds between iterations

**Problem: All files have same co-occurrence**
- Solution: Create more diverse file pairs
- Solution: Simulate more iterations (5-10)
- Solution: Use different file types

**Problem: Co-occurrence too high**
- Solution: Reduce γ weight in config
- Solution: Space out file accesses beyond 5 minutes
- Solution: Clear activity logs and restart

**Problem: No co-occurrence data appearing**
- Solution: Verify `/activity/log` endpoint returns 200
- Solution: Check file paths are absolute
- Solution: Ensure files exist in database (run /scan first)

### Testing Checklist

- [ ] Created test files
- [ ] Ran `/scan` endpoint successfully
- [ ] Logged activities via `/activity/log`
- [ ] Verified data in database
- [ ] Got recommendations with co-occurrence scores
- [ ] Adjusted ranking weights if needed
- [ ] Tested with Swagger UI
- [ ] Ran Python simulation script
- [ ] Verified co-occurrence affects ranking
