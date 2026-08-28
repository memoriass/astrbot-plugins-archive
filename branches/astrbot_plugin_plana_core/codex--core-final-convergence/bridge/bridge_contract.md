# Bridge Contract

`bridge/` 是 Plana Core 内部的受控 Bridge 契约层。它只定义 Core 接受什么 payload、如何归一化、如何返回 result/context，不内置外部 bot SDK、sidecar client、WebSocket server 或主动发送端点。

外部端点、外部 bot 适配、sidecar 转发、主动发送和后续 MCP 映射属于 `astrbot_plugin_plana_bridge_gateway`。

## 文件职责

- `bridge_contract.py`: `BridgeContract`，负责标准 payload kind、状态描述、payload 归一化、result report 和 context sync 数据结构。
- `plugin/plugin_bridge.py`: Core handler mixin。它把标准 payload 转给 memory、task、proactive、workflow 或 context 服务，并继续通过 runtime/service 层执行。

## 受控 Payload

Core 只识别以下 kind：

- `memory_query`
- `task_delegate`
- `result_report`
- `context_sync`
- `emotional_handoff`
- `workflow_request`

未知 kind 会被规整为 `unknown`，不能映射到任意工具名或任意 workflow 名。

## 数据流

1. Bridge Gateway 处理外部认证、限流、协议转换和来源识别。
2. Gateway 调用 Core 的 `/plana_core/bridge/payload`。
3. Core 用 `BridgeContract.normalize_payload()` 规整 payload。
4. 只读请求直接走 runtime/service 查询；写入或 workflow 请求进入 Core workflow/确认/审计边界。
5. `result_report`、`context_sync` 和 `emotional_handoff` 只生成 pending feedback 候选，不直接写入长期记忆。
6. Proactive pickup 和 delivery mark 走 `/plana_core/bridge/proactive/*`，仍由 Gateway 调用。

## 维护规则

- 新 payload kind 必须同步 `BridgeContract`、README、`ARCHITECTURE.md`、Gateway 文档和验证脚本。
- Core handler 不记录完整 payload、token、cookie 或 secret。
- 网络失败是 Gateway 责任；Core 返回可诊断业务结果，不把失败伪装为空数据。
