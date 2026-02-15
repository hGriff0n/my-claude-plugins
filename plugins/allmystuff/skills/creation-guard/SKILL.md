---
name: creation-guard
description: Analyze existing skills, agents, commands before creating new ones. Prevents duplicates and suggests iterations. Use when claude is about to create any new skill, agent, slash command, or CLI tool.
---

# Creation Guard

Prevents duplicate functionality and enforces analysis before creating new Claude Code artifacts.

---

## Purpose

Before creating ANY new:
- Skill (`~/.claude/skills/*/SKILL.md`)
- Agent (`~/.claude/agents/*.md`)
- Slash command (`~/.claude/commands/*.md`)
- CLI tool (`~/bin/*`)

This skill MUST be invoked to:
1. Search for existing artifacts with similar functionality
2. Identify potential overlap or extension opportunities
3. Present findings with recommendation
4. Get explicit user approval before proceeding

## Trigger Phrases

Invoke this skill when you detect:
- "Create a skill for..."
- "I want a new command that..."
- "Let's add an agent for..."
- "Build a CLI tool to..."
- Any intent to create new automation/tooling

---

## Analysis Process

### Step 1: Identify the Proposal

Extract from the request:
- **Name**: Proposed name for the artifact
- **Type**: skill | agent | command | cli-tool
- **Purpose**: What it does (one sentence)
- **Key Functions**: 3-5 main capabilities
- **Keywords**: Searchable terms related to functionality

### Step 2: Search Existing Artifacts

Run these searches in parallel:

```bash
# Skills - search names and descriptions
for skill in ~/.claude/skills/*/SKILL.md; do
  echo "=== $(basename $(dirname $skill)) ==="
  head -20 "$skill"
done

# Agents - search all agent definitions
for agent in ~/.claude/agents/*.md; do
  echo "=== $(basename $agent) ==="
  head -20 "$agent"
done

# Commands - search all command definitions
for cmd in ~/.claude/commands/*.md; do
  echo "=== $(basename $cmd) ==="
  head -10 "$cmd"
done

# CLI tools - list with descriptions
ls -la ~/bin/
```

Also search by keywords:
```bash
grep -ril "[keyword]" ~/.claude/skills/ ~/.claude/agents/ ~/.claude/commands/
```

### Step 3: Analyze Overlap

For each potentially related artifact, assess:

| Criterion | Question |
|-----------|----------|
| Functional overlap | Does it do the same thing? (0-100%) |
| Naming confusion | Could names be confused? |
| Extension potential | Could the proposal extend this instead? |
| Composition | Could existing artifacts compose to achieve this? |

### Step 4: Generate Recommendation

Based on analysis, recommend ONE of:

| Recommendation | Criteria | Action |
|----------------|----------|--------|
| **PROCEED** | <20% overlap, genuinely new capability | Create new artifact |
| **EXTEND** | 50%+ overlap with single existing artifact | Modify existing instead |
| **COMPOSE** | Multiple artifacts cover 80%+ combined | Create thin wrapper or document workflow |
| **ITERATE** | 20-50% overlap, proposal needs refinement | Refine proposal to differentiate |
| **BLOCK** | Would create problematic duplication | Do not create |

---

## Output Format

```
════════════════════════════════════════════════════════════════
CREATION GUARD ANALYSIS
════════════════════════════════════════════════════════════════

PROPOSAL:
  Type: [skill|agent|command|cli-tool]
  Name: [proposed-name]
  Purpose: [one sentence]

EXISTING ARTIFACTS ANALYZED: [count]

RELATED ARTIFACTS FOUND:

1. [artifact-name] ([type])
   Purpose: [what it does]
   Overlap: [X]% - [explanation]

2. [artifact-name] ([type])
   Purpose: [what it does]
   Overlap: [X]% - [explanation]

RECOMMENDATION: [PROCEED|EXTEND|COMPOSE|ITERATE|BLOCK]

RATIONALE:
[2-3 sentences explaining the recommendation]

SUGGESTED ACTION:
[Specific next step based on recommendation]

════════════════════════════════════════════════════════════════
Proceed with creation? (y/n/discuss)
════════════════════════════════════════════════════════════════
```

---

## Recommendation Details

### PROCEED
- Artifact is genuinely new
- No significant overlap found
- Clear differentiation from existing tools
- Go ahead and create

### EXTEND
Present extension proposal:
```
Instead of creating [new-name], extend [existing-name]:

Current capabilities:
- [existing feature 1]
- [existing feature 2]

Proposed additions:
- [new feature 1]
- [new feature 2]

This approach:
- Maintains single source of truth
- Reduces cognitive load
- Leverages existing testing/documentation
```

### COMPOSE
Present composition approach:
```
The proposed functionality can be achieved by combining:

1. [artifact-1] - handles [aspect]
2. [artifact-2] - handles [aspect]

Options:
A) Document this workflow (no new code)
B) Create thin orchestration command
C) Add to existing skill's "integration" section
```

### ITERATE
Present refinement questions:
```
Overlap detected with [existing-artifact].

Differentiation needed:
1. [question about scope]
2. [question about use case]
3. [question about implementation]

Please clarify to proceed.
```

### BLOCK
Explain why creation should not proceed:
```
BLOCKED: Would create problematic duplication.

Existing artifact: [name]
- Already does: [capabilities]
- Your request: [same capabilities]

Alternative actions:
1. Use existing: /[command] or run [skill]
2. If missing features, extend the existing artifact
3. If different use case, explain how this differs
```

---

## Integration with Workflow

### Hook into Creation Patterns

When Claude detects intent to create new artifacts, it should:

1. **Pause** - Do not start writing the artifact
2. **Invoke** - Run this skill's analysis
3. **Present** - Show findings to user
4. **Confirm** - Get explicit approval before proceeding
5. **Document** - If proceeding, note the analysis was done

### Self-Check Questions

Before creating ANY new artifact, Claude should ask itself:

1. Does something similar already exist?
2. Could this be added to an existing artifact?
3. Would a user know to look for this vs the existing one?
4. Am I creating this because it's needed or because it's easier than finding what exists?

---

## Examples

### Example 1: Duplicate Detection

User: "Create a skill for detecting AI-generated writing patterns"

Analysis finds: `slop-detector` skill already exists with 95% functional overlap.

**Recommendation: BLOCK**
- slop-detector already detects AI writing patterns
- Same detection framework, same output format
- User should use existing skill

### Example 2: Extension Opportunity

User: "Create a command for logging work to projects"

Analysis finds: `log-to-daily` skill exists (70% overlap)

**Recommendation: EXTEND**
- log-to-daily logs to daily notes
- Proposal wants project-specific logging
- Suggest: Add project targeting to existing skill OR create thin wrapper

### Example 3: Genuine New Need

User: "Create a skill for managing analytics dashboards"

Analysis finds: No existing analytics skills.

**Recommendation: PROCEED**
- New capability not covered by existing artifacts
- Clear differentiation from other tools
- Proceed with creation

---

## Success Criteria

This skill is complete when:
- All artifact types searched (skills, agents, commands, cli-tools)
- Related artifacts identified with overlap assessment
- Clear recommendation provided with rationale
- User has explicitly acknowledged the analysis
- If PROCEED: Creation can begin
- If not PROCEED: Alternative action documented