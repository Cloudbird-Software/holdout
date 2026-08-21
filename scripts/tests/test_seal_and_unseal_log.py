#!/usr/bin/env python3
# test_seal_and_unseal_log.py —— W4-C3 自测（ADR-0068 决策 2/4，fixture 临时目录、零真实试卷）
#   seal.py：哈希公式绿 / 超大拒 / marker 拒（错误输出掩码）/ 非扁平名拒
#   unseal-log.py：追加两次→两行且首行字节不变 / 验链绿 / 改历史断链红 / 缺字段拒收
import json
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
PY = sys.executable
MINI_TEST = "def test_mini_ok():\n    assert 1 + 1 == 2\n"
FULL_MARKER = "CLOUDBIRD-HOLDOUT-CANARY-0000000000000000"


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def make_record(pr=7, run_id="run-1", verdict="pass", passed=4, total=5):
    return {"schema": "holdout-unseal-record/1", "ts": "2026-08-22T08:00:00Z",
            "repo": "Cloudbird-Software/CI-Workflows", "pr": pr, "run_id": run_id,
            "verdict": verdict, "entries": [{"id": "HO-0007", "sha8": "a1b2c3d4", "verify": True}],
            "passed": passed, "total": total, "gap_pct": 1.0, "threshold_pct": 5.0,
            "escalated": verdict == "gap-escalated"}


def run_py(*argv):
    return subprocess.run([PY, *map(str, argv)], capture_output=True, text=True, encoding="utf-8")


class TestSeal(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="holdout-seal-test-"))
        (self.root / "scripts").mkdir()
        for s in ("new_entry.py", "seal.py"):
            (self.root / "scripts" / s).write_bytes((SCRIPTS / s).read_bytes())
        self.src = self.root / "test_mini.py"
        self.src.write_text(MINI_TEST, encoding="utf-8", newline="\n")

    def seal(self, src=None, *extra):
        return run_py(self.root / "scripts" / "seal.py", "--file", src or self.src,
                      "--ac-ref", "IR-0003/W4-C3/AC-1", "--sealed-by", "fixture-owner",
                      "--root", self.root, *extra)

    def test_green_hash_formula(self):
        """绿：封存成功且 sealed_sha256 == sha256(canonical payload)（ADR-0056 公式）。"""
        p = self.seal()
        self.assertEqual(p.returncode, 0, p.stderr)
        entry = json.loads((self.root / "entries" / "HO-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(entry["payload"]["kind"], "sealed-test-set")
        self.assertEqual(entry["payload"]["files"][0]["sha256"], sha256(MINI_TEST.encode()).hexdigest())
        self.assertEqual(entry["sealed_sha256"], sha256(canon(entry["payload"]).encode()).hexdigest())
        self.assertTrue((self.root / "entries" / "index.yaml").exists())

    def test_red_oversize(self):
        self.src.write_text("# pad\n" + "x" * 70000, encoding="utf-8", newline="\n")
        p = self.seal()
        self.assertEqual(p.returncode, 1); self.assertIn("65536B", p.stderr)

    def test_red_marker_masked(self):
        self.src.write_text(f"X = '{FULL_MARKER}'\n", encoding="utf-8", newline="\n")
        p = self.seal()
        self.assertEqual(p.returncode, 1); self.assertIn("canary marker", p.stderr)
        # 错误输出绝不回显完整 marker（本测试输出会进 CI 日志=sweep 扫描面）
        self.assertNotIn(FULL_MARKER, p.stderr)

    def test_red_bad_name(self):
        # 名字带空格=非扁平白名单形态（路径分隔符/../非 .py 同理全拒）；名检查先于读文件
        p = self.seal("has space.py")
        self.assertEqual(p.returncode, 1); self.assertIn("扁平", p.stderr)


class TestUnsealLog(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="holdout-ledger-test-"))
        self.ledger = self.root / "ledger" / "unseal.jsonl"
        self.log = SCRIPTS / "unseal-log.py"

    def append(self, rec, rc_expect=0):
        rf = self.root / "rec.json"
        rf.write_text(json.dumps(rec), encoding="utf-8", newline="\n")
        p = run_py(self.log, "append", "--record", rf, "--ledger", self.ledger)
        self.assertEqual(p.returncode, rc_expect, p.stderr + p.stdout)
        return p

    def verify(self):
        return run_py(self.log, "verify", "--ledger", self.ledger)

    def test_append_only_replay_two_lines(self):
        """AC-3 核心：重放揭封 → 两行记录，且第一行字节不变（append-only）。"""
        self.append(make_record(run_id="run-1"))
        first = self.ledger.read_bytes()
        self.append(make_record(run_id="run-2", verdict="gap-escalated", passed=3))
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].encode("utf-8"), first.rstrip(b"\n"))
        self.assertEqual(json.loads(lines[1])["prev_hash"], json.loads(lines[0])["record_hash"])  # 链式 prev

    def test_verify_green(self):
        self.append(make_record(run_id="r1")); self.append(make_record(run_id="r2"))
        p = self.verify()
        self.assertEqual(p.returncode, 0, p.stderr); self.assertIn("验链全绿", p.stdout)

    def test_rewrite_history_breaks_chain(self):
        self.append(make_record(run_id="r1")); self.append(make_record(run_id="r2"))
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[0]); tampered["passed"] = 999  # 改写历史=append-only 禁区
        lines[0] = canon(tampered)
        self.ledger.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        p = self.verify()
        self.assertEqual(p.returncode, 1); self.assertIn("record_hash 不符", p.stderr)

    def test_malformed_record_refused(self):
        bad = make_record(); del bad["entries"]  # 缺 sealed_sha256 校验结果字段——拒收
        rf = self.root / "bad.json"; rf.write_text(json.dumps(bad), encoding="utf-8", newline="\n")
        p = run_py(self.log, "append", "--record", rf, "--ledger", self.ledger)
        self.assertEqual(p.returncode, 2); self.assertIn("缺字段 entries", p.stderr)


if __name__ == "__main__":
    unittest.main()
