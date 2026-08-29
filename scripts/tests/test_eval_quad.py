#!/usr/bin/env python3
# test_eval_quad.py —— W5-E1 自测（IR-0006 / AC-10a，fixture 临时目录、零真实试卷）
#   eval-quad 四元组 pin：生成绿 / quad 结构逐键拒（缺键/缺 digest 锚/坏形状）/
#   双哈希公式（sealed_sha256 与 index sha256）与 e2e-scenario 同公式
import json
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))
from new_entry import validate_eval_quad  # noqa: E402


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def quad():
    return {
        "quad": {
            "code":   {"name": "ciw-ocr-precision", "repo": "Cloudbird-Software/CI-Workflows",
                       "path": "pipeline/ocr/precision.py", "commit": "0" * 40},
            "dataset": {"name": "ciw-ocr-selftest-fixture", "sha256": "1" * 64},
            "prompt": {"name": "ocr-v1.9.9-embedded", "sha256": "2" * 64},
            "model":  {"name": "z-ai glm", "provider": "z-ai", "version": "glm-4.5-air"},
        },
        "baseline_ref": "fixture",
    }


class TestQuadStructure(unittest.TestCase):
    def test_green(self):
        self.assertIsNone(validate_eval_quad(quad()))

    def test_missing_key_rejected(self):
        for drop in ("code", "dataset", "prompt", "model"):
            bad = quad()
            del bad["quad"][drop]
            self.assertIn("四键", validate_eval_quad(bad), drop)

    def test_extra_key_rejected(self):
        bad = quad()
        bad["quad"]["extra"] = {"name": "x", "sha256": "3" * 64}
        self.assertIn("四键", validate_eval_quad(bad))

    def test_missing_digest_anchor_rejected(self):
        bad = quad()
        bad["quad"]["dataset"] = {"name": "no-pin"}  # 无 sha256/commit
        self.assertIn("digest 锚", validate_eval_quad(bad))

    def test_bad_digest_shape_rejected(self):
        bad = quad()
        bad["quad"]["prompt"] = {"name": "short", "sha256": "abcd"}  # 非 64hex
        self.assertIn("digest 锚", validate_eval_quad(bad))

    def test_non_object_rejected(self):
        self.assertIn("四键", validate_eval_quad({"quad": "not-a-dict"}))
        self.assertIn("四键", validate_eval_quad({}))


class TestNewEntryCli(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="holdout-quad-test-"))
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "new_entry.py").write_bytes((SCRIPTS / "new_entry.py").read_bytes())
        self.payload = self.root / "quad.json"
        self.payload.write_text(json.dumps(quad()), encoding="utf-8")

    def gen(self, payload=None):
        return subprocess.run(
            [PY, str(self.root / "scripts" / "new_entry.py"), "--type", "eval-quad",
             "--ac-ref", "IR-0006/W5-E1/AC-10a", "--sealed-by", "fixture-owner",
             "--payload-file", str(payload or self.payload), "--root", str(self.root)],
            capture_output=True, text=True, encoding="utf-8")

    def test_green_generation_and_hash_formula(self):
        r = self.gen()
        self.assertEqual(r.returncode, 0, r.stderr)
        entry = json.loads((self.root / "entries" / "HO-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(entry["type"], "eval-quad")
        # sealed_sha256 = sha256(canonical payload)——与既有类型同公式（ADR-0056）
        self.assertEqual(entry["sealed_sha256"], sha256(canon(entry["payload"]).encode()).hexdigest())
        # index 登记整条目哈希
        idx = (self.root / "entries" / "index.yaml").read_text(encoding="utf-8")
        self.assertIn("HO-0001", idx)

    def test_bad_quad_rejected_no_side_effect(self):
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"quad": {"code": {"name": "x"}}}), encoding="utf-8")
        r = self.gen(bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("eval-quad payload 结构非法", r.stderr)
        self.assertFalse((self.root / "entries").exists() or
                         list((self.root / "entries").glob("*.json")))  # 拒绝=零副作用


if __name__ == "__main__":
    unittest.main()
