#!/usr/bin/env python3
# Harness: context isolation -- protecting the model's clarity of thought.
"""
s04_subagent.py - Subagents

Spawn a child agent with fresh messages=[]. The child works in its own
context, sharing the filesystem, then returns only a summary to the parent.

    Parent agent                     Subagent
    +------------------+             +------------------+
    | messages=[...]   |             | messages=[]      |  <-- fresh
    |                  |  dispatch   |                  |
    | tool: task       | ---------->| while tool_use:  |
    |   prompt="..."   |            |   call tools     |
    |   description="" |            |   append results |
    |                  |  summary   |                  |
    |   result = "..." | <--------- | return last text |
    +------------------+             +------------------+
              |
    Parent context stays clean.
    Subagent context is discarded.

Key insight: "Fresh messages=[] gives context isolation. The parent stays clean."

Note: Real Claude Code also uses in-process isolation (not OS-level process
forking). The child runs in the same process with a fresh message array and
isolated tool context -- same pattern as this teaching implementation.

    Comparison with real Claude Code:
    +-------------------+------------------+----------------------------------+
    | Aspect            | This demo        | Real Claude Code                 |
    +-------------------+------------------+----------------------------------+
    | Backend           | in-process only  | 5 backends: in-process, tmux,    |
    |                   |                  | iTerm2, fork, remote             |
    | Context isolation | fresh messages=[]| createSubagentContext() isolates  |
    |                   |                  | ~20 fields (tools, permissions,  |
    |                   |                  | cwd, env, hooks, etc.)           |
    | Tool filtering    | manually curated | resolveAgentTools() filters from |
    |                   |                  | parent pool; allowedTools         |
    |                   |                  | replaces all allow rules         |
    | Agent definition  | hardcoded system | .claude/agents/*.md with YAML    |
    |                   | prompt           | frontmatter (AgentTemplate)      |
    +-------------------+------------------+----------------------------------+
"""

import os
import re
import subprocess
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from log import clip_text_by_lines, main_logger, sub_logger

# 日志：仅展示最新一条消息；长输出按行保留首尾各若干行
S04_LOG_LINE_CLIP = (4, 4)

load_dotenv(override=True)

if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]

SYSTEM = f"You are a coding agent at {WORKDIR}. Use the task tool to delegate exploration or subtasks."
SUBAGENT_SYSTEM = f"You are a coding subagent at {WORKDIR}. Complete the given task, then summarize your findings."


class AgentTemplate:
    """
    Parse agent definition from markdown frontmatter.

    Real Claude Code loads agent definitions from .claude/agents/*.md.
    Frontmatter fields: name, tools, disallowedTools, skills, hooks,
    model, effort, permissionMode, maxTurns, memory, isolation, color,
    background, initialPrompt, mcpServers.
    3 sources: built-in, custom (.claude/agents/), plugin-provided.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.stem
        self.config = {}
        self.system_prompt = ""
        self._parse()

    def _parse(self):
        text = self.path.read_text()
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not match:
            self.system_prompt = text
            return
        for line in match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                self.config[k.strip()] = v.strip()
        self.system_prompt = match.group(2).strip()
        self.name = self.config.get("name", self.name)


# -- Tool implementations shared by parent and child --
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}

# Child gets all base tools except task (no recursive spawning)
CHILD_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
]


# -- Subagent: fresh context, filtered tools, summary-only return --
def run_subagent(prompt: str, *, verbose: bool = True) -> str:
    sub_messages = [{"role": "user", "content": prompt}]  # fresh context
    response = None
    for sub_turn in range(1, 31):  # safety limit
        if verbose:
            sub_logger.messages_context(
                sub_messages, "调用 API 前的消息历史", latest_only=True,
            )
        response = client.messages.create(
            model=MODEL, system=SUBAGENT_SYSTEM, messages=sub_messages,
            tools=CHILD_TOOLS, max_tokens=8000,
        )
        if verbose:
            sub_logger.llm_response(
                sub_turn, response, output_line_clip=S04_LOG_LINE_CLIP,
            )
        sub_messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                sub_logger.tool_execution(
                    block.name,
                    output,
                    tool_input=block.input,
                    bracket_tag=True,
                    line_clip=S04_LOG_LINE_CLIP,
                )
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)[:50000]})
        if verbose:
            sub_logger.tool_results_summary(
                results, content_line_clip=S04_LOG_LINE_CLIP,
            )
        sub_messages.append({"role": "user", "content": results})
    # Only the final text returns to the parent -- child context is discarded
    if response is None:
        return "(no summary)"
    return "".join(b.text for b in response.content if hasattr(b, "text")) or "(no summary)"


# -- Parent tools: base tools + task dispatcher --
PARENT_TOOLS = CHILD_TOOLS + [
    {"name": "task", "description": "Spawn a subagent with fresh context. It shares the filesystem but not conversation history.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "description": {"type": "string", "description": "Short description of the task"}}, "required": ["prompt"]}},
]


def agent_loop(messages: list, *, verbose: bool = True):
    main_turn = 0
    while True:
        main_turn += 1
        if verbose:
            main_logger.messages_context(
                messages, "调用 API 前的消息历史", latest_only=True,
            )
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=PARENT_TOOLS, max_tokens=8000,
        )
        if verbose:
            main_logger.llm_response(
                main_turn, response, output_line_clip=S04_LOG_LINE_CLIP,
            )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "task":
                    desc = block.input.get("description", "subtask")
                    prompt = block.input.get("prompt", "")
                    prompt_preview = clip_text_by_lines(
                        prompt, *S04_LOG_LINE_CLIP,
                    )
                    main_logger.emit(
                        f"\n> [主 Agent] 委派 task ({desc}):\n{prompt_preview}",
                    )
                    output = run_subagent(prompt, verbose=verbose)
                    main_logger.emit(
                        "\n[主 Agent] task 返回摘要（首尾若干行）:\n"
                        + clip_text_by_lines(str(output), *S04_LOG_LINE_CLIP),
                    )
                else:
                    handler = TOOL_HANDLERS.get(block.name)
                    output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                    main_logger.tool_execution(
                        block.name,
                        output,
                        tool_input=block.input,
                        bracket_tag=True,
                        line_clip=S04_LOG_LINE_CLIP,
                    )
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        if verbose:
            main_logger.tool_results_summary(
                results, content_line_clip=S04_LOG_LINE_CLIP,
            )
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms04 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()
