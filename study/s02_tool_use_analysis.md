# s02_tool_use.py 源码分析

## 概述

`s02_tool_use.py` 在 `s01_agent_loop.py` 的基础上引入了**工具调度机制**和**消息规范化**。核心洞见：

> "The loop didn't change at all. I just added tools."

---

## 与 s01 对比：新增内容

### 1. 工具扩展

| 工具 | s01 | s02 |
|------|-----|-----|
| `bash` | ✅ | ✅ |
| `read_file` | ❌ | ✅ |
| `write_file` | ❌ | ✅ |
| `edit_file` | ❌ | ✅ |

### 2. 调度中心：TOOL_HANDLERS

s01 在 `execute_tool_calls()` 中硬编码执行 bash，s02 引入**调度映射**：

```python
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}
```

通过 `block.name` 动态分发，无需修改循环逻辑即可扩展工具。

### 3. 路径安全：safe_path()

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
```

防止路径穿越攻击（path traversal）。所有文件操作工具都用它包装：

```python
def run_read(path: str, limit: int = None) -> str:
    text = safe_path(path).read_text()  # ← 安全化
    ...

def run_write(path: str, content: str) -> str:
    fp = safe_path(path)  # ← 安全化
    ...
```

### 4. 并发安全分类

```python
CONCURRENCY_SAFE = {"read_file"}      # 可并行
CONCURRENCY_UNSAFE = {"write_file", "edit_file"}  # 需串行
```

为后续并发优化埋下的**设计注释**。

### 5. 消息规范化：normalize_messages()

s02 新增的核心函数，对消息列表做三件事：

**a. 清理元数据**
```python
clean["content"] = [
    {k: v for k, v in block.items()
     if not k.startswith("_")}  # 丢弃 _ 开头的内部字段
    for block in msg["content"]
]
```

**b. 孤儿 tool_use 检测**
```python
# 找到没有对应 tool_result 的 tool_use，插入占位符
if block.get("type") == "tool_use" and block.get("id") not in existing_results:
    cleaned.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": block["id"], "content": "(cancelled)"}
    ]})
```

**c. 合并相邻同 role 消息**
```python
if msg["role"] == merged[-1]["role"]:
    prev["content"] = prev_c + curr_c  # 合并
else:
    merged.append(msg)
```

> API 要求 `user/assistant` 严格交替，合并防止格式错误。

### 6. LoopState 简化

| 字段 | s01 | s02 |
|------|-----|-----|
| `messages` | ✅ | ✅ |
| `turn_count` | ✅ | ❌ 移除 |
| `transition_reason` | ✅ | ❌ 移除 |

s02 简化了状态追踪，移除了显式的轮次和转移原因。

### 7. agent_loop() 重构

| | s01 | s02 |
|--|-----|-----|
| 结构 | `run_one_turn()` + `agent_loop()` 分离 | 单一 `agent_loop()` 函数 |
| 状态管理 | `LoopState` dataclass | 直接传 `messages: list` |
| 返回值 | `run_one_turn()` 返回 bool | 直接在循环内检查 `stop_reason` |

```python
# s01
def agent_loop(state: LoopState) -> None:
    while run_one_turn(state):
        pass

# s02
def agent_loop(messages: list):
    while True:
        response = client.messages.create(...)
        if response.stop_reason != "tool_use":
            return
        # 执行工具...
```

### 8. 调试输出

s02 在关键节点添加了 print 语句：

```python
def agent_loop(messages: list):
    while True:
        print(">>>>>>>>messages")    # ← 新增
        print(messages[-1])
        response = client.messages.create(...)
        print("<<<<<<<<response")     # ← 新增
        for block in response.content:
            print(block)
        ...
```

---

## 工具函数对照

| 函数 | 职责 |
|------|------|
| `run_bash()` | 执行 shell 命令（保留自 s01） |
| `run_read()` | 读取文件（支持行数限制） |
| `run_write()` | 写入文件（自动创建目录） |
| `run_edit()` | 精确替换文件中的一段文本 |

---

## 总结：s02 的增量

```
s01                              s02
─────────────────────────────────────────────────
单一 bash 工具                   工具调度中心 (TOOL_HANDLERS)
硬编码 bash 执行                 函数式 handler 映射
无路径安全                      safe_path() 防护
无消息规范化                    normalize_messages() 三合一
LoopState dataclass              直接传 list
run_one_turn 分离设计           单一 agent_loop()
无并发分类                      CONCURRENCY_SAFE/UNSAFE
```

**核心设计原则**：循环逻辑不变，通过扩展 `TOOL_HANDLERS` 和 `TOOLS` 列表来增加新工具。
