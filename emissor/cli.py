"""Linha de comando: `emissor web`, `emissor mcp`, `emissor status`."""

from __future__ import annotations

import argparse
import json


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="emissor", description="Emissor de NFS-e Padrão Nacional (Simples Nacional)")
    sub = parser.add_subparsers(dest="comando", required=True)

    web = sub.add_parser("web", help="inicia a interface web")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--porta", type=int, default=8000)
    web.add_argument("--debug", action="store_true")

    mcp = sub.add_parser("mcp", help="inicia o MCP server (stdio por padrão)")
    mcp.add_argument("--http", action="store_true", help="usa transporte streamable HTTP em vez de stdio")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--porta", type=int, default=8001)

    sub.add_parser("status", help="mostra o diagnóstico da configuração")

    args = parser.parse_args(argv)
    if args.comando == "web":
        from .web.app import main as web_main

        web_main(args.host, args.porta, args.debug)
    elif args.comando == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main("http" if args.http else "stdio", args.host, args.porta)
    elif args.comando == "status":
        from .servico import Emissor

        print(json.dumps(Emissor().status(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
