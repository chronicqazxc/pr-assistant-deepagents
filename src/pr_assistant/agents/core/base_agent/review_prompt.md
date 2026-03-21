🚨 Logging rules (strictly follow for CI log visibility):

- Before every **Read** tool call → output: `📂 Reading local file: <resolved path>`
- Before every **Bash** tool call that reads/processes a file → output: `📂 Reading local file: <resolved path>` (do NOT print the raw command)
- Do NOT narrate bash commands or print them as text — just output the `📂` line, then run the tool silently
- At the start of each step → output the step header exactly as shown below

---

Review this GitHub pull request: {base_pr_url}

---

## Step 1: Review the PR data embedded below

The PR metadata, diff, and comments are provided directly below in this message. Use them directly - do NOT try to read external files. Do NOT use the read_file tool - all data is already in this prompt.

{file_locations}

---

## Step 2: Analyze Code

**Output at start:** `--- ### Step 2: Analyzing code`

Output your intent and plan:

```
🎯 User intent: <one sentence>
📋 Review plan: <focus adjustments based on user intent>
```

{analysis_guideline_instruction}

Process each file from the PR diff **SEQUENTIALLY** — complete one before starting the next.

For each file:

1. Output: `📂 Reading local file: <cloned_repo_path>/<file_path>` then read it
2. Analyze and identify issues
3. Use Grep for surrounding context when needed

**MAJOR Validation** — before recording any MAJOR finding:
a. Re-read the exact code location (±5 lines around the issue)
b. Check whether the code is already safe (null guards, lifecycle management, thread safety, etc.)
c. Confirmed → continue to (d) | Uncertain → downgrade to MINOR | False positive → discard
d. Check `line_type` from the diff: if `CONTEXT` → the bug existed before this PR → record as **PRE_EXISTING** (🟣) instead

When in doubt, prefer MINOR over MAJOR. Pre-existing bugs must always use severity `PRE_EXISTING` — never MAJOR.

**Look up line_type from diff JSON** for each finding:

```bash
DIFF_FILE=$(bash -c 'echo $PR_DIFF_FILE')
LINE_TYPE=$(jq -r --arg path "<FILE_PATH>" --argjson line <LINE_NUMBER> '
  .diffs[] | select(.destination.toString == $path) |
  .hunks[].segments[] |
  select(.lines[] | .destination == $line) |
  .type
' "$DIFF_FILE" 2>/dev/null | head -1)
LINE_TYPE="${{LINE_TYPE:-CONTEXT}}"
```

**Finding the actual line number:**
The diff shows line numbers from the BASE branch, but the cloned repo is the PR SOURCE branch. To find the correct line number:

1. Read the file from the cloned repo
2. Search for the specific code (the added/removed lines appear in the diff)
3. Count the actual line number in the cloned file - THIS is your `line_number`

Do NOT use the line numbers from the diff directly - they refer to the base branch, not the source branch.

**Path format:**

- Use the EXACT path from the diff
- Do NOT duplicate folder names

---

## Step 3: Write Review JSON

**Output at start:** `--- ### Step 3: Writing review JSON`

**Check for RE-REVIEW:** If PR activities contain a prior `# 🤖 PR Review` + NEEDS_WORK status from the bot → use `PR Re-Review` title and add `**Blocker Status**: ✅ X fixed | ❌ Y remain`.

**CRITICAL - REQUIRED ACTION**: You MUST use the **write_file** tool (not text output) to write "review_result.json".

1. Use the write_file tool with file_path="review_result.json"
2. Write the JSON content using write_file
3. Do NOT just output JSON as text - you MUST use the write_file tool

The file may already exist - use write_file to overwrite it. This is the ONLY way to produce output.

Output JSON format:

```json
{{
  "inline_comments": [
    {{
      "file_path": "EXACT_PATH_FROM_DIFF",
      "line_number": ACTUAL_LINE_NUMBER_IN_CLONED_REPO,
      "line_type": "ADDED|REMOVED|CONTEXT",
      "severity": "MAJOR|MINOR|PRE_EXISTING",
      "comment": "Your comment here"
    }}
  ],
  "summary": "# 🤖 PR Review\\n\\n**Review Request**: ...\\n**Findings**: ...\\n**Decision**: ...",
  "decision": "approve|needs_work"
}}
```

Summary template (NO footer — Python appends it):

```
# 🤖 PR Review

**Review Request**: [trigger text, remove @"bot-name" to avoid re-triggering]
**Jira**: [KEY] [summary] — ✅ Addressed | ⚠️ Partially | ❌ Not addressed | N/A
**Findings**: 🔴 X | 🔵 X | 🟣 X
**Decision**: ✅ Approved | ❌ Needs Work
**Next Steps**: [brief instruction]
```

Rules: use ONLY these fields, no extra sections. `decision`: `"approve"` if no MAJOR, `"needs_work"` otherwise. PRE_EXISTING findings never affect the decision.

After outputting JSON: output `✅ Review complete`
