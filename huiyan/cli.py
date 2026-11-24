"""命令行入口:python -m huiyan <图片路径> ["问题"] 或 python -m huiyan <子命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, db as dbmod, llm
from .llm import LLMError

MOCK_BANNER = (
    "⚠️  当前为离线演示模式(未配置 LLM_API_KEY)。图片识别需要视觉模型,\n"
    "   在 .env 填入 LLM_API_KEY 后即可;离线模式仅支持纯文字记录。\n"
)


def _get_db(args) -> dbmod.Database:
    return dbmod.Database(args.db if getattr(args, "db", None) else None)


def _render_steps(steps: list[dict]) -> str:
    if not steps:
        return ""
    lines = ["", "📋 执行步骤:"]
    for i, s in enumerate(steps, 1):
        args = json.dumps(s.get("arguments", {}), ensure_ascii=False)
        lines.append(f"  {i}. {s['tool']}({args})")
        res = s.get("result", {})
        if isinstance(res, dict) and "error" in res:
            lines.append(f"     ❌ {res['error']}")
        elif isinstance(res, dict) and "saved" in res:
            lines.append(f"     ✓ {res['saved']}")
    return "\n".join(lines)


def _emit(r: dict, args):
    if getattr(args, "json", False):
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("🔍 " + r["answer"].replace("\n", "\n   "))
        print(_render_steps(r["steps"]))


def cmd_analyze(args):
    db = _get_db(args)
    cfg = llm.config_from_args(args)
    question = " ".join(args.question) if args.question else ""
    r = agent.run(args.image, question=question, db=db, config=cfg, force_mock=args.mock)
    _emit(r, args)


def cmd_records(args):
    db = _get_db(args)
    metrics = db.all_metrics(20)
    notes = db.list_notes(20)
    if not metrics and not notes:
        print("还没有任何记录。拍张照片或说「记录我的体重 65kg」试试。")
        return
    if metrics:
        print(f"📈 健康指标({len(metrics)}):")
        for m in metrics:
            print(f"  · {m['date']}  {m['name']} {m['value']} {m['unit'] or ''}".rstrip())
    if notes:
        print(f"\n🗒 识物记录({len(notes)}):")
        for n in notes:
            print(f"  · [{n['category'] or '未分类'}] {n['title']}")


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db if getattr(args, "db", None) else None,
              force_mock=args.mock)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="huiyan",
        description="慧眼 · 拍照识物生活助手:拍一张图,识别内容并给出解读与建议。",
    )
    p.add_argument("--version", action="version", version=f"huiyan {__version__}")
    p.add_argument("--mock", action="store_true", help="强制离线演示模式(不调用模型)")
    p.add_argument("--json", action="store_true", help="以 JSON 输出原始结果")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 数据库路径")

    sub = p.add_subparsers(dest="command")

    ap = sub.add_parser("analyze", help="识别一张图片")
    ap.add_argument("image", help="图片路径")
    ap.add_argument("question", nargs="*", help="可选问题,如「有什么问题吗」")
    ap.set_defaults(func=cmd_analyze)

    rp = sub.add_parser("records", help="查看健康指标与识物记录")
    rp.set_defaults(func=cmd_records)

    wp = sub.add_parser("web", help="启动 Web 界面")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.set_defaults(func=cmd_web)

    return p


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    known = {"analyze", "records", "web"}
    value_flags = {"--model", "--base-url", "--api-key", "--db"}
    i = 0
    while i < len(raw):
        tok = raw[i]
        if tok in value_flags:
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            break
    if i < len(raw) and raw[i] not in known:
        raw.insert(i, "analyze")
    args = build_parser().parse_args(raw)
    if args.command is None:
        build_parser().print_help()
        sys.exit(0)

    if not args.mock and args.command in ("analyze",):
        if not llm.config_from_args(args).get("api_key"):
            print(MOCK_BANNER, file=sys.stderr)

    try:
        args.func(args)
    except LLMError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
