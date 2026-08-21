#!/usr/bin/env python3
# seal.py —— 测试文件 → 封存条目（W4-C3 .github#222 / ADR-0068 决策 2 前置；哈希公式=ADR-0056）
#
# 把验收测试文件封存为可揭封执行的 sealed 条目，payload 约定（holdout-unseal/1）：
#   {kind:"sealed-test-set", schema:"holdout-unseal/1", runner:"pytest",
#    files:[{name, sha256, content_b64}]}
# 条目落盘一律经 scripts/new_entry.py（"禁止手写条目"纪律不变——本脚本只组装 payload，
# canonical sealed_sha256 的计算仍归 new_entry.py，单一事实源）。payload 一经封存不可变
# （sealed_sha256 锚定）；揭封侧（CI-Workflows pipeline/holdout-unseal/）先验哈希再执行。
#
# 防线（fail-closed）：>64KB 拒（条目是场景级小测试集，非套件倾倒口）；文件名非扁平
# （分隔符/..）拒——解封侧按名落盘防路径逃逸；非 UTF-8 文本拒（二进制走 golden）；
# marker 前缀拒（validate_entries.py 第 7 条同款）。--sealed-by 须 owner 或授权人类。
# 退出码：0=封存成功 | 1=违规拒绝 | 2=环境错误（new_entry.py 缺失/调用失败）
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER_PREFIX = "CLOUDBIRD-HOLDOUT-CANARY-"
MAX_BYTES = 65536
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+\.py$")


def main() -> int:
    ap = argparse.ArgumentParser(description="测试文件 → sealed 条目（经 new_entry.py）")
    ap.add_argument("--file", action="append", required=True, help="测试文件路径（可多次，扁平 *.py 名）")
    ref = ap.add_mutually_exclusive_group(required=True)
    ref.add_argument("--ir-ref", help="来源意图 issue 号（如 #161）")
    ref.add_argument("--ac-ref", help="来源验收判据（如 IR-0003/W4-C3/AC-1）")
    ap.add_argument("--sealed-by", required=True, help="封存人（owner 或 owner 授权的人类）")
    ap.add_argument("--type", default="e2e-scenario", choices=["e2e-scenario", "golden"])
    ap.add_argument("--root", default=str(HERE.parent), help="holdout 仓库根目录")
    args = ap.parse_args()
    root = Path(args.root)
    new_entry = root / "scripts" / "new_entry.py"
    if not new_entry.is_file():
        print(f"FAIL  {new_entry} 不存在——封存必须经 new_entry.py（条目禁止手写）", file=sys.stderr)
        return 2

    files, seen = [], set()
    for fspec in args.file:
        p = Path(fspec)
        name = p.name
        # 解封侧按 name 落盘——落盘名只取 basename 且必须过扁平白名单（分隔符/../
        # 非后缀形态全拒=路径逃逸无入口）；重复名拒（防解封互相覆盖）
        if not NAME_RE.match(name):
            print(f"FAIL  文件名须为扁平 *.py（防解封路径逃逸）: {name!r}", file=sys.stderr); return 1
        if name in seen:
            print(f"FAIL  重复文件名 {name!r}——解封按名落盘会互相覆盖", file=sys.stderr); return 1
        seen.add(name)
        try:
            raw = p.read_bytes()
        except OSError as exc:
            print(f"FAIL  读取失败（fail-closed）: {fspec}: {exc}", file=sys.stderr); return 1
        if len(raw) > MAX_BYTES:
            print(f"FAIL  {name} {len(raw)}B > {MAX_BYTES}B——拒绝测试套件倾倒", file=sys.stderr); return 1
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print(f"FAIL  {name} 非 UTF-8 文本（pytest runner 只吃文本；二进制走 golden 条目）", file=sys.stderr); return 1
        if MARKER_PREFIX in text or MARKER_PREFIX in name:
            print(f"FAIL  {name} 含 canary marker 前缀——非 canary 条目禁止混入诱饵串", file=sys.stderr); return 1
        files.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(),
                      "content_b64": base64.b64encode(raw).decode("ascii")})

    payload = {"kind": "sealed-test-set", "schema": "holdout-unseal/1", "runner": "pytest", "files": files}
    # payload 含试卷内容——临时文件只落系统临时目录，绝不进仓库工作区/日志
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8", newline="\n") as tf:
        json.dump(payload, tf, ensure_ascii=False)
        payload_file = tf.name
    cmd = [sys.executable, str(new_entry), "--type", args.type, "--payload-file", payload_file,
           "--sealed-by", args.sealed_by, "--root", str(root)]
    cmd += ["--ir-ref", args.ir_ref] if args.ir_ref else ["--ac-ref", args.ac_ref]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    finally:
        Path(payload_file).unlink(missing_ok=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"FAIL  new_entry.py 退出 {proc.returncode}（封存未落盘）", file=sys.stderr); return 2
    print(f"OK    sealed-test-set 封存完成（{len(files)} 个测试文件，runner=pytest）——"
          f"解封侧先验 sealed_sha256 再执行（ADR-0068 决策 2）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
