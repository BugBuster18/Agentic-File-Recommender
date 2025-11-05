import hashlib
import pathlib
import logging
from typing import List, Optional
import mimetypes

# Try to import chardet, use fallback if not available
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False
    logging.warning("chardet not found, using UTF-8 as default encoding")

def detect_encoding(raw_data: bytes) -> str:
    """Detect text encoding with fallback to UTF-8."""
    if HAS_CHARDET:
        try:
            detected = chardet.detect(raw_data)
            return detected['encoding'] or 'utf-8'
        except Exception as e:
            logging.warning(f"chardet detection failed: {e}")
    return 'utf-8'

def compute_file_hash(path: pathlib.Path) -> str:
    """Compute SHA-256 hash of file with proper error handling."""
    try:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logging.error(f"Failed to hash file {path}: {e}")
        return ""

def extract_text_snippet(path: pathlib.Path, max_bytes: int = 8192) -> Optional[str]:
    """Extract text snippet with improved type handling."""
    try:
        # Check if file exists and is readable
        if not path.exists():
            logging.error(f"File not found: {path}")
            return None
            
        # Get file type
        mime_type, _ = mimetypes.guess_type(str(path))
        
        # Handle common text file types
        text_types = ['text/', 'application/json', 'application/xml', 'application/javascript']
        is_text = any(mime_type and mime_type.startswith(prefix) for prefix in text_types)
        
        if not is_text:
            logging.warning(f"Unsupported file type {mime_type} for {path}")
            return None
            
        # Read and decode file
        with open(path, 'rb') as f:
            raw_data = f.read(max_bytes)
            
        encoding = detect_encoding(raw_data)
        text = raw_data.decode(encoding, errors='ignore')
        cleaned_text = ' '.join(text.split())  # Normalize whitespace
        
        if not cleaned_text.strip():
            logging.warning(f"No text content extracted from {path}")
            return None
            
        return cleaned_text

    except Exception as e:
        logging.error(f"Failed to extract text from {path}: {e}")
        return None

def get_file_type(path: pathlib.Path) -> str:
    """Get standardized file type."""
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or 'application/octet-stream'
