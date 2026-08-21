#!/usr/bin/env python3
# validate_entries.py —— holdout 条目封存完整性校验（W1-C4 / ADR-0056）
#
# 校验项（全部 fail-closed：任何 IO/解析失败 = 校验失败，绝不静默跳过）：
#   1. schema 合规（schema/entry.schema.json，IFACE-07：ir_ref|ac_ref 二选一等）
#   2. created_at 可解析为 RFC 3339
#   3. sealed_sha256 == sha256(canonical JSON of payload)
#   4. id 唯一、文件名 == id、数字严格递增且连续（append-only：出现空洞=有条目被删）
#   5. entries/index.yaml 过 index schema + 与条目文件双向一致
#      （sha256 = 整条目 canonical JSON 哈希，防文件级篡改）
#   6. canary/registry.yaml ↔ canary 条目双向一致 + marker 形状 + ≥1 条 drill 正控
#   7. 非 canary 条目 payload 不得含 canary marker 前缀串（防语义混淆）
#
# 注意：本脚本输出会进 workflow 日志，而 holdout-canary-sweep 会扫全部日志——
# 因此任何输出必须掩码 marker（只显示末 4 位），绝不打印完整 marker。
#
# 用法: python scripts/validate_entries.py [--root <仓库根目录>]
# 退出码: 0=全绿；1=有违规；2=环境失败（缺依赖等）。

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover
    print(f"FATAL: 缺依赖 {exc}（pip install jsonschema pyyaml）", file=sys.stderr)
    sys.exit(2)

MARKER_RE = re.compile(r"^CLOUDBIRD-HOLDOUT-CANARY-[0-9a-f]{16}$")
MARKER_PREFIX = "CLOUDBIRD-HOLDOUT-CANARY-"
ID_RE = re.compile(r"^HO-(\d{4})$")


