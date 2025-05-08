# utils/caching.py
"""
Caching utilities for the Vetting Intelligence Hub.
"""

import functools
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Configure logging
logger = logging.getLogger('vetting_hub.caching')

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

# Cache settings
CACHE_TTL = 60 * 60 * 24  # 24 hours in seconds

class SimpleCache:
    """Simple file-based cache implementation."""
    
    def __init__(self, cache_dir=CACHE_DIR, ttl=CACHE_TTL):
        """
        Initialize the cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl: Time-to-live in seconds (default: 24 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(exist_ok=True)
    
    def get(self, key):
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache has expired
            timestamp = cache_data.get('timestamp', 0)
            if time.time() - timestamp > self.ttl:
                logger.debug(f"Cache expired for key: {key}")
                return None
            
            logger.debug(f"Cache hit for key: {key}")
            return cache_data.get('value')
        except Exception as e:
            logger.error(f"Error reading cache for key {key}: {str(e)}")
            return None
    
    def set(self, key, value):
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            
        Returns:
            True if successful, False otherwise
        """
        cache_file = self.cache_dir / f"{key}.json"
        
        try:
            cache_data = {
                'timestamp': time.time(),
                'value': value
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            logger.debug(f"Cache set for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Error setting cache for key {key}: {str(e)}")
            return False
    
    def delete(self, key):
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return True
        
        try:
            os.remove(cache_file)
            logger.debug(f"Cache deleted for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting cache for key {key}: {str(e)}")
            return False
    
    def clear(self):
        """
        Clear all cache entries.
        
        Returns:
            Number of entries cleared
        """
        count = 0
        for cache_file in self.cache_dir.glob('*.json'):
            try:
                os.remove(cache_file)
                count += 1
            except Exception as e:
                logger.error(f"Error deleting cache file {cache_file}: {str(e)}")
        
        logger.info(f"Cleared {count} cache entries")
        return count

# Create a global cache instance
app_cache = SimpleCache()

def cached(ttl=CACHE_TTL):
    """
    Decorator to cache function results.
    
    Args:
        ttl: Time-to-live in seconds (default: 24 hours)
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            key_parts = [func.__name__]
            
            # Add positional arguments
            for arg in args:
                key_parts.append(str(arg))
            
            # Add keyword arguments (sorted for consistency)
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            
            # Create a hash of the key parts
            key = hashlib.md5('|'.join(key_parts).encode()).hexdigest()
            
            # Try to get from cache
            cached_result = app_cache.get(key)
            if cached_result is not None:
                return cached_result
            
            # Call the function and cache the result
            result = func(*args, **kwargs)
            app_cache.set(key, result)
            return result
        
        return wrapper
    
    return decorator