# Agent 主循环流程图实现原理

## 概述

"Agent 主循环"（Agent Loop）是 Claude Code 教学网站中的一个交互式流程图演示页面。它使用 **自定义 SVG + Framer Motion** 手绘实现，而非任何第三方图表库。

## 核心文件

| 文件 | 职责 |
|------|------|
| `web/src/components/visualizations/s01-agent-loop.tsx` | 主流程图组件 |
| `web/src/hooks/useSteppedVisualization.ts` | 分步动画状态管理 |
| `web/src/hooks/useDarkMode.ts` | 暗色模式颜色主题 |
| `web/src/components/visualizations/shared/step-controls.tsx` | 播放控制栏 |

## 技术架构

### 1. 数据模型

流程图由节点（FlowNode）和边（FlowEdge）构成：

```typescript
interface FlowNode {
  id: string;
  label: string;
  x: number;      // 中心 x 坐标
  y: number;      // 中心 y 坐标
  w: number;      // 宽度
  h: number;      // 高度
  type: "rect" | "diamond";  // 矩形或菱形（决策节点）
}

interface FlowEdge {
  from: string;
  to: string;
  label?: string;  // 可选边标签（如 "tool_use", "end_turn"）
}
```

### 2. 分步演示机制

关键设计：**预定义每一步的活跃节点和边**

```typescript
const ACTIVE_NODES_PER_STEP: string[][] = [
  [],                    // Step 0: 初始状态
  ["start"],             // Step 1: 开始节点激活
  ["api_call"],          // Step 2: API 调用激活
  ["check", "execute"],  // Step 3: 决策+执行激活
  ["execute", "append"], // Step 4: 执行+追加激活
  ["api_call", "check", "execute", "append"],  // Step 5: 全流程
  ["check", "end"],      // Step 6: 结束
];

const ACTIVE_EDGES_PER_STEP: string[][] = [
  [],
  [],
  ["start->api_call"],
  ["api_call->check", "check->execute"],
  // ...
];
```

这种设计将**动画状态与业务逻辑分离**——数据驱动而非命令式驱动。

### 3. SVG 路径计算

边路径通过 `edgePath()` 函数动态计算：

```typescript
function edgePath(nodes: FlowNode[], fromId: string, toId: string): string {
  // 特殊处理：循环回路（左上→左下→回上）
  if (fromId === "append" && toId === "api_call") {
    return `M ${startX} ${startY} L ${startX - 50} ${startY} L ${endX - 50} ${endY} L ${endX} ${endY}`;
  }
  // 水平决策分支
  if (fromId === "check" && toId === "end") {
    return `M ${startX} ${startY} L ${endX} ${endY}`;
  }
  // 默认垂直连接
  return `M ${startX} ${startY} L ${endX} ${endY}`;
}
```

### 4. 动画实现

使用 **Framer Motion** 的 `motion` 组件实现流畅动画：

```typescript
<motion.rect
  animate={{
    fill: isActive ? palette.activeNodeFill : palette.nodeFill,
    stroke: isActive ? palette.activeNodeStroke : palette.nodeStroke,
  }}
  transition={{ duration: 0.4 }}
/>

<motion.path
  animate={{
    stroke: isActive ? palette.activeEdgeStroke : palette.edgeStroke,
    strokeWidth: isActive ? 2.5 : 1.5,
  }}
  transition={{ duration: 0.4 }}
/>
```

### 5. 暗色模式适配

通过 `useSvgPalette()` hook 动态返回颜色配置：

```typescript
function useSvgPalette(): SvgPalette {
  const isDark = useDarkMode();
  // 根据 isDark 返回不同调色板
}
```

| 元素 | 亮色模式 | 暗色模式（激活态） |
|------|---------|------------------|
| 节点填充 | `#e2e8f0` | `#3b82f6` (蓝色) |
| 节点描边 | `#cbd5e1` | `#2563eb` |
| 边 | `#cbd5e1` | `#52525b` |
| 激活边 | `#3b82f6` | `#3b82f6` |

### 6. 循环箭头特殊处理

Agent 主循环的核心是 `while (stop_reason === "tool_use")` 循环。循环回路的 SVG 路径采用折线设计：

```
    ┌──────────────────────────────┐
    │                              │
    ▼                              │
[追加结果] ──→ [API 调用]           │
    ▲                              │
    │                              │
    └──────────────────────────────┘
```

代码中 `edgePath()` 对 `append→api_call` 边使用三段折线模拟曲线效果。

## messages[] 面板同步

右侧面板实时显示 `messages[]` 数组的增长过程：

```typescript
const visibleMessages: MessageBlock[] = [];
for (let step = 0; step <= currentStep; step++) {
  for (const message of copy.messagesPerStep[step]) {
    if (message) visibleMessages.push(message);
  }
}
```

每条消息包含 `role`（user/assistant/tool_result）和 `detail`，并通过 Framer Motion 的 `AnimatePresence` 实现逐个弹入动画。

## 国际化支持

所有文本通过 `COPY` 对象管理，支持 `zh`、`en`、`ja` 三种语言：

```typescript
const COPY: Record<SupportedLocale, { title: string; nodeLabels: Record<NodeId, string>; ... }>
```

## 总结

| 维度 | 实现方式 |
|------|---------|
| 图表渲染 | 手绘 SVG（polygon/rect/path） |
| 动画 | Framer Motion（motion.* 组件） |
| 状态管理 | React hooks（useState/useEffect） |
| 分步控制 | 预定义数组（数据驱动） |
| 主题适配 | CSS 变量 + useDarkMode hook |
| 国际化 | COPY 对象映射 |
| 无依赖 | 不使用任何第三方图表库 |
