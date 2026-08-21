#!/usr/bin/env python3
# new_entry.py —— 生成新 holdout 条目（W1-C4 / ADR-0056）
#
# 条目禁止手写：一律经本脚本生成（算 canonical sealed_sha256、分配下一个 id 防冲突、
# 同步更新 entries/index.yaml；canary 类型另更新 canary/registry.yaml）。
# marker 由调用方用 openssl rand -hex 8 生成后经 --marker 传入（形如
# CLOUDBIRD-HOLDOUT-CANARY-a1b2c3d4e5f60718——16 个 hex 字符）。
#
# 注意：输出必须掩码 marker（本仓 validate/本脚本日志会被 canary sweep 扫描）。
#
# 用法示例:
#   python scripts/new_entry.py --type e2e-scenario --ir-ref "#161" \
#     --sealed-by randypanding --payload-file payload.json
#   python scripts/new_entry.py --type canary --ac-ref "IR-0003/W1-C4/AC-3" \
#     --sealed-by randypanding --payload-file bait.json \
#     --marker "$(openssl rand -hex 8 | sed 's/^/CLOUDBIRD-HOLDOUT-CANARY-/')" --drill
# 生成后必须跑 python scripts/validate_entries.py 验证再提交。

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

MARKER_RE = re.compile(r"^CLOUDBIRD-HOLDOUT-CANARY-[0-9a-f]{16}$")
MARKER_PREFIX = "CLOUDBIRD-HOLDOUT-CANARY-"
ID_RE = re.compile(r"^HO-(\d{4})$")
TYPES = ["e2e-scenario", "golden", "agent-trajectory", "canary"]


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()


def mask(marker: str) -> str:
    return f"{MARKER_PREFIX}…{marker[-4:]}" if len(marker) > 4 else "…"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成新 holdout 条目（禁止手写条目文件）")
    ap.add_argument("--type", required=True, choices=TYPES)
    ref = ap.add_mutually_exclusive_group(required=True)
    ref.add_argument("--ir-ref", help="来源意图 issue 号（如 #161）")
    ref.add_argument("--ac-ref", help="来源验收判据（如 IR-0003/W1-C4/AC-2）")
    ap.add_argument("--payload-file", required=True, help="payload JSON 文件（须为 JSON 对象；canary 类型不得含 marker 字段）")
    ap.add_argument("--sealed-by", required=True, help="封存人（owner 或 owner 授权的人类）")
    ap.add_argument("--created-at", default=None, help="封存时刻 RFC 3339（缺省=now UTC）")
    ap.add_argument("--marker", default=None, help=f"canary marker（{MARKER_PREFIX}<16hex>，openssl rand -hex 8 生成）")
    ap.add_argument("--drill", action="store_true", help="标记为演习正控 marker（sweep 命中不报警的通道）")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()
    root = Path(args.root)

    if args.type == "canary":
        if not args.marker or not MARKER_RE.match(args.marker):
            print(f"FAIL  --marker 缺失或形状非法（须 {MARKER_PREFIX}<16hex>，openssl rand -hex 8）", file=sys.stderr)
            return 1
    elif args.marker or args.drill:
        print("FAIL  --marker/--drill 仅用于 --type canary", file=sys.stderr)
        return 1

    try:
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL  payload 文件读取/解析失败: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("FAIL  payload 必须是 JSON 对象", file=sys.stderr)
        return 1
    if args.type == "canary":
        if "marker" in payload:
            print("FAIL  canary payload 文件不得自带 marker 字段（由本脚本注入 --marker）", file=sys.stderr)
            return 1
        payload = dict(payload)
        payload["marker"] = args.marker

    # ---------- id 分配（max+1，防冲突：目标文件已存在即拒绝）----------
    entries_dir = root / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(entries_dir.glob("HO-????.json"))
    nums = [int(ID_RE.match(f.stem).group(1)) for f in existing if ID_RE.match(f.stem)]
    next_num = (max(nums) + 1) if nums else 1
    eid = f"HO-{next_num:04d}"
    entry_path = entries_dir / f"{eid}.json"
    if entry_path.exists():
        print(f"FAIL  {entry_path} 已存在——id 冲突，拒绝覆盖（防误删已封存条目）", file=sys.stderr)
        return 1
    created_at = args.created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        print(f"FAIL  --created-at 非 RFC 3339: {created_at!r}", file=sys.stderr)
        return 1

    entry = {
        "id": eid,
        "type": args.type,
        "payload": payload,
        "sealed_sha256": sha256_hex(payload),
        "created_at": created_at,
        "sealed_by": args.sealed_by,
    }
    if args.ir_ref:
        entry["ir_ref"] = args.ir_ref
    else:
        entry["ac_ref"] = args.ac_ref

    # ---------- 落盘条目 + 更新 index ----------
    entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    index_path = entries_dir / "index.yaml"
    if index_path.exists():
        index = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {"version": 1, "entries": []}
    else:
        index = {"version": 1, "entries": []}
    index["entries"].append({"id": eid, "file": f"{eid}.json", "sha256": sha256_hex(entry)})
    index_path.write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")

    # ---------- canary: 更新 registry ----------
    if args.type == "canary":
        reg_path = root / "canary" / "registry.yaml"
        reg_dir = reg_path.parent
        reg_dir.mkdir(parents=True, exist_ok=True)
        if reg_path.exists():
            reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {"version": 1, "markers": []}
        else:
            reg = {"version": 1, "markers": []}
        reg.setdefault("markers", []).append({"id": eid, "marker": args.marker, "drill": bool(args.drill)})
        reg_path.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")

    m = f" marker={mask(args.marker)} drill={args.drill}" if args.type == "canary" else ""
    print(f"OK    {entry_path.name} 已生成（type={args.type} sealed_sha256={entry['sealed_sha256'][:8]}…{m}）")
    print("下一步: python scripts/validate_entries.py && 提交（引用只允许 " + eid + "@" + entry["sealed_sha256"][:8] + "，禁止引用 payload 内容）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
