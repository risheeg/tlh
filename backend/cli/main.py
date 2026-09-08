"""Entrypoint for the tlh CLI."""

from __future__ import annotations

from cli.parser import build_parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
