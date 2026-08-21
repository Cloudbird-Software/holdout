# holdout —— 试卷层（封存验收场景 + golden 集 + 泄漏诱饵）

> 宪法 §1 试卷层实体 · IR-0003（.github#161）W1-C4（.github#167）· ADR-0056 · owner 直管

本仓是 Cloudbird-Software 组织的**考卷**：封存的验收场景（e2e-scenario）、golden 集
（golden）、agent 任务轨迹样本（agent-trajectory，宪法 §13 推论一第四观测类）与
泄漏诱饵（canary）。产品仓的测试套件永远不含这些内容——它们只用于揭封验收与
判定物有效性演习（宪法 §4B/§4E），防止实现与验证对考卷过拟合。

## 封存/引用约定（本仓的核心纪律）

- 每个条目 `entries/HO-NNNN.json` 带 `sealed_sha256` =
  `sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))`——payload
  内容一经封存即不可变动（动了哈希必红，`scripts/validate_entries.py` 强制）。
- **spec/卡/PR 只能引用 `id` + `sealed_sha256` 前 8 位**（如 `HO-0001@a1b2c3d4`），
  **禁止引用 payload 内容**——引用内容 = 提前泄题 + 破坏封存的可验证性。
- 揭封（unseal）gate 属 W4-C3（.github#222 / ADR-0068）：揭封侧（CI-Workflows
  `pipeline/holdout-unseal/`）先验 `sealed_sha256` 再解封执行（不匹配=fail-closed
  拒揭），PR check 只显示计数；逐条明细写回本仓 issue。本仓配套两件：
  `scripts/seal.py`——测试文件封存为 `payload.kind=sealed-test-set` 条目
  （文件名+sha256+base64；仍经 `new_entry.py` 落盘）；`scripts/unseal-log.py`
  ——揭封台账 `ledger/unseal.jsonl`（append-only JSONL + hash 链，公式同
  CI-Workflows pipeline/metering）：每次揭封追加一行（PR 号、sealed_sha256 校验
  结果、通过计数、时戳、run_id），改历史必断链，`verify` 随时巡检（决策 4）。
- 新增/补给条目必须经 `scripts/new_entry.py` 生成（自动算哈希、防 id 冲突），
  禁止手写条目文件。

## 隔离不变量（DECISION-02，宪法 §1 试卷层）

- 本仓 **public**（IR-0001 DECISION-02：agent 读公开仓是不确定风险，私有化的
  运维是确定支出）。
- **cloudbrid-agent App 严禁挂载到本仓**——`new-repo-init.sh` 的 App 挂载步骤对
  本仓禁止执行；`.github` 仓 drift-check **§18** 每小时断言：App installation
  仓清单不得包含 holdout（在 = P0 隔离失效）。正向对照：清单必须非空且含
  `.github`，否则按检测器失明 fail-closed 报漂移。
- owner 直管：admin 唯一且为 owner（ADR-0010），补给职责见下。

## 泄漏诱饵（canary）与 markers 公开的设计理由

`canary/registry.yaml` 登记全部诱饵 marker（形如
`CLOUDBIRD-HOLDOUT-CANARY-<16hex>`，`openssl rand -hex 8` 生成）。`.github` 仓
`holdout-canary-sweep`（每周 cron）扫描全部 active 仓 workflow 日志：**marker
出现在任何日志 = holdout 内容被违规读进上下文/输出 = P0 报警**（宪法 §6）。

markers 为什么公开：本仓本就 public，无密可保——隔离不靠保密，靠"违规读取
可检测"。marker 的告警语义是"出现在 agent 上下文/workflow 日志"，而非
"marker 字符串本身保密"。

registry 含且必含 ≥1 条 `drill: true` 演习 marker（正控必须在场，fail-closed）：
`holdout-canary-drill`（dispatch）把 drill marker 写进 run 日志模拟泄漏 →
sweep dispatch(`treat_drill_as_leak=true`) 应开出 P0 issue → 手动关闭留评论
"演习"——证明报警通道端到端真的会触发（W1-C4 AC-3）。sweep 窗口内 drill
正控未被检出 = 检测通道可能坏了，报 P1（检测器失明不得伪装成无泄漏）。

## owner 月度补给职责（宪法 §2/§7，结构上不可交给 agent）

每月 30 分钟：新增条目（e2e/golden/trajectory 各至少 1 条，`scripts/new_entry.py`）、
轮换一条 canary marker、执行一次泄漏演习。agent 补给 holdout = 运动员写考卷，
禁止。

## 目录结构

```
schema/entry.schema.json     # 条目 schema（IFACE-07）：id/ir_ref|ac_ref 二选一/type/
                             #   payload/sealed_sha256/created_at/sealed_by
schema/index.schema.json     # entries/index.yaml 自身 schema
entries/HO-NNNN.json         # 封存条目（纯 JSON）
entries/index.yaml           # 索引：{version, entries: [{id, file, sha256}]}
                             #   sha256 = 整条目 canonical JSON 哈希（防文件级篡改）
canary/registry.yaml         # {version, markers: [{id, marker, drill}]}
scripts/validate_entries.py  # 校验：schema/哈希/id 唯一递增/index/canary 双向一致
scripts/new_entry.py         # 参数化生成新条目（算哈希、防冲突、更新 index/registry）
scripts/seal.py / unseal-log.py  # 封存测试文件 / append-only 揭封台账（W4-C3，ADR-0068）
scripts/tests/ + ledger/unseal.jsonl  # 脚本自测 / 台账落账（verdict 揭封时追加+回传）
.github/workflows/validate.yml  # PR+push+weekly cron 跑校验与脚本自测
```

## 验证

```bash
pip install jsonschema pyyaml
python scripts/validate_entries.py
```

退出码 0=全绿；任何 IO/解析失败按 fail-closed 处理，退出码非 0。
