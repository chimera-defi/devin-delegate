# Meta Learnings — 2026-05-31

## Session: SharedStake iterative security audit

### 1. Circular deploy dependency detection should be a standard completeness check

Found: `stakingCore → oracleAdapter → validatorModule → stakingRouter → stakingCore`
would deadlock hardhat-deploy. Add "verify no circular func.dependencies chains" to
every deploy-script completeness review task.

### 2. Devin-generated Foundry merkle builders need OZ-compatibility verification

`DebtPoolFuzz.t.sol` from Devin used unsorted pair hashing. OZ requires sorted pairs.
Template: always ask Devin to verify Foundry merkle helpers against OZ MerkleProof.verify
or use single-leaf/two-leaf trees (no sorting edge cases).

### 3. Batch multiple checks into one Devin call with specific sub-tasks

Instead of 3 separate calls for "check keepers", "check deploy deps", "check test coverage",
combine into one structured task with numbered checks. Each check gets its own evidence
section. Saves ~60% overhead cost.

### 4. For test coverage gaps, ask for specific file creation, not generic "add tests"

"Add MigrationHelper integration tests" is too vague. Effective pattern:
"Create test/foundry/MigrationHelperFuzz.t.sol with tests for: (1) announceMigration notice
period enforcement, (2) activateMigration reverts before notice period, (3) GOV-only access
control. Use forge-std Test. Import MigrationHelper from contracts/..."

### 5. Token savings: provide file paths with line ranges, not open-ended questions

"Read deploy/004_stakingCore.ts line 65. Is oracleAdapter in func.dependencies?" costs
far less than "review all deploy scripts for dependency issues."
