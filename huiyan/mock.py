"""离线演示模式:无 API key 时的回退。

图片识别依赖视觉模型,离线无法完成,故给出友好提示;纯文本的
「记录/查询」指令仍可离线处理,供演示与单元测试使用。
"""

from __future__ import annotations

from . import db as dbmod


def run(image_path: str, question: str, db: dbmod.Database) -> dict:
    steps: list[dict] = []

    if image_path:
        return {
            "answer": "离线演示模式不支持图片识别(需要视觉模型)。请配置 LLM_API_KEY 后重试;\n"
                      "或者你也可以直接文字告诉我,比如「记录我的体重 65kg」。",
            "steps": steps,
        }

    # 纯文本:仅支持「记录体重/血压…」这类简单指令
    text = question or ""
    import re
    m = re.search(r"(体重|血压|血糖|体温|心率).{0,6}?([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        name = m.group(1)
        val = float(m.group(2))
        unit = {"体重": "kg", "血压": "mmHg", "血糖": "mmol/L", "体温": "℃", "心率": "次/分"}.get(name, "")
        tid = db.save_metric(name, val, unit)
        steps.append({"tool": "save_metric", "arguments": {"name": name, "value": val, "unit": unit}, "result": {"id": tid}})
        return {"answer": f"已记录 {name} {val} {unit}(离线规则版)。", "steps": steps}

    return {"answer": "我没太看懂。你可以传一张图片,或说「记录我的体重 65kg」。", "steps": steps}
