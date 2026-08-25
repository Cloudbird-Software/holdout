# AGENTS.md（索引型——试卷层封存纪律，只放不可推断的约束）

## 命令

- 条目校验：`python3 scripts/validate_entries.py`（sealed_sha256 全量核验，不匹配必红；CI 同款 `.github/workflows/validate.yml`）
- 新增/补给条目：`python3 scripts/new_entry.py`（自动算哈希、防 id 冲突——禁止手写条目文件）
- 封存测试文件 / 揭封台账：`scripts/seal.py` / `scripts/unseal-log.py`（台账 `ledger/unseal.jsonl` append-only + hash 链，改历史必断链）

## 硬规则（违反 = 封存失效 / PR 打回）

1. 隔离不变量（DECISION-02）：本仓 owner 直管；cloudbrid-agent App 严禁挂载（drift-check §18 每小时断言）；验证者 App 仅限测试/验证路径写权
2. 条目一经封存不可变动：payload 动了 `sealed_sha256` 必红；勘误走新条目，不改原件
3. spec/卡/PR 只能引用 `id@sha8`（如 `HO-0001@a1b2c3d4`），禁止引用 payload 内容（= 提前泄题，宪法 §4B/§4E）
4. `canary/registry.yaml` 的诱饵 marker 公开是设计决策——勿当泄漏处理、勿"清理"
5. 变更一律走 PR（owner 直管）；提交信息用 Conventional Commits

## 索引（用到再读，不要全读）

| 场景 | 读这个 |
| --- | --- |
| 本仓角色 / 封存与隔离纪律 / 揭封 gate | [README.md](README.md)（宪法 §1 试卷层 / ADR-0056 / ADR-0080） |
| 条目与索引 schema | [schema/](schema/)（entry / index） |
| 封存条目（只读，引用仅 `id@sha8`） | [entries/](entries/) |
| 泄漏诱饵登记 | [canary/](canary/) |
| 脚本自测 | `scripts/tests/` |
