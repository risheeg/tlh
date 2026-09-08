"""Subcommand: links."""

from __future__ import annotations

import argparse

from cli.common import _api_links, _base_url, _get_user_id, _print_api_links


def cmd_links(args: argparse.Namespace) -> None:
    """Print local API links in logical order."""
    values = {"user_id": str(_get_user_id())}
    _print_api_links(_base_url(args), _api_links(), values)
