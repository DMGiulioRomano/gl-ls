"""Entry point: ``glls`` (o ``python -m glls``) avvia il server su stdio."""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="glls",
        description="gl-ls: language server per il linguaggio di granulazione "
                    "(study.yml).",
    )
    parser.add_argument("--tcp", action="store_true",
                        help="ascolta su TCP invece che stdio (debug)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--version", action="store_true",
                        help="stampa la versione ed esce")
    args = parser.parse_args(argv)

    from . import __version__

    if args.version:
        print(f"gl-ls {__version__}")
        return 0

    from .server import server

    if args.tcp:
        server.start_tcp(args.host, args.port)
    else:
        server.start_io()
    return 0


if __name__ == "__main__":
    sys.exit(main())
