#!/usr/bin/env python3
"""Agent 调试日志：写入仓库 logs/ 目录，不占用控制台（控制台仅保留正常对话）。

日志文件路径：<仓库根>/logs/<当前执行的 .py 主文件名>.log（追加写入）。
可通过环境变量 AGENT_LOG_CONSOLE=1 同时镜像到 stderr（带主/子角色颜色）。
"""

from __future__ import annotations

import atexit
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

# 本文件在 agents/ 下，仓库根为其上一级
_AGENTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AGENTS_DIR.parent
_LOGS_DIR = _REPO_ROOT / "logs"

LineClip = tuple[int, int]  # (head_lines, tail_lines)

RESET = "\033[0m"
COLOR_DEFAULT = ""
COLOR_MAIN = "\033[1;34m"  # 粗体蓝 — 主 agent
COLOR_SUB = "\033[1;35m"  # 粗体洋红 — subagent

LABEL_MAIN_AGENT = "主 Agent"
LABEL_SUBAGENT = "Subagent"

ROLE_DEFAULT = "default"
ROLE_MAIN = "main"
ROLE_SUB = "sub"

_log_lock = threading.Lock()
_log_path: str | None = None
_log_fp: TextIO | None = None

# 设为 1 / true / yes 时，除写文件外还按原样（含 ANSI）打印到 stderr
_MIRROR_CONSOLE = os.environ.get("AGENT_LOG_CONSOLE", "").lower() in (
    "1",
    "true",
    "yes",
)


def get_agent_log_path() -> str:
    """返回当前会话的日志文件路径（首次写入时打开 logs/<脚本名>.log）。"""
    _ensure_log_file()
    assert _log_path is not None
    return _log_path


def _executing_script_log_name() -> str:
    """取当前 Python 入口脚本主文件名 + .log（如 s04_subagent.log）。"""
    if not sys.argv:
        return "python.log"
    raw = sys.argv[0]
    path = Path(raw)
    try:
        path = path.resolve()
    except OSError:
        path = Path(raw)
    if path.suffix.lower() in (".py", ".pyw") and path.stem:
        return f"{path.stem}.log"
    stem = Path(raw).stem
    if stem and stem not in ("-",):
        return f"{stem}.log"
    return "python.log"


def _ensure_log_file() -> TextIO:
    global _log_path, _log_fp
    with _log_lock:
        if _log_fp is not None:
            return _log_fp
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOGS_DIR / _executing_script_log_name()
        _log_path = str(log_file)
        _log_fp = open(log_file, "a", encoding="utf-8")
        _log_fp.write(f"# session start {datetime.now().isoformat(timespec='seconds')}\n")
        _log_fp.flush()
        atexit.register(_close_log_file)
        return _log_fp


def _close_log_file() -> None:
    global _log_fp
    with _log_lock:
        if _log_fp is not None:
            try:
                _log_fp.write(f"# session end {datetime.now().isoformat(timespec='seconds')}\n")
                _log_fp.flush()
                _log_fp.close()
            except OSError:
                pass
            _log_fp = None


def clip_text_by_lines(text: str, head: int, tail: int) -> str:
    """过长时只保留前 head 行与后 tail 行，中间用省略标记。"""
    if head < 1 or tail < 1:
        return text
    lines = text.splitlines()
    n = len(lines)
    if n <= head + tail:
        return text
    omitted = n - head - tail
    mid = f"... （省略 {omitted} 行）..."
    return "\n".join([*lines[:head], mid, *lines[-tail:]])


