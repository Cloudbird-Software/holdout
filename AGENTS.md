# AGENTS.md（索引型——试卷层封存纪律，只放不可推断的约束）

<!-- entry-protocol v2 -->

### 入口协议（陌生 agent 从这里开始——宪法 §11 / ADR-0055/0095）

0. **按意图定角色**（指引=.github 仓 `docs/agent/ROLE-*.md`，ADR-0095）：开新意图→ROLE-IR · 把已签署 IR 写成 spec→ROLE-SPEC · 实现卡片→ROLE-IMPLEMENT · 验收/人类让你处理 issues→ROLE-ACCEPT
1. 取 ghcb（钉 SHA，禁浮动 main）：`curl -fsS -o ghcb https://raw.githubusercontent.com/Cloudbird-Software/.github/f72d9520706c8fca974d92456f65cae5c1412bb7/scripts/ghcb && chmod +x ghcb`（凭据用你自己的：`gh auth login` 或 `export GH_TOKEN=<PAT>`；`-f` 必带——404 时 curl 无 -f 仍退出 0，会把错误页当脚本落盘）
2. 找活：`bash ghcb next [owner/repo]` → 列 state:ready 卡（卡 issue 是唯一工作凭证，无卡不开工）
3. 认领：`bash ghcb claim <n> [owner/repo]` → 评论 /claim——conductor 转介 arbiter 原子 CAS 租约，先到先得；败者换下一张（`bash ghcb status <n>` 看持有者）
4. 开工：`make card-test CARD=<n>`（读卡 AC、测试先行）→ `make gates-pr`（本地复现 CI 关卡）
5. 提 PR：body 必带一行卡元数据 `Card: <owner>/<repo>#<n>`（`bash ghcb card-meta <n>` 生成；缺失=后续关卡 exit 3）
6. front-desk 命令（卡 issue 评论，conductor 转介 arbiter 处理）：/claim 认领 · /release 释放租约 · /retry 隔离回流

<!-- /entry-protocol -->

## 角色路由（按你的意图选路——ADR-0095；指引文件在 .github 治理仓 docs/agent/）

- 开 IR：feature 意图=本仓 issue（issue 即 IR，无需 PR）；治理意图=.github 仓 → [ROLE-IR.md](https://github.com/Cloudbird-Software/.github/blob/main/docs/agent/ROLE-IR.md)
- IR→spec：spec PR 必带测试设计逐类讨论（差分/属性/模糊…）+ holdout；**spec agent 不得直接实现** → [ROLE-SPEC.md](https://github.com/Cloudbird-Software/.github/blob/main/docs/agent/ROLE-SPEC.md)
- 实现卡片（PM 职责）：弱模型优先（子 agent / CNB 池）· fan-out=工具非流程 · 边做边推 PR · 3 次熔断自己接手 → [ROLE-IMPLEMENT.md](https://github.com/Cloudbird-Software/.github/blob/main/docs/agent/ROLE-IMPLEMENT.md)
- 验收 / 人类让你处理 issues：卡/IR 完成度检查 · bug 复现三值判定 → [ROLE-ACCEPT.md](https://github.com/Cloudbird-Software/.github/blob/main/docs/agent/ROLE-ACCEPT.md)

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
