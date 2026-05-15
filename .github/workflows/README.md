# GitHub Actions Integration Templates

This directory contains GitHub Actions workflow templates for integrating devin-delegate into your CI/CD pipeline.

## Available Workflows

### 1. `devin-delegate-ci.yml`
**Purpose**: Main CI workflow for on-demand and automated Devin delegation

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches
- Manual workflow dispatch

**Features**:
- Environment validation and dependency installation
- Devin authentication configuration
- Task delegation with configurable task classes
- Parallel batch processing support
- Automatic telemetry dashboard generation
- Artifact upload for results and telemetry

**Usage**:
```yaml
# Manual trigger with custom task
- uses: ./.github/workflows/devin-delegate-ci.yml
  with:
    task: "Review the authentication module for security issues"
    task_class: "review"
```

**Required Secrets**:
- `DEVIN_API_KEY`: Your Devin API key for authentication

### 2. `devin-delegate-scheduled.yml`
**Purpose**: Scheduled automated reviews and analysis

**Triggers**:
- Daily schedule (midnight UTC)
- Weekly schedule (Sundays)
- Manual workflow dispatch

**Features**:
- Daily code quality and security reviews
- Comprehensive weekly analysis
- Automatic cache management
- Dashboard generation and artifact retention
- Summary reports in GitHub Actions UI

**Usage**:
```yaml
# Override schedule in your fork
on:
  schedule:
    - cron: '0 2 * * *'  # Run at 2 AM UTC
```

## Setup Instructions

### 1. Copy Workflows to Your Repository

```bash
# Copy the workflow templates to your repository
cp -r .github/workflows/*.yml /path/to/your/repo/.github/workflows/
```

### 2. Configure Required Secrets

1. Go to your repository Settings → Secrets and variables → Actions
2. Add the following secrets:
   - `DEVIN_API_KEY`: Your Devin API key
   - Optional: `CODEX_API_KEY` if using Codex fallback

### 3. Customize Workflows (Optional)

Edit the workflow files to customize:
- Task descriptions and classes
- Schedule timing
- Artifact retention periods
- Failure handling behavior

### 4. Test the Integration

```bash
# Trigger workflow manually via GitHub UI or CLI
gh workflow run "Devin Delegate CI.yml" -f task="Test task" -f task_class="implement"
```

## Advanced Usage

### Custom Task Templates

Create custom task templates in your workflow:

```yaml
- name: Custom task
  run: |
    devin-delegate \
      --template custom-audit \
      --var component="payment" \
      --var severity="high"
```

### Parallel Execution

Use batch processing for multiple tasks:

```yaml
- name: Create batch file
  run: |
    cat > tasks.jsonl << EOF
    {"task": "Review auth module", "task_class": "review"}
    {"task": "Check API endpoints", "task_class": "security-audit"}
    {"task": "Validate data models", "task_class": "review"}
    EOF

- name: Run batch
  run: |
    devin-delegate --batch tasks.jsonl --parallel --max-workers 3
```

### Conditional Execution

Add conditions based on file changes:

```yaml
- name: Run on code changes
  if: contains(github.event.head_commit.modified, 'src/')
  run: |
    devin-delegate --task "Review source changes" --task-class review
```

## Monitoring and Debugging

### View Telemetry

1. Download the `devin-delegate-telemetry` artifact
2. Open the HTML dashboard for visual analytics
3. Check CLI output for detailed logs

### Common Issues

**Authentication failures**:
- Verify `DEVIN_API_KEY` is set correctly
- Check API key permissions and expiration

**Timeout errors**:
- Increase timeout in workflow: `--timeout-override 600`
- Use fallback provider: `--fallback-provider kimi`

**Dependency issues**:
- Ensure `devin` CLI is installed in the runner
- Verify Python dependencies are compatible

## Best Practices

1. **Start with manual triggers** before enabling automatic schedules
2. **Use task classes** appropriately for better routing
3. **Monitor telemetry** to optimize costs and performance
4. **Set appropriate timeouts** based on task complexity
5. **Configure fallback providers** for reliability
6. **Review artifacts regularly** and clean up old data
7. **Use safety checks** for automated tasks on production code

## Support

For issues or questions:
- Check devin-delegate documentation: `devin-delegate --help`
- Review telemetry dashboard for patterns
- Consult main skill documentation in SKILL.md