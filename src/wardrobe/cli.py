"""Command line: `wardrobe serve | demo | import | check`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wardrobe", description="Wardrobe MCP server")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the MCP server (public port) and the Shortcuts API (private port)")
    demo = sub.add_parser("demo", help="create a demo wardrobe folder with drawn placeholder photos")
    demo.add_argument("folder", type=Path)
    imp = sub.add_parser("import", help="import product links into WARDROBE_DIR")
    imp.add_argument("urls", nargs="*", help="links; or use --file")
    imp.add_argument("--file", type=Path, help="text file with one link per line (# comments allowed)")
    sub.add_parser("check", help="validate the wardrobe folder and print a summary")
    sub.add_parser("secret", help="print a random passphrase/token you can use in the env file")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "secret":
        print(secrets.token_urlsafe(24))
        return 0
    if args.command == "demo":
        from wardrobe.demo import make_demo

        print(f"Created {make_demo(args.folder)} demo items in {args.folder}")
        return 0

    from wardrobe.config import Config, ConfigError

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.command == "serve":
        asyncio.run(serve(config))
        return 0
    if args.command == "check":
        return check(config)
    if args.command == "import":
        urls = list(args.urls)
        if args.file:
            urls += [ln.strip() for ln in args.file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if not urls:
            parser.error("give links or --file")
        return asyncio.run(import_links(config, urls))
    return 1


async def serve(config) -> None:
    import uvicorn

    from wardrobe.server import Wardrobe, build_mcp, build_private_app, build_public_app

    w = Wardrobe(config)
    w.state.cleanup()
    mcp = build_mcp(w)
    public = build_public_app(w, mcp)
    private = build_private_app(w)
    log = logging.getLogger("wardrobe")
    log.info("wardrobe: %d items in %s", len(w.catalog.items()), config.wardrobe_dir)
    for err in w.catalog.errors:
        log.warning("wardrobe folder: %s", err)
    log.info("public  (Funnel → this): http://%s:%d  — MCP at %s/mcp", config.bind, config.public_port, config.public_url)
    log.info("private (tailnet only):  http://%s:%d  — /location /import /inbox", config.bind, config.private_port)
    servers = [
        uvicorn.Server(uvicorn.Config(public, host=config.bind, port=config.public_port, proxy_headers=True,
                                      forwarded_allow_ips="127.0.0.1", log_level="info")),
        uvicorn.Server(uvicorn.Config(private, host=config.bind, port=config.private_port, log_level="info")),
    ]
    await asyncio.gather(*(s.serve() for s in servers))


def check(config) -> int:
    from wardrobe.catalog import Catalog

    catalog = Catalog(config.wardrobe_dir)
    catalog.refresh(force=True)
    items = catalog.items(include_inactive=True)
    print(f"{len(items)} items in {config.wardrobe_dir}")
    for item in items:
        flags = []
        if not item.photos:
            flags.append("NO PHOTO")
        if item.get("needs_review"):
            flags.append("needs review")
        if item.inferred:
            flags.append("guessed: " + ",".join(sorted(item.inferred)))
        if not item.active:
            flags.append(item.status)
        print(f"  {item.id:55s} {item.category:11s} {' | '.join(flags)}")
    for err in catalog.errors:
        print(f"ERROR {err}")
    inbox = catalog.inbox_files()
    if inbox:
        print(f"{len(inbox)} photo(s) waiting in inbox/")
    return 1 if catalog.errors else 0


async def import_links(config, urls: list[str]) -> int:
    from wardrobe.catalog import Catalog
    from wardrobe.importer import import_url

    catalog = Catalog(config.wardrobe_dir)
    catalog.ensure_layout()
    failed = 0
    for url in urls:
        result = await import_url(catalog, url, chromium=config.chromium)
        if result.existing and result.item:
            print(f"exists  {result.item.id}")
        elif result.item:
            print(f"added   {result.item.id}" + (f"  ({result.error})" if result.error else ""))
        else:
            failed += 1
            print(f"FAILED  {url}: {result.error}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
