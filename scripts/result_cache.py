#!/usr/bin/env python3
"""Result caching for similar tasks to improve performance and reduce costs."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

class ResultCache:
    """Cache system for storing and retrieving task results."""
    
    def __init__(self, cache_dir: Path | None = None, ttl_seconds: int = 86400):
        """
        Initialize the result cache.
        
        Args:
            cache_dir: Directory to store cache files. Defaults to artifacts/devin-delegate/cache
            ttl_seconds: Time-to-live for cache entries in seconds (default: 24 hours)
        """
        if cache_dir is None:
            # Default to artifacts/devin-delegate/cache in repo root
            try:
                import subprocess
                proc = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    repo_root = Path(proc.stdout.strip())
                else:
                    repo_root = Path.cwd()
            except Exception:
                repo_root = Path.cwd()
            cache_dir = repo_root / "artifacts" / "devin-delegate" / "cache"
        
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_cache_key(self, task: str, task_class: str | None = None, context: str | None = None) -> str:
        """
        Generate a cache key from task parameters.
        
        Args:
            task: Task description
            task_class: Optional task class
            context: Optional context file content
        
        Returns:
            MD5 hash as cache key
        """
        # Normalize the task string
        normalized_task = " ".join(task.lower().split())
        
        # Compress context if present (take first 500 chars to avoid huge keys)
        compressed_context = ""
        if context:
            compressed_context = context[:500] if len(context) > 500 else context
        
        # Create a string with all relevant parameters
        key_string = f"{normalized_task}|{task_class or 'default'}|{compressed_context}"
        
        # Generate MD5 hash
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if a cache file is still valid based on TTL."""
        if not cache_path.exists():
            return False
        
        try:
            cache_age = time.time() - cache_path.stat().st_mtime
            return cache_age < self.ttl_seconds
        except OSError:
            return False
    
    def get(self, task: str, task_class: str | None = None, context: str | None = None) -> dict[str, Any] | None:
        """
        Retrieve a cached result if available and valid.
        
        Args:
            task: Task description
            task_class: Optional task class
            context: Optional context file content
        
        Returns:
            Cached result dict or None if not found/expired
        """
        cache_key = self._generate_cache_key(task, task_class, context)
        cache_path = self._get_cache_path(cache_key)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            cache_data["from_cache"] = True
            cache_data["cache_key"] = cache_key
            return cache_data
        except (json.JSONDecodeError, OSError):
            return None
    
    def set(self, task: str, result: str, task_class: str | None = None, context: str | None = None, 
            metadata: dict[str, Any] | None = None) -> None:
        """
        Store a task result in the cache.
        
        Args:
            task: Task description
            result: Task result/output
            task_class: Optional task class
            context: Optional context file content
            metadata: Optional metadata to store with the cache
        """
        cache_key = self._generate_cache_key(task, task_class, context)
        cache_path = self._get_cache_path(cache_key)
        
        cache_data = {
            "task": task,
            "task_class": task_class,
            "result": result,
            "timestamp": time.time(),
            "cache_key": cache_key,
            "metadata": metadata or {}
        }
        
        try:
            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except OSError:
            # Fail silently if cache write fails
            pass
    
    def invalidate(self, task: str | None = None, task_class: str | None = None) -> int:
        """
        Invalidate cache entries.
        
        Args:
            task: Specific task to invalidate, or None for all
            task_class: Specific task class to invalidate, or None for all
        
        Returns:
            Number of cache entries invalidated
        """
        invalidated = 0
        
        if task is None and task_class is None:
            # Clear all cache
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                    invalidated += 1
                except OSError:
                    pass
        else:
            # Invalidate specific entries
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if task and cache_data.get("task") != task:
                        continue
                    if task_class and cache_data.get("task_class") != task_class:
                        continue
                    cache_file.unlink()
                    invalidated += 1
                except (json.JSONDecodeError, OSError):
                    pass
        
        return invalidated
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of expired entries removed
        """
        removed = 0
        
        for cache_file in self.cache_dir.glob("*.json"):
            if not self._is_cache_valid(cache_file):
                try:
                    cache_file.unlink()
                    removed += 1
                except OSError:
                    pass
        
        return removed
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_entries = 0
        valid_entries = 0
        expired_entries = 0
        total_size_bytes = 0
        
        for cache_file in self.cache_dir.glob("*.json"):
            total_entries += 1
            try:
                total_size_bytes += cache_file.stat().st_size
                if self._is_cache_valid(cache_file):
                    valid_entries += 1
                else:
                    expired_entries += 1
            except OSError:
                expired_entries += 1
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
            "ttl_seconds": self.ttl_seconds
        }
    
    def find_similar_tasks(self, task: str, threshold: float = 0.7, limit: int = 5) -> list[dict[str, Any]]:
        """
        Find similar tasks in the cache using simple text similarity.
        
        Args:
            task: Task to find similar tasks for
            threshold: Similarity threshold (0-1)
            limit: Maximum number of results
        
        Returns:
            List of similar task entries with similarity scores
        """
        similar_tasks = []
        task_words = set(task.lower().split())
        
        for cache_file in self.cache_dir.glob("*.json"):
            if not self._is_cache_valid(cache_file):
                continue
            
            try:
                cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
                cached_task = cache_data.get("task", "")
                cached_words = set(cached_task.lower().split())
                
                # Calculate Jaccard similarity
                if not task_words or not cached_words:
                    continue
                
                intersection = len(task_words & cached_words)
                union = len(task_words | cached_words)
                similarity = intersection / union if union > 0 else 0
                
                if similarity >= threshold:
                    similar_tasks.append({
                        "task": cached_task,
                        "similarity": round(similarity, 3),
                        "cache_key": cache_data.get("cache_key"),
                        "timestamp": cache_data.get("timestamp"),
                        "task_class": cache_data.get("task_class")
                    })
            except (json.JSONDecodeError, OSError):
                continue
        
        # Sort by similarity and return top results
        similar_tasks.sort(key=lambda x: x["similarity"], reverse=True)
        return similar_tasks[:limit]


def main() -> int:
    """CLI for cache management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Result cache management for devin-delegate")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--cleanup", action="store_true", help="Remove expired cache entries")
    parser.add_argument("--clear", action="store_true", help="Clear all cache entries")
    parser.add_argument("--invalidate-task", help="Invalidate cache for a specific task")
    parser.add_argument("--invalidate-class", help="Invalidate cache for a specific task class")
    parser.add_argument("--find-similar", help="Find similar tasks in cache")
    parser.add_argument("--threshold", type=float, default=0.7, help="Similarity threshold (default: 0.7)")
    parser.add_argument("--cache-dir", help="Custom cache directory")
    parser.add_argument("--ttl", type=int, default=86400, help="TTL in seconds (default: 86400)")
    
    args = parser.parse_args()
    
    cache = ResultCache(cache_dir=Path(args.cache_dir) if args.cache_dir else None, ttl_seconds=args.ttl)
    
    if args.stats:
        stats = cache.get_stats()
        print("📊 Cache Statistics")
        print(f"   Total entries:  {stats['total_entries']}")
        print(f"   Valid entries:  {stats['valid_entries']}")
        print(f"   Expired entries: {stats['expired_entries']}")
        print(f"   Total size:     {stats['total_size_mb']} MB")
        print(f"   Cache directory: {stats['cache_dir']}")
        print(f"   TTL:            {stats['ttl_seconds']}s")
        return 0
    
    if args.cleanup:
        removed = cache.cleanup_expired()
        print(f"🧹 Removed {removed} expired cache entries")
        return 0
    
    if args.clear:
        removed = cache.invalidate()
        print(f"🗑️  Cleared {removed} cache entries")
        return 0
    
    if args.invalidate_task or args.invalidate_class:
        removed = cache.invalidate(task=args.invalidate_task, task_class=args.invalidate_class)
        print(f"❌ Invalidated {removed} cache entries")
        return 0
    
    if args.find_similar:
        similar = cache.find_similar_tasks(args.find_similar, threshold=args.threshold)
        print(f"🔍 Similar tasks for: {args.find_similar}")
        if not similar:
            print("   No similar tasks found")
        else:
            for i, task_info in enumerate(similar, 1):
                print(f"   {i}. Similarity: {task_info['similarity']} | {task_info['task'][:60]}...")
        return 0
    
    print("No action specified. Use --help for usage information.")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())