#!/usr/bin/env python3
"""MCP server for exposing devin-delegate functionality as MCP tools."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Try to import MCP SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None
    stdio_server = None
    Tool = None
    TextContent = None

# Import devin-delegate modules
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from delegate import run_delegate, current_repo_root, skill_root, load_json
    from result_cache import ResultCache
    from telemetry_dashboard import TelemetryDashboard
except ImportError as e:
    logging.error(f"Failed to import devin-delegate modules: {e}")
    sys.exit(1)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DevinDelegateMCPServer:
    """MCP server for devin-delegate functionality."""
    
    def __init__(self):
        """Initialize the MCP server."""
        if not MCP_AVAILABLE:
            logger.error("MCP SDK not available. Install with: pip install mcp")
            sys.exit(1)
        
        self.server = Server("devin-delegate")
        self._setup_handlers()
        
        # Load configuration
        try:
            script_root = Path(__file__).parent
            skill_root = script_root.parent
            self.config = load_json(skill_root / "config" / "devin-delegate.json")
            self.routing = load_json(skill_root / "config" / "routing.json")
            self.repo_root = current_repo_root(skill_root)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self.config = {}
            self.routing = {}
            self.repo_root = Path.cwd()
    
    def _setup_handlers(self):
        """Setup MCP tool handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available MCP tools."""
            return [
                Tool(
                    name="delegate_task",
                    description="Delegate a task to Devin with structured envelope and fallback routing",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "Task description to delegate to Devin"
                            },
                            "task_class": {
                                "type": "string",
                                "enum": ["research", "implement", "debug", "review", "browser"],
                                "description": "Task classification for routing and timeout calculation"
                            },
                            "workspace": {
                                "type": "string",
                                "description": "Workspace directory path (optional, defaults to current repo)"
                            },
                            "use_cache": {
                                "type": "boolean",
                                "description": "Enable result caching (default: true)"
                            },
                            "safety_check": {
                                "type": "boolean",
                                "description": "Run safety checks before delegation (default: false)"
                            },
                            "fallback_engine": {
                                "type": "string",
                                "enum": ["codex", "kimi", "anthropic", "pi"],
                                "description": "Override fallback engine"
                            },
                            "fallback_provider": {
                                "type": "string",
                                "enum": ["codex", "kimi", "anthropic", "pi"],
                                "description": "Deprecated alias for fallback_engine"
                            },
                            "fallback_pi_provider": {
                                "type": "string",
                                "description": "Provider to pass to pi fallback (e.g., kimi-coding, openai)"
                            },
                            "timeout_override": {
                                "type": "integer",
                                "description": "Override timeout in seconds"
                            }
                        },
                        "required": ["task"]
                    }
                ),
                Tool(
                    name="get_telemetry",
                    description="Get telemetry statistics for devin-delegate usage",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "Number of days to analyze (default: 14)",
                                "default": 14
                            }
                        }
                    }
                ),
                Tool(
                    name="get_cache_stats",
                    description="Get result cache statistics",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="clear_cache",
                    description="Clear result cache entries",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "expired_only": {
                                "type": "boolean",
                                "description": "Only clear expired entries (default: false)",
                                "default": false
                            }
                        }
                    }
                ),
                Tool(
                    name="health_check",
                    description="Perform health check on devin-delegate environment",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="batch_delegate",
                    description="Delegate multiple tasks in batch",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "task": {"type": "string"},
                                        "task_class": {"type": "string"},
                                        "workspace": {"type": "string"}
                                    },
                                    "required": ["task"]
                                },
                                "description": "Array of task specifications"
                            },
                            "parallel": {
                                "type": "boolean",
                                "description": "Enable parallel processing (default: false)",
                                "default": false
                            },
                            "max_workers": {
                                "type": "integer",
                                "description": "Maximum parallel workers (default: 4)",
                                "default": 4
                            }
                        },
                        "required": ["tasks"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            try:
                if name == "delegate_task":
                    return await self._delegate_task(arguments)
                elif name == "get_telemetry":
                    return await self._get_telemetry(arguments)
                elif name == "get_cache_stats":
                    return await self._get_cache_stats(arguments)
                elif name == "clear_cache":
                    return await self._clear_cache(arguments)
                elif name == "health_check":
                    return await self._health_check(arguments)
                elif name == "batch_delegate":
                    return await self._batch_delegate(arguments)
                else:
                    return [TextContent(
                        type="text",
                        text=f"Unknown tool: {name}"
                    )]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    async def _delegate_task(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Delegate a task to Devin."""
        task = arguments.get("task", "")
        if not task:
            return [TextContent(type="text", text="Error: 'task' parameter is required")]
        
        task_class = arguments.get("task_class")
        workspace = arguments.get("workspace")
        use_cache = arguments.get("use_cache", True)
        safety_check = arguments.get("safety_check", False)
        fallback_engine = arguments.get("fallback_engine") or arguments.get("fallback_provider")
        fallback_pi_provider = arguments.get("fallback_pi_provider")
        timeout_override = arguments.get("timeout_override")
        
        workspace_path = Path(workspace) if workspace else self.repo_root
        
        # Run delegation in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        rc = await loop.run_in_executor(
            None,
            lambda: run_delegate(
                task=task,
                context_file=None,
                task_class=task_class,
                dry_run=False,
                print_envelope=False,
                config=self.config,
                routing=self.routing,
                repo_root=self.repo_root,
                workspace=workspace_path,
                show_cost=False,
                timeout_override=timeout_override,
                quick=True,
                interactive=False,
                safety_check=safety_check,
                strict_safety=False,
                use_cache=use_cache,
                cache_ttl=86400,
                fallback_engine_override=fallback_engine,
                fallback_provider_override=arguments.get("fallback_provider"),
                fallback_model_override=None,
                fallback_pi_provider_override=fallback_pi_provider
            )
        )
        
        result = f"Task delegation completed with exit code: {rc}"
        if rc == 0:
            result += " (Success)"
        else:
            result += f" (Failed)"
        
        return [TextContent(type="text", text=result)]
    
    async def _get_telemetry(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Get telemetry statistics."""
        days = arguments.get("days", 14)
        
        try:
            dashboard = TelemetryDashboard(self.repo_root)
            stats = dashboard.generate_stats(days)
            
            result = json.dumps(stats, indent=2)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting telemetry: {str(e)}")]
    
    async def _get_cache_stats(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Get cache statistics."""
        try:
            cache = ResultCache()
            stats = cache.get_stats()
            
            result = json.dumps(stats, indent=2)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting cache stats: {str(e)}")]
    
    async def _clear_cache(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Clear cache entries."""
        expired_only = arguments.get("expired_only", False)
        
        try:
            cache = ResultCache()
            if expired_only:
                removed = cache.cleanup_expired()
                result = f"Removed {removed} expired cache entries"
            else:
                removed = cache.invalidate()
                result = f"Cleared {removed} cache entries"
            
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error clearing cache: {str(e)}")]
    
    async def _health_check(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Perform health check."""
        try:
            # Check if required binaries are available
            import shutil
            
            checks = {
                "devin": shutil.which("devin") is not None,
                "codex": shutil.which("codex") is not None,
                "devin-delegate": shutil.which("devin-delegate") is not None
            }
            
            result = {
                "status": "healthy" if all(checks.values()) else "degraded",
                "checks": checks,
                "config_loaded": bool(self.config),
                "routing_loaded": bool(self.routing),
                "repo_root": str(self.repo_root)
            }
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error during health check: {str(e)}")]
    
    async def _batch_delegate(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Delegate multiple tasks in batch."""
        tasks = arguments.get("tasks", [])
        if not tasks:
            return [TextContent(type="text", text="Error: 'tasks' parameter is required")]
        
        parallel = arguments.get("parallel", False)
        max_workers = arguments.get("max_workers", 4)
        
        if parallel:
            # Use parallel batch processing
            try:
                from parallel_batch import run_parallel_batch
                
                # Create temporary batch file
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
                    for task_spec in tasks:
                        f.write(json.dumps(task_spec) + '\n')
                    batch_file = f.name
                
                try:
                    loop = asyncio.get_event_loop()
                    rc = await loop.run_in_executor(
                        None,
                        lambda: run_parallel_batch(
                            batch_file=batch_file,
                            context_file=None,
                            task_class=None,
                            config=self.config,
                            routing=self.routing,
                            repo_root=self.repo_root,
                            workspace=None,
                            dry_run=False,
                            quick=True,
                            interactive=False,
                            safety_check=False,
                            strict_safety=False,
                            max_workers=max_workers,
                            timeout_seconds=3600
                        )
                    )
                    result = f"Parallel batch completed with exit code: {rc}"
                finally:
                    os.unlink(batch_file)
                
            except ImportError:
                result = "Error: Parallel batch processing not available"
            except Exception as e:
                result = f"Error in parallel batch: {str(e)}"
        else:
            # Sequential processing
            results = []
            for i, task_spec in enumerate(tasks, 1):
                task = task_spec.get("task", "")
                task_class = task_spec.get("task_class")
                workspace = task_spec.get("workspace")
                
                workspace_path = Path(workspace) if workspace else self.repo_root
                
                loop = asyncio.get_event_loop()
                rc = await loop.run_in_executor(
                    None,
                    lambda: run_delegate(
                        task=task,
                        context_file=None,
                        task_class=task_class,
                        dry_run=False,
                        print_envelope=False,
                        config=self.config,
                        routing=self.routing,
                        repo_root=self.repo_root,
                        workspace=workspace_path,
                        show_cost=False,
                        timeout_override=None,
                        quick=True,
                        interactive=False,
                        safety_check=False,
                        strict_safety=False,
                        use_cache=True,
                        cache_ttl=86400,
                        fallback_provider_override=None,
                        fallback_model_override=None
                    )
                )
                
                results.append({
                    "task": task,
                    "exit_code": rc,
                    "success": rc == 0
                })
            
            successful = sum(1 for r in results if r["success"])
            result = f"Batch completed: {successful}/{len(results)} tasks successful"
            result += "\n" + json.dumps(results, indent=2)
        
        return [TextContent(type="text", text=result)]
    
    async def run(self):
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Main entry point."""
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not available. Install with: pip install mcp")
        sys.exit(1)
    
    server = DevinDelegateMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
