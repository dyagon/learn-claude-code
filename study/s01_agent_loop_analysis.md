# s01_agent_loop.py 源码分析

## 概述

`s01_agent_loop.py` 是 Claude Code 教学项目中**最小的 Agent 循环实现**。它演示了 Agent 的核心模式：

```
用户消息 → 模型回复 → 执行工具 → 回写结果 → 继续循环
```

整个实现约 170 行，刻意保持精简，但将循环状态显式化，为后续章节的扩展奠定结构基础。

---

## 核心数据结构

### LoopState

```python
@dataclass
class LoopState:
    messages: list          # 对话历史
    turn_count: int = 1     # 循环轮次计数
    transition_reason: str | None = None  # 状态转移原因
```

**设计意图**：`transition_reason` 字段用于追踪循环为何继续——是 `tool_result` 还是其他原因。后续章节可以基于此字段扩展状态机。

---

## 核心流程

### 1. 入口：`agent_loop()`

```python
def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass
```

标准的 while 循环，条件为 `run_one_turn()` 返回 `True` 时继续。简洁明了。

### 2. 单轮执行：`run_one_turn()`

```python
def run_one_turn(state: LoopState) -> bool:
    response = client.messages.create(...)
    state.messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        state.transition_reason = None
        return False  # 结束本轮

    results = execute_tool_calls(response.content)
    if not results:
        state.transition_reason = None
        return False  # 无工具调用，结束

    state.messages.append({"role": "user", "content": results})
    state.turn_count += 1
    state.transition_reason = "tool_result"
    return True  # 继续循环
```

**流程图**：

```
创建消息 → 添加到历史
    ↓
stop_reason == "tool_use"？
    ↓ 是                    ↓ 否
执行工具调用              返回 False（结束）
    ↓
有结果？                  无结果
    ↓ 是                    ↓ 否
追加到 messages         返回 False（结束）
turn_count++
返回 True（继续）
```

### 3. 工具执行：`execute_tool_calls()`

```python
def execute_tool_calls(response_content) -> list[dict]:
    results = []
    for block in response_content:
        if block.type != "tool_use":
            continue
        command = block.input["command"]
        output = run_bash(command)
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })
    return results
```

遍历模型返回的 `tool_use` 块，逐一执行 `bash` 命令，将结果收集后返回。

### 4. Bash 执行：`run_bash()`

```python
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    # ... subprocess.run
```

**安全检查**：基础的危险命令过滤。注意这只是简单字符串匹配，不构成完整的安全防护。

---

## 消息流

```
用户输入 (role: user)
    ↓
client.messages.create()  →  模型回复
    ↓
stop_reason == "tool_use"
    ↓ 是                      ↓ 否
execute_tool_calls()      →  循环结束
    ↓
tool_result (role: user)  →  添加到 messages
    ↓
回到 client.messages.create()
```

**关键点**：`tool_result` 以 `role: "user"` 的身份追加回消息历史，这样模型在下一轮能看到完整的上下文。

---

## 交互入口

```python
if __name__ == "__main__":
    history = []
    while True:
        query = input("\033[36ms01 >> \033[0m")
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
```

- 循环等待用户输入
- 输入 `q`/`exit`/空行退出
- 每次交互创建一个独立的 `LoopState`

---

## 工具定义

```python
TOOLS = [{
    "name": "bash",
    "description": "Run a shell command in the current workspace.",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}]
```

目前只有一个 `bash` 工具。工具列表设计为数组，便于后续扩展更多工具。

---

## 安全性设计

| 措施 | 实现 |
|------|------|
| 危险命令过滤 | `run_bash()` 中的硬编码黑名单 |
| 超时限制 | `subprocess.run(timeout=120)` |
| 输出截断 | 限制在 50000 字符 |
| Base URL 配置 | 支持通过环境变量配置 `ANTHROPIC_BASE_URL` |

---

## 与前端可视化对比

前端 `s01-agent-loop.tsx` 展示的是**教学视角的循环状态机**，而 `s01_agent_loop.py` 是**实际可运行的最小实现**。

| 维度 | 前端 (s01-agent-loop.tsx) | 后端 (s01_agent_loop.py) |
|------|--------------------------|-------------------------|
| 目的 | 教学演示 | 实际执行 |
| 状态 | 预定义分步动画 | 运行时动态 |
| 工具 | 仅 SVG 渲染 | bash 实际执行 |
| 循环条件 | `stop_reason === "tool_use"` | 同左 |

---

## 总结

`s01_agent_loop.py` 演示了最小 Agent 循环的**核心要素**：

1. **显式状态** - `LoopState` 将消息历史、轮次、转移原因集中管理
2. **循环条件** - 基于 `stop_reason` 判断是否继续
3. **结果回写** - 工具结果以 `role: "user"` 追加到消息历史
4. **可扩展性** - 结构清晰，便于后续章节增加更多工具和状态

这是一个**教学导向的最小实现**，而非生产级 Agent 框架。
