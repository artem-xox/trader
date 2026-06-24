"""Eval CLI.

    uv run python -m tests.eval.cli run [--skill find]
    uv run python -m tests.eval.cli list
    uv run python -m tests.eval.cli add-case --trace <id> --skill find [--id ...] [--rubric ...]

`run` and `add-case` need LangSmith + OpenAI credentials (loaded from .env).
"""

from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

from tests.eval.cases import add_case, load_cases, skills


def _build_backend_and_evaluators():
    from tests.eval.backends.langsmith import LangSmithBackend
    from tests.eval.evaluators import Depth, Grounding, Quality, Routing, ToolCalls
    from trader.common.config import get_settings
    from trader.core.bootstrap import build_agent, get_model

    settings = get_settings()
    agent = build_agent(settings)
    judge = get_model(settings.openai_model_weak, settings)
    evaluators = [Grounding(), Routing(), ToolCalls(), Quality(judge), Depth(judge)]
    return LangSmithBackend(agent), evaluators


async def _run(skill: str | None) -> None:
    backend, evaluators = _build_backend_and_evaluators()
    targets = [skill] if skill else skills()
    for name in targets:
        cases = load_cases(name)
        print(f"running '{name}': {len(cases)} case(s)...")
        experiment = await backend.run(name, cases, evaluators)
        print(f"  experiment: {experiment}")
        summary = backend.summarize(experiment)
        means = "  ".join(f"{k}={v:.2f}" for k, v in sorted(summary["means"].items()))
        print(f"  scores: {means}")
        cost, tokens = summary["total_cost"], summary["total_tokens"]
        cost_s = f"${cost:.4f}" if cost is not None else "n/a"
        tokens_s = f"{tokens:,}" if tokens is not None else "n/a"
        print(f"  total cost: {cost_s}  |  total tokens: {tokens_s}")


def _list() -> None:
    for name in skills():
        cases = load_cases(name)
        print(f"{name}: {len(cases)} case(s)")
        for case in cases:
            print(f"  - {case.id}: {case.input}")


def _add_case(args: argparse.Namespace) -> None:
    from tests.eval.backends.langsmith import LangSmithBackend
    from trader.core.bootstrap import build_agent

    backend = LangSmithBackend(build_agent())
    case = backend.read_case_from_trace(
        args.trace, args.skill, case_id=args.id, rubric=args.rubric
    )
    path = add_case(case)
    print(f"added case '{case.id}' (input: {case.input!r}) → {path}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="eval")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run evals for one or all skills")
    run_p.add_argument("--skill", help="skill to run; omit for all")

    sub.add_parser("list", help="list skills and their cases")

    add_p = sub.add_parser("add-case", help="distill a case from a LangSmith trace")
    add_p.add_argument("--trace", required=True, help="LangSmith run/trace id")
    add_p.add_argument("--skill", required=True, help="dataset to add the case to")
    add_p.add_argument("--id", help="case id (default: derived from skill + trace)")
    add_p.add_argument("--rubric", help="per-case quality rubric (default: skill rubric)")

    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(_run(args.skill))
    elif args.command == "list":
        _list()
    elif args.command == "add-case":
        _add_case(args)


if __name__ == "__main__":
    main()
