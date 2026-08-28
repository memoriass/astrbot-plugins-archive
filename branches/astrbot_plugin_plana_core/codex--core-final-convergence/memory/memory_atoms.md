# Memory Atoms

`memory/atoms.py` 和 `memory/atom_policy.py` 提供 Plana-native 细粒度记忆切片。Atom 用于增强召回粒度和生命周期管理，不是第二套记忆运行时。

## 职责

- 从 episodic memory 派生短文本切片。
- 维护 active、expired、forgotten 生命周期。
- 提供 TTL、decay、reinforce 和时间权重策略。
- 使用独立 FTS index 提升短文本召回。

## 边界

- Atom 的父证据仍是原始 memory；删除父 memory 后 atom 也应被清理。
- Atom 不能直接触发画像、关系或 workflow 写入。
- LLM 可作为未来 advisory atom producer，但持久化策略仍由 `atom_policy.py` 控制。

## 维护规则

- 新 atom kind 或 decay 策略必须同步 `atom_policy.py`、maintenance 检查和 Web 展示。
- atom 状态迁移应保持可重建，不保存无法追溯的长期事实。
