"""核心 Agent:多步工具调用循环 + 多模态(图片)输入。"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from datetime import date

from . import llm, mock, tools
from .db import Database
from .llm import LLMError

MAX_STEPS = 16

_SYSTEM = """你是「慧眼」,一个拍照识物生活助手。用户会上传一张图片(可能附一段文字),你识别图片内容并给出通俗易懂的解读与建议。

图片常见类型:体检报告/化验单、药品说明书、衣服标签、食品配料表、植物、票据/收据、电器说明书、其他。

你只能通过调用工具来完成操作。每次回复必须是下面两种之一(只输出 JSON,不要任何解释):

1) 调用工具:
{"tool":"工具名","arguments":{参数}}

2) 最终回答(任务完成时):
{"answer":"给用户看的回答"}

规则:
- 先判断图片类型,再决定怎么解读。
- 图片里若有健康/化验指标(血压、血糖、血脂、体重等),务必:先 save_metric 逐项保存,再 query_metrics 对比历史,回答里说明变化趋势。
- 高效起见:保存完所有指标后,用一次 query_metrics(不传 name)拿到全部历史即可,不要逐项查询,然后直接给出回答。
- 若图片里的指标与当天已有记录完全相同(重复上传同一张),不必重复保存,直接 query_metrics 对比并回答。
- 解读要通俗易懂;涉及疾病诊断时不要下结论,提醒用户咨询医生。
- 药品类:说明用法用量、禁忌、注意事项。
- 标签/配料类:说明材质/成分、洗涤护理或健康提示。
- 植物类:说明品种与养护要点。
- 今天是 {today}。
- 一步一步来,每次只调用一个工具,拿到结果后再决定下一步。

可用工具:
{tools}"""


def _image_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _use_model(config: dict | None, force_mock: bool) -> bool:
    if force_mock:
        return False
    cfg = {**llm.default_config(), **(config or {})}
    return bool(cfg.get("api_key"))


def _cfg(config: dict | None) -> dict:
    return {**llm.default_config(), **(config or {})}


def run(image_path: str, question: str = "", db: Database | None = None,
        config: dict | None = None, force_mock: bool = False) -> dict:
    """识别一张本地图片,返回 {answer, steps}。"""
    db = db or Database()
    if not image_path or not os.path.isfile(image_path):
        return {"answer": "请提供有效的图片路径。", "steps": []}
    if not _use_model(config, force_mock):
        return mock.run(image_path, question, db)
    return _analyze(_image_data_url(image_path), question, db, config)


def run_data(image_b64: str, mime: str, question: str = "", db: Database | None = None,
             config: dict | None = None, force_mock: bool = False) -> dict:
    """识别一段 base64 图片数据(Web 上传用),返回 {answer, steps}。"""
    db = db or Database()
    if not _use_model(config, force_mock):
        return mock.run("", question, db)
    return _analyze(f"data:{mime or 'image/jpeg'};base64,{image_b64}", question, db, config)


def _analyze(image_url: str, question: str, db: Database, config: dict | None) -> dict:
    cfg = _cfg(config)
    system = _SYSTEM.replace("{today}", date.today().isoformat()).replace("{tools}", tools.tools_description())
    content: list = [{"type": "text", "text": question.strip() or "请识别这张图片,给出解读与建议。"}]
    content.append({"type": "image_url", "image_url": {"url": image_url}})
    history: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]
    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        raw = llm.chat(history, config=cfg, temperature=0.2, max_tokens=2048)
        try:
            data = llm.extract_json(raw)
        except LLMError:
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content": '输出格式不对,请严格按 JSON 输出:调用工具用 {"tool":"...","arguments":{...}},结束用 {"answer":"..."}。'})
            continue

        if not isinstance(data, dict):
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content": "请输出一个 JSON 对象。"})
            continue

        if "answer" in data:
            return {"answer": str(data["answer"]), "steps": steps}

        if "tool" in data and tools.is_valid_tool(str(data["tool"])):
            args = data.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            try:
                result = tools.execute_tool(str(data["tool"]), args, db)
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            steps.append({"tool": str(data["tool"]), "arguments": args, "result": result})
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content": "工具执行结果:" + json.dumps(result, ensure_ascii=False, default=str)})
            continue

        history.append({"role": "assistant", "content": raw})
        history.append({"role": "user", "content": '无法识别。请输出 {"tool":"工具名","arguments":{...}} 或 {"answer":"..."}。'})

    return {"answer": "达到最大步骤数仍未完成,请换个说法再试。", "steps": steps}
