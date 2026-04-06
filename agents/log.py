#!/usr/bin/env python3
"""终端 LLM / Agent 交互日志：支持默认输出与主/子 Agent 分色。"""

from __future__ import annotations

import json
from typing import Any

RESET = "\033[0m"
COLOR_DEFAULT = ""
COLOR_MAIN = "\033[1;34m"  # 粗体蓝 — 主 agent
COLOR_SUB = "\033[1;35m"  # 粗体洋红 — subagent

LABEL_MAIN_AGENT = "主 Agent"
LABEL_SUBAGENT = "Subagent"

ROLE_DEFAULT = "default"
ROLE_MAIN = "main"
ROLE_SUB = "sub"


class AgentLogger:
    """按角色着色打印；role=default 时不加 ANSI 色。"""

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
        c = self._color()
        if c:
            print(f"{c}{msg}{RESET}")
        else:
            print(msg)

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

    def messages_context(self, messages: list, label: str) -> None:
        tag = self._tag()
        if tag:
            self.emit(f"\n--- [{tag}] {label}（共 {len(messages)} 条）---")
        else:
            self.emit(f"\n--- {label} (共 {len(messages)} 条) ---")
        for i, m in enumerate(messages):
            self.emit(f"  [{i}] {self.summarize_message(m)}")
        self.emit("---")

    def llm_response(self, turn: int, response: Any) -> None:
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
                    self.emit("[assistant 文本]\n" + preview)
            elif block.type == "tool_use":
                self.emit(f"[tool_use] {block.name}")
                try:
                    self.emit(json.dumps(block.input, ensure_ascii=False, indent=2))
                except (TypeError, ValueError):
                    self.emit(str(block.input))

    def tool_results_summary(self, results: list) -> None:
        tag = self._tag()
        if tag:
            self.emit(f"\n--- [{tag}] 本回合返回给模型的 tool_result 摘要 ---")
        else:
            self.emit("\n--- 本回合返回给模型的 tool_result 摘要 ---")
        for r in results:
            if isinstance(r, dict) and r.get("type") == "tool_result":
                c = str(r.get("content", ""))[:300]
                tid = str(r.get("tool_use_id", ""))[:12]
                self.emit(f"  tool_use_id={tid}… content={c!r}…")
            elif isinstance(r, dict) and r.get("type") == "text":
                self.emit(f"  injected: {r.get('text', '')!r}")

    def tool_execution(
        self,
        tool_name: str,
        output: Any,
        *,
        max_len: int = 2000,
        bracket_tag: bool = False,
    ) -> None:
        tag = self._tag()
        if bracket_tag and tag:
            self.emit(f"\n> [{tag}] 执行工具 {tool_name}:")
        else:
            self.emit(f"\n> 执行工具 {tool_name}:")
        out_s = str(output)
        self.emit(out_s[:max_len] + ("…" if len(out_s) > max_len else ""))


# 默认实例：无角色色，供单 Agent 脚本使用
logger = AgentLogger()

# 主 / 子 Agent 常用实例（s04 等）
main_logger = AgentLogger(ROLE_MAIN)
sub_logger = AgentLogger(ROLE_SUB)
