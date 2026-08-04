from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import select

from src.db import async_session_maker
from src.eval.agent_eval import run_agent_eval
from src.eval.runner import run_compare, run_compare_all_providers, run_eval, run_eval_all_providers
from src.ingest.pipeline import IngestSummary, delete_provider_data, run_ingest
from src.logging import configure_logging, get_logger
from src.models import Provider
from src.providers import (
    ProviderConfig,
    ProviderConfigError,
    add_provider,
    get_provider,
    load_providers,
    remove_provider,
)
from src.retrieval.factory import STRATEGIES

logger = get_logger(__name__)


async def _ingested_providers() -> dict[str, Provider]:
    async with async_session_maker() as session:
        rows = (await session.execute(select(Provider))).scalars().all()
    return {row.id: row for row in rows}


async def _providers_list() -> None:
    configured = load_providers()
    ingested = await _ingested_providers()

    if not configured and not ingested:
        print("No providers configured. Add one in specs.yaml, or run:")
        print("  specpilot ingest --url <spec-url> --id <id> --name <name>")
        return

    for provider_id, config in configured.items():
        row = ingested.get(provider_id)
        if row is None:
            print(f"WARN {provider_id} ({config.name}): configured, not yet ingested")
        else:
            print(
                f"OK   {provider_id} ({config.name}): {row.endpoint_count} endpoints, "
                f"openapi {row.openapi_version or '?'}, ingested {row.ingested_at}"
            )

    for provider_id, row in ingested.items():
        if provider_id not in configured:
            print(f"WARN {provider_id}: {row.endpoint_count} endpoints ingested, no longer in specs.yaml")


async def _providers_remove(provider_id: str) -> None:
    was_configured = remove_provider(provider_id)
    async with async_session_maker() as session:
        await delete_provider_data(session, provider_id)
    if was_configured:
        print(f"OK removed provider {provider_id!r}: specs.yaml entry and all ingested data")
    else:
        print(f"OK removed provider {provider_id!r}: ingested data (no specs.yaml entry existed)")


def _print_ingest_summary(summary: IngestSummary) -> None:
    skipped_total = sum(summary.skipped.values())
    line = (
        f"OK ingested {summary.provider_id}: {summary.endpoints_parsed} endpoints, "
        f"{summary.parameters_extracted} parameters, {summary.chunks_embedded} chunks embedded"
    )
    if skipped_total:
        line += f", {skipped_total} skipped ({summary.skipped})"
    print(line)


async def _ingest_one(provider: ProviderConfig, refresh: bool) -> None:
    async with async_session_maker() as session:
        summary = await run_ingest(session, provider, refresh=refresh)
    _print_ingest_summary(summary)


async def _ingest(args: argparse.Namespace) -> None:
    if args.all:
        providers = load_providers()
        if not providers:
            print("FAIL no providers configured in specs.yaml")
            return
        for provider in providers.values():
            await _ingest_one(provider, args.refresh)
        return

    if args.provider:
        try:
            provider = get_provider(args.provider)
        except ProviderConfigError as error:
            print(f"FAIL {error}")
            return
        await _ingest_one(provider, args.refresh)
        return

    # --url or --file: ad hoc provider, appended to specs.yaml so it's re-ingestible later.
    if not args.id:
        print("FAIL --id is required with --url or --file")
        return
    try:
        provider = add_provider(args.id, name=args.name, url=args.url, file_path=args.file)
    except ProviderConfigError as error:
        print(f"FAIL {error}")
        return
    await _ingest_one(provider, refresh=True)


def _print_report_summary(label: str, report: dict[str, Any]) -> None:
    print(f"OK {label}: splits={list(report.get('splits', {}).keys())}")


async def _eval(args: argparse.Namespace) -> None:
    if args.mode == "agent":
        if args.all_providers:
            for provider_id in load_providers():
                report = await run_agent_eval(provider_id, split=args.split, seed=args.seed)
                _print_report_summary(f"agent eval {provider_id}", report)
            return
        report = await run_agent_eval(args.provider, split=args.split, seed=args.seed)
        _print_report_summary(f"agent eval {args.provider}", report)
        return

    if args.all_providers:
        report = await run_eval_all_providers(split=args.split, seed=args.seed, strategy=args.strategy)
        _print_report_summary("eval (all providers)", report)
        return

    report = await run_eval(args.provider, split=args.split, seed=args.seed, strategy=args.strategy)
    _print_report_summary(f"eval {args.provider}", report)


async def _compare(args: argparse.Namespace) -> None:
    if args.all_providers:
        report = await run_compare_all_providers(split=args.split, seed=args.seed)
        _print_report_summary("compare (all providers)", report)
        return

    report = await run_compare(args.provider, split=args.split, seed=args.seed)
    _print_report_summary(f"compare {args.provider}", report)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="specpilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    providers_parser = subparsers.add_parser("providers")
    providers_subparsers = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_subparsers.add_parser("list")
    remove_parser = providers_subparsers.add_parser("remove")
    remove_parser.add_argument("provider_id")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_group = ingest_parser.add_mutually_exclusive_group(required=True)
    ingest_group.add_argument("--provider", help="ingest one configured provider by id")
    ingest_group.add_argument("--all", action="store_true", help="ingest every configured provider")
    ingest_group.add_argument("--url", help="ad hoc: spec URL for a new provider")
    ingest_group.add_argument("--file", help="ad hoc: local spec file path for a new provider")
    ingest_parser.add_argument("--id", help="provider id, required with --url/--file")
    ingest_parser.add_argument("--name", help="provider display name, optional with --url/--file")
    ingest_parser.add_argument("--refresh", action="store_true", help="re-download/re-parse/re-embed")

    for command in ("eval", "compare"):
        p = subparsers.add_parser(command)
        provider_group = p.add_mutually_exclusive_group(required=True)
        provider_group.add_argument("--provider", help="run against one ingested provider")
        provider_group.add_argument(
            "--all-providers", action="store_true", help="run against every ingested provider"
        )
        p.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
        p.add_argument("--seed", type=int, default=None)
        if command == "eval":
            p.add_argument("--strategy", choices=STRATEGIES, default=None)
            p.add_argument("--mode", choices=["single_pass", "agent"], default="single_pass")

    args = parser.parse_args()

    if args.command == "providers":
        if args.providers_command == "list":
            asyncio.run(_providers_list())
        elif args.providers_command == "remove":
            asyncio.run(_providers_remove(args.provider_id))
    elif args.command == "ingest":
        asyncio.run(_ingest(args))
    elif args.command == "eval":
        asyncio.run(_eval(args))
    elif args.command == "compare":
        asyncio.run(_compare(args))


if __name__ == "__main__":
    main()
