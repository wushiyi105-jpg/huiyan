"""工具层:定义模型可调用的工具,并负责执行。"""

from __future__ import annotations

from . import db as dbmod


def tools_description() -> str:
    lines = [
        "1. save_metric —— 保存一项健康指标(血压/血糖/血脂/体重等)。参数: name(指标名)、value(数值)、unit(单位,可选)、date(日期,可选)",
        "2. query_metrics —— 查询健康指标历史(趋势对比)。参数: name(指标名,可选;不传则返回全部指标)",
        "3. save_note —— 保存一条识物记录。参数: category(图片类型)、title(标题)、content(内容)",
        "4. list_notes —— 查看最近的识物记录。参数: limit(可选,默认10)",
    ]
    return "\n".join(lines)


def execute_tool(name: str, args: dict, db: dbmod.Database) -> dict:
    args = args or {}

    if name == "save_metric":
        nm = str(args.get("name", "")).strip()
        val = float(args.get("value", 0))
        unit = str(args.get("unit", "")).strip()
        d = str(args.get("date", "")).strip() or dbmod.today()
        tid = db.save_metric(nm, val, unit, d)
        return {"id": tid, "saved": f"{nm} {val} {unit}".strip(), "date": d}

    if name == "query_metrics":
        nm = str(args.get("name", "")).strip()
        if nm:
            rows = db.query_metrics(nm, int(args.get("limit", 20)))
            return {"name": nm, "count": len(rows), "history": rows}
        return {"count": len(db.all_metrics()), "history": db.all_metrics(int(args.get("limit", 50)))}

    if name == "save_note":
        category = str(args.get("category", "")).strip()
        title = str(args.get("title", "")).strip()
        content = str(args.get("content", "")).strip()
        tid = db.save_note(category, title, content)
        return {"id": tid, "saved": f"[{category}] {title}"}

    if name == "list_notes":
        rows = db.list_notes(int(args.get("limit", 10)))
        return {"count": len(rows), "notes": rows}

    return {"error": f"未知工具: {name}"}


def is_valid_tool(name: str) -> bool:
    return name in {"save_metric", "query_metrics", "save_note", "list_notes"}