class AgentLogger:
    """日志写入仓库 logs/<脚本名>.log（追加）；不在 stdout 打印（避免干扰对话）。"""

    def __init__(self, role: str = ROLE_DEFAULT, *, enabled: bool = True) -> None:
        self.role = role
        self.enabled = enabled

    def _color(self) -> str:
        if self.role == ROLE_MAIN:
            return COLOR_MAIN
        if self.role == ROLE_SUB:
            return COLOR_SUB
        return COLOR_DEFAULT

    def _tag(self) -> str:
        if self.role == ROLE_MAIN:
            return LABEL_MAIN_AGENT
        if self.role == ROLE_SUB:
            return LABEL_SUBAGENT
        return ""

    def emit(self, msg: str) -> None:
        if not self.enabled:
            return
        fp = _ensure_log_file()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = msg.splitlines() if msg else [""]
        with _log_lock:
            for line in lines:
                fp.write(f"{ts} [{self.role}] {line}\n")
            fp.flush()
        if _MIRROR_CONSOLE:
            c = self._color()
            out = f"{c}{msg}{RESET}" if c else msg
            print(out, file=sys.stderr)

    @staticmethod
    def summarize_message(msg: dict, max_len: int = 400) -> str:
        role = msg.get("role", "?")
        content = msg.get("content")
        if isinstance(content, str):
            body = content[:max_len] + ("…" if len(content) > max_len else "")
            return f"{role}: {body!r}"
        if isinstance(content, list):
            parts = []
            for b in content:
                if isinstance(b, dict):
                    t = b.get("type", "?")
                    if t == "text":
                        tx = (b.get("text") or "")[:max_len]
                        parts.append(f"text:{tx!r}")
                    elif t == "tool_result":
                        tid = b.get("tool_use_id", "")
                        c = str(b.get("content", ""))[:200]
                        parts.append(f"tool_result({tid[:8]}…):{c!r}")
                    else:
                        parts.append(str(b)[:200])
                elif getattr(b, "type", None) == "text":
                    tx = (getattr(b, "text", None) or "")[:max_len]
                    parts.append(f"text:{tx!r}")
                elif getattr(b, "type", None) == "tool_use":
                    parts.append(f"tool_use:{getattr(b, 'name', '?')!r}")
                else:
                    parts.append(str(type(b).__name__))
            return f"{role}: [{'; '.join(parts)}]"
        return f"{role}: {type(content).__name__}"

    def messages_context(
        self,
        messages: list,
        label: str,
        *,
        latest_only: bool = False,
    ) -> None:
        tag = self._tag()
        n = len(messages)
        if latest_only:
            if tag:
                self.emit(
                    f"\n--- [{tag}] {label}（共 {n} 条；仅展示最新 1 条）---",
                )
            else:
                self.emit(f"\n--- {label} (共 {n} 条；仅展示最新 1 条) ---")
            if messages:
                last = messages[-1]
                self.emit(f"  [最新 #{n - 1}] {self.summarize_message(last)}")
            else:
                self.emit("  (无消息)")
        else:
            if tag:
                self.emit(f"\n--- [{tag}] {label}（共 {n} 条）---")
            else:
                self.emit(f"\n--- {label} (共 {n} 条) ---")
            for i, m in enumerate(messages):
                self.emit(f"  [{i}] {self.summarize_message(m)}")
        self.emit("---")

    def llm_response(
        self,
        turn: int,
        response: Any,
        *,
        output_line_clip: LineClip | None = None,
    ) -> None:
        tag = self._tag()
        if tag:
            head = f"[{tag} · LLM 回合 {turn}]"
        else:
            head = f"[LLM 回合 {turn}]"
        lines = [
            f"\n{'='*60}",
            f"{head} id={getattr(response, 'id', '?')}",
            f"  stop_reason={response.stop_reason!r}",
        ]
        usage = getattr(response, "usage", None)
        if usage is not None:
            it = getattr(usage, "input_tokens", None)
            ot = getattr(usage, "output_tokens", None)
            lines.append(f"  usage: input_tokens={it} output_tokens={ot}")
        lines.append(f"{'='*60}")
        self.emit("\n".join(lines))
        for block in response.content:
            if block.type == "text":
                preview = (block.text or "").strip()
                if preview:
                    body = (
                        clip_text_by_lines(preview, *output_line_clip)
                        if output_line_clip
                        else preview
                    )
                    self.emit("[assistant 文本]\n" + body)
            elif block.type == "tool_use":
                self.emit(f"[tool_use] {block.name}")
                try:
                    dumped = json.dumps(block.input, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    dumped = str(block.input)
                self.emit(
                    clip_text_by_lines(dumped, *output_line_clip)
                    if output_line_clip
                    else dumped
                )

    def tool_results_summary(
        self,
        results: list,
        *,
        content_line_clip: LineClip | None = None,
    ) -> None:
        tag = self._tag()
        if tag:
            self.emit(f"\n--- [{tag}] 本回合返回给模型的 tool_result 摘要 ---")
        else:
            self.emit("\n--- 本回合返回给模型的 tool_result 摘要 ---")
        for r in results:
            if isinstance(r, dict) and r.get("type") == "tool_result":
                raw = str(r.get("content", ""))
                if content_line_clip:
                    c = clip_text_by_lines(raw, *content_line_clip)
                else:
                    c = raw[:300] + ("…" if len(raw) > 300 else "")
                tid = str(r.get("tool_use_id", ""))[:12]
                self.emit(f"  tool_use_id={tid}… content={c!r}")
            elif isinstance(r, dict) and r.get("type") == "text":
                inj = str(r.get("text", ""))
                if content_line_clip:
                    inj = clip_text_by_lines(inj, *content_line_clip)
                self.emit(f"  injected: {inj!r}")

    def tool_execution(
        self,
        tool_name: str,
        output: Any,
        *,
        tool_input: Any | None = None,
        max_len: int = 2000,
        bracket_tag: bool = False,
        line_clip: LineClip | None = None,
    ) -> None:
        """记录本地工具执行：可选参数 tool_input（如 LLM 传入的 JSON）+ 本地返回值。"""
        tag = self._tag()
        role_hint = f"[{tag}] " if bracket_tag and tag else ""
        self.emit(f"\n--- {role_hint}[本地执行] {tool_name} ---")
        if tool_input is not None:
            try:
                inp = json.dumps(tool_input, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                inp = str(tool_input)
            self.emit("  参数:")
            for line in inp.splitlines() or [""]:
                self.emit(f"    {line}")
        self.emit("  输出（本地结果）:")
        out_s = str(output)
        if line_clip:
            body = clip_text_by_lines(out_s, *line_clip)
        else:
            body = out_s[:max_len] + ("…" if len(out_s) > max_len else "")
        for line in body.splitlines() or [""]:
            self.emit(f"    {line}")


# 默认实例：无角色色，供单 Agent 脚本使用
logger = AgentLogger()

# 主 / 子 Agent 常用实例（s04 等）
main_logger = AgentLogger(ROLE_MAIN)
sub_logger = AgentLogger(ROLE_SUB)
