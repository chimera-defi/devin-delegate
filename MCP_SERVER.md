# MCP Server for Devin Delegate

This directory contains an MCP (Model Context Protocol) server that exposes devin-delegate functionality as MCP tools, enabling integration with MCP-compatible systems.

## Installation

### Prerequisites

- Python 3.8+
- MCP SDK: `pip install mcp`
- devin-delegate skill installed and configured
- Devin CLI: `devin`
- Optional fallback CLIs: `codex`, `kimi`, `anthropic`

### Setup

1. **Install MCP SDK**:
```bash
pip install mcp
```

2. **Make the server executable**:
```bash
chmod +x scripts/mcp_server.py
```

3. **Test the server**:
```bash
python3 scripts/mcp_server.py
```

## Available MCP Tools

### 1. `delegate_task`
Delegate a task to Devin with structured envelope and fallback routing.

**Parameters**:
- `task` (required): Task description to delegate to Devin
- `task_class` (optional): Task classification - "research", "implement", "debug", "review", "browser"
- `workspace` (optional): Workspace directory path
- `use_cache` (optional): Enable result caching (default: true)
- `safety_check` (optional): Run safety checks before delegation (default: false)
- `fallback_engine` (optional): Override fallback engine - "codex", "kimi", "anthropic", "pi"
- `fallback_provider` (optional): Deprecated alias for `fallback_engine`
- `fallback_pi_provider` (optional): Provider passed to pi fallback (for example "kimi-coding", "openai")
- `timeout_override` (optional): Override timeout in seconds

**Example**:
```json
{
  "task": "Review the authentication module for security issues",
  "task_class": "review",
  "safety_check": true,
  "use_cache": true
}
```

### 2. `get_telemetry`
Get telemetry statistics for devin-delegate usage.

**Parameters**:
- `days` (optional): Number of days to analyze (default: 14)

**Example**:
```json
{
  "days": 7
}
```

### 3. `get_cache_stats`
Get result cache statistics.

**Parameters**: None

**Example**:
```json
{}
```

### 4. `clear_cache`
Clear result cache entries.

**Parameters**:
- `expired_only` (optional): Only clear expired entries (default: false)

**Example**:
```json
{
  "expired_only": true
}
```

### 5. `health_check`
Perform health check on devin-delegate environment.

**Parameters**: None

**Example**:
```json
{}
```

### 6. `batch_delegate`
Delegate multiple tasks in batch.

**Parameters**:
- `tasks` (required): Array of task specifications
- `parallel` (optional): Enable parallel processing (default: false)
- `max_workers` (optional): Maximum parallel workers (default: 4)

**Example**:
```json
{
  "tasks": [
    {
      "task": "Review auth module",
      "task_class": "review"
    },
    {
      "task": "Check API endpoints",
      "task_class": "security-audit"
    }
  ],
  "parallel": true,
  "max_workers": 2
}
```

## Integration Examples

### Claude Desktop Integration

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "devin-delegate": {
      "command": "python3",
      "args": ["/path/to/devin-delegate/scripts/mcp_server.py"],
      "env": {
        "DEVIN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Cline (VS Code) Integration

Add to your Cline settings:

```json
{
  "mcpServers": {
    "devin-delegate": {
      "command": "python3",
      "args": ["/path/to/devin-delegate/scripts/mcp_server.py"]
    }
  }
}
```

### Custom MCP Client

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Create server parameters
    server_params = StdioServerParameters(
        command="python3",
        args=["/path/to/mcp_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize session
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {[tool.name for tool in tools.tools]}")
            
            # Call a tool
            result = await session.call_tool("delegate_task", {
                "task": "Review code for bugs",
                "task_class": "review"
            })
            print(f"Result: {result}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Configuration

### Environment Variables

- `DEVIN_API_KEY`: Devin API key for authentication
- `CODEX_API_KEY`: Codex API key for fallback
- `WORKSPACE_DEFAULT`: Default workspace directory

### Server Configuration

The server loads configuration from:
1. `config/devin-delegate.json` - Main configuration
2. `config/routing.json` - Task routing configuration
3. `config/pricing.json` - Provider pricing configuration

## Usage Patterns

### Sequential Task Delegation

```python
# Delegate tasks one by one
result1 = await session.call_tool("delegate_task", {
    "task": "Implement feature A",
    "task_class": "implement"
})

result2 = await session.call_tool("delegate_task", {
    "task": "Test feature A",
    "task_class": "debug"
})
```

### Parallel Batch Processing

```python
# Process multiple tasks in parallel
result = await session.call_tool("batch_delegate", {
    "tasks": [
        {"task": "Task 1", "task_class": "implement"},
        {"task": "Task 2", "task_class": "review"},
        {"task": "Task 3", "task_class": "debug"}
    ],
    "parallel": true,
    "max_workers": 3
})
```

### Monitoring and Telemetry

```python
# Get usage statistics
telemetry = await session.call_tool("get_telemetry", {"days": 7})

# Check cache performance
cache_stats = await session.call_tool("get_cache_stats", {})

# Perform health check
health = await session.call_tool("health_check", {})
```

## Error Handling

The MCP server provides structured error responses:

```json
{
  "content": [
    {
      "type": "text",
      "text": "Error: Task delegation failed with exit code 126 (Auth error)"
    }
  ]
}
```

Common error codes:
- `0`: Success
- `2`: Configuration or input error
- `126`: Authentication error
- `124`: Timeout
- `127`: Missing dependency

## Performance Considerations

1. **Caching**: Enable caching for repeated tasks to reduce costs
2. **Parallel Processing**: Use batch processing for independent tasks
3. **Timeout Configuration**: Adjust timeouts based on task complexity
4. **Fallback Providers**: Configure appropriate fallbacks for reliability

## Security

1. **API Keys**: Never commit API keys to version control
2. **Safety Checks**: Enable safety checks for automated tasks
3. **Workspace Isolation**: Use appropriate workspace directories
4. **Access Control**: Limit MCP server access to authorized systems

## Troubleshooting

### Server won't start
- Verify MCP SDK is installed: `pip list | grep mcp`
- Check Python version: `python3 --version`
- Verify devin-delegate modules are accessible

### Tools return errors
- Check Devin authentication: `devin auth status`
- Verify configuration files are valid JSON
- Check workspace permissions
- Review logs for detailed error messages

### Performance issues
- Enable caching for repeated tasks
- Use appropriate task classes for routing
- Adjust timeout values for complex tasks
- Monitor telemetry for patterns

## Development

### Adding New Tools

1. Add tool definition in `_setup_handlers()`
2. Implement handler method
3. Update documentation
4. Test with MCP client

### Testing

```bash
# Test server directly
python3 scripts/mcp_server.py

# Test with Claude Desktop
# Add to config and restart Claude

# Test with custom client
python3 test_mcp_client.py
```

## License

This MCP server is part of the devin-delegate skill and follows the same license terms.

## Support

For issues or questions:
- Check devin-delegate documentation: `devin-delegate --help`
- Review MCP documentation: https://modelcontextprotocol.io
- Consult main skill documentation in SKILL.md
