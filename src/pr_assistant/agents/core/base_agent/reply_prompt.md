🚨 Logging rules (strictly follow for CI log visibility):

- Before every **Read** tool call → output: `📂 Reading local file: <resolved path>`
- Before every **Bash** tool call that reads/processes a file → output: `📂 Reading local file: <resolved path>` (do NOT print the raw command)
- Do NOT narrate bash commands or print them as text — just output the `📂` line, then run the tool silently

## Pre-Fetched Data

Available files:
{file_lines}

output all available files you have:

1. xxx
2. xxx

---

## Step 2: Analyze Trigger Comment

Read /trigger_comment.json to understand what the user is asking.

{analysis_guideline_instruction}
If the trigger comment references specific code (check for path/line fields), read that code from the cloned repository.

Understand:

output answers to the below questions

1. What is the user asking? (code explanation / review clarification / process question / technical guidance)
2. How are you gonna do for answering user's question.

If code context is needed, read files directly from the cloned repository path provided above.

After investigation output: `🔍 Investigation findings: [files read], [key findings]`

---

## Step 3: Write Reply JSON

Output: `📂 Write a JSON file called {result_file}`

**CRITICAL - REQUIRED ACTION**: You MUST use the **write_file** tool (not text output) to write "{result_file}".

1. Use the write_file tool with file_path="{result_file}"
2. The content parameter must be a STRING, not a Python object. Pass the JSON as a string literal.
3. Do NOT just output JSON as text - you MUST use the write_file tool

Use the Write tool to write to {result_file}:

```json
{{
  "reply": "<natural greeting> [@\"<user_name>\"](https://github.com/<user_name>) <replay content>"
}}
```

Reply guidelines:

- Open with a natural greeting using the commenter's name
- Answer directly and concisely (2–4 sentences for simple questions, more for complex)
- Provide code examples if helpful
- When proposing code fixes in a reply, use GitHub's suggestion syntax:
  ```suggestion
  <your code here>
  ```
- Do NOT include a footer — Python appends it automatically

After writing: output `✅ Reply JSON written to: {result_file}`
