"""离线路径的单元测试(不依赖网络 / API key)。运行:python -m unittest discover tests"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from huiyan import agent, db as dbmod, llm, mock, tools  # noqa: E402


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = dbmod.Database(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.db.close()

    def test_metric_save_and_query(self):
        tid = self.db.save_metric("体重", 65.5, "kg", "2026-11-24")
        self.assertGreater(tid, 0)
        rows = self.db.query_metrics("体重")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 65.5)

    def test_metric_history_order(self):
        self.db.save_metric("血糖", 5.8, "mmol/L", "2026-11-20")
        self.db.save_metric("血糖", 6.2, "mmol/L", "2026-11-24")
        rows = self.db.query_metrics("血糖")
        self.assertEqual(rows[0]["value"], 6.2)  # 最新在前

    def test_note(self):
        tid = self.db.save_note("药品", "布洛芬", "饭后服用,注意剂量")
        self.assertGreater(tid, 0)
        notes = self.db.list_notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["category"], "药品")


class TestTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = dbmod.Database(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.db.close()

    def test_save_metric_tool(self):
        r = tools.execute_tool("save_metric", {"name": "血压", "value": 120, "unit": "mmHg"}, self.db)
        self.assertIn("saved", r)
        self.assertEqual(len(self.db.query_metrics("血压")), 1)

    def test_unknown_tool(self):
        r = tools.execute_tool("nope", {}, self.db)
        self.assertIn("error", r)


class TestMock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = dbmod.Database(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.db.close()

    def test_mock_text_record(self):
        r = mock.run("", "记录我的体重 65kg", self.db)
        self.assertIn("体重", r["answer"])
        self.assertEqual(len(self.db.query_metrics("体重")), 1)

    def test_mock_image_graceful(self):
        r = mock.run("some/path.png", "这是什么", self.db)
        self.assertIn("不支持图片识别", r["answer"])

    def test_agent_falls_back_to_mock_without_key(self):
        p = os.path.join(self.tmp, "dummy.png")
        with open(p, "wb") as f:
            f.write(b"not-a-real-image")
        r = agent.run(p, "这是什么", db=self.db, config={"api_key": ""})
        self.assertIn("不支持图片识别", r["answer"])

    def test_run_invalid_path(self):
        r = agent.run("", "", db=self.db, config={"api_key": "x"})
        self.assertIn("有效的图片路径", r["answer"])


class TestLLM(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(llm.extract_json('{"answer": "hi"}'), {"answer": "hi"})


if __name__ == "__main__":
    unittest.main()