def canon(obj) -> str:
    """canonical JSON：与 ADR-0056 封存哈希公式唯一对应。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()


def mask(marker: str) -> str:
    """marker 掩码——防本脚本自身日志成为 sweep 的命中源。"""
    return f"{MARKER_PREFIX}…{marker[-4:]}" if len(marker) > 4 else "…"


def parse_rfc3339(s: str):
    """RFC 3339 解析（jsonschema 的 format 检查需额外依赖 rfc3339-validator，
    此处手工解析——fail-closed：解析不了就是违规）。"""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="holdout 仓库根目录（缺省=脚本上级）")
    args = ap.parse_args()
    root = Path(args.root)

    errors: list[str] = []

    def err(msg: str):
        errors.append(msg)
        print(f"FAIL  {msg}")

    def ok(msg: str):
        print(f"OK    {msg}")

    # ---------- 0. 载入 schema（缺文件=环境失败）----------
    schema_dir = root / "schema"
    try:
        entry_schema = json.loads((schema_dir / "entry.schema.json").read_text(encoding="utf-8"))
        index_schema = json.loads((schema_dir / "index.schema.json").read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"FATAL: schema 文件读取失败: {exc}", file=sys.stderr)
        return 2
    entry_validator = Draft202012Validator(entry_schema)
    index_validator = Draft202012Validator(index_schema)

    # ---------- 1. 逐条目校验 ----------
    entries_dir = root / "entries"
    entry_files = sorted(entries_dir.glob("HO-????.json"))
    if not entry_files:
        err("entries/ 下没有任何 HO-NNNN.json——试卷层不可为空")
    entries: dict[str, dict] = {}
    numbers: list[int] = []
    for f in entry_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            err(f"{f.name} 读取/解析失败（fail-closed）: {exc}")
            continue
        # schema 合规（含 ir_ref|ac_ref oneOf、各字段 pattern）
        verrs = sorted(entry_validator.iter_errors(data), key=str)
        for v in verrs:
            err(f"{f.name} schema 违规: {'/'.join(str(p) for p in v.absolute_path)} {v.message}")
        if verrs:
            continue
        eid = data["id"]
        if f.stem != eid:
            err(f"{f.name} 文件名与 id '{eid}' 不一致（必须 entries/<id>.json）")
        num = int(ID_RE.match(eid).group(1))
        if eid in entries:
            err(f"id {eid} 重复")
            continue
        entries[eid] = data
        numbers.append(num)
        # created_at RFC3339
        if parse_rfc3339(data["created_at"]) is None:
            err(f"{eid} created_at={data['created_at']!r} 非 RFC 3339")
        # 封存哈希（核心：payload 不可变锚定）
        want = sha256_hex(data["payload"])
        if data["sealed_sha256"] != want:
            err(f"{eid} sealed_sha256 不符：声明 {data['sealed_sha256'][:12]}… 实算 {want[:12]}…"
                "（payload 被改而哈希未重算？封存内容不可变——新内容开新条目）")
        # 非 canary 条目不得混入 marker 前缀串
        if data["type"] != "canary" and MARKER_PREFIX in canon(data["payload"]):
            err(f"{eid}（type={data['type']}）payload 含 canary marker 前缀串——语义混淆，拒绝")
    # id 唯一已保证；递增+连续（append-only）
    numbers.sort()
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        err(f"id 编号不连续: {numbers}——append-only 试卷层不允许删条目留空洞")
    if entries:
        ok(f"条目 schema/哈希/编号（{len(entries)} 条，HO-0001..HO-{numbers[-1]:04d} 连续）")

    # ---------- 2. index.yaml ----------
    index_path = entries_dir / "index.yaml"
    try:
        index_data = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"FATAL: entries/index.yaml 读取失败: {exc}", file=sys.stderr)
        return 2
    except yaml.YAMLError as exc:
        err(f"entries/index.yaml YAML 解析失败（fail-closed）: {exc}")
        index_data = None
    if index_data is not None:
        for v in sorted(index_validator.iter_errors(index_data), key=str):
            err(f"index.yaml schema 违规: {'/'.join(str(p) for p in v.absolute_path)} {v.message}")
        if index_validator.is_valid(index_data):
            idx_ids = [row["id"] for row in index_data["entries"]]
            if len(idx_ids) != len(set(idx_ids)):
                err("index.yaml 内 id 重复")
            missing = sorted(set(entries) - set(idx_ids))
            extra = sorted(set(idx_ids) - set(entries))
            if missing:
                err(f"index.yaml 缺条目: {missing}（新条目必须经 new_entry.py 登记）")
            if extra:
                err(f"index.yaml 有幽灵条目: {extra}")
            for row in index_data["entries"]:
                eid = row["id"]
                if eid not in entries:
                    continue
                if row["file"] != f"{eid}.json":
                    err(f"index.yaml {eid} file={row['file']} 应为 {eid}.json")
                want = sha256_hex(entries[eid])
                if row["sha256"] != want:
                    err(f"index.yaml {eid} 整条目哈希不符（文件被篡改而索引未更新？）")
            if not errors:
                ok(f"index.yaml 与条目双向一致（{len(idx_ids)} 条）")

    # ---------- 3. canary registry ↔ entries ----------
    reg_path = root / "canary" / "registry.yaml"
    try:
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"FATAL: canary/registry.yaml 读取失败: {exc}", file=sys.stderr)
        return 2
    except yaml.YAMLError as exc:
        err(f"canary/registry.yaml YAML 解析失败（fail-closed）: {exc}")
        reg = None
    canary_entries = {k: v for k, v in entries.items() if v.get("type") == "canary"}
    if reg is not None:
        markers = reg.get("markers") if isinstance(reg, dict) else None
        if not isinstance(markers, list) or not markers:
            err("canary/registry.yaml markers 为空——泄漏诱饵机制失去检测面（正控/诱饵必须在场）")
        else:
            reg_ids, reg_markers, drills = [], [], 0
            for m in markers:
                if not isinstance(m, dict):
                    err(f"registry marker 行非对象: {m!r}")
                    continue
                mid, marker, drill = m.get("id"), m.get("marker"), m.get("drill", False)
                reg_ids.append(mid)
                reg_markers.append(marker)
                drills += 1 if drill is True else 0
                if not ID_RE.match(str(mid or "")):
                    err(f"registry marker id 非法: {mid!r}")
                if not isinstance(marker, str) or not MARKER_RE.match(marker):
                    err(f"registry {mid} marker 形状非法: {mask(str(marker))}")
                if drill not in (True, False):
                    err(f"registry {mid} drill 必须为布尔，得到 {drill!r}")
            if len(reg_markers) != len(set(reg_markers)):
                err("registry 存在重复 marker")
            # 双向一致：每条 canary entry 的 marker 在 registry；registry 每个 id 有 entry
            for eid, data in sorted(canary_entries.items()):
                pm = data["payload"].get("marker")
                if not isinstance(pm, str) or not MARKER_RE.match(pm):
                    err(f"{eid}（canary）payload.marker 缺失或形状非法")
                    continue
                if eid not in reg_ids:
                    err(f"{eid}（canary）未登记进 canary/registry.yaml")
                else:
                    row = next(r for r in markers if r.get("id") == eid)
                    if row.get("marker") != pm:
                        err(f"{eid} marker 与 registry 不一致（entry {mask(pm)} vs registry {mask(str(row.get('marker')))}）")
            for mid in reg_ids:
                if mid not in canary_entries:
                    err(f"registry 登记 {mid} 但 entries/ 无对应 canary 条目")
            if drills < 1:
                err("registry 无任何 drill: true 演习 marker——正控必须在场（fail-closed：sweep 无法自证检测通道健康，ADR-0056 决策 5）")
            if not errors:
                drills_ids = [r["id"] for r in markers if r.get("drill") is True]
                ok(f"canary registry ↔ entries 双向一致（{len(reg_ids)} 条诱饵，drill 正控: {', '.join(drills_ids)}）")

    print("----------------------------------------")
    if errors:
        print(f"结果: {len(errors)} 项违规。修复: 条目一律经 scripts/new_entry.py 生成，勿手改已封存条目")
        return 1
    print("结果: 条目封存完整性校验全绿（schema / sealed_sha256 / index / canary registry）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
