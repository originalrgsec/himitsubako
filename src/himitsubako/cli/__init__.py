"""himitsubako CLI — hmb command group."""

from __future__ import annotations

import click

from himitsubako.cli.init import init
from himitsubako.cli.rotate import rotate_key
from himitsubako.cli.secrets import (
    delete_secret,
    direnv_export,
    get_secret,
    list_secrets,
    set_secret,
)


@click.group()
@click.version_option(package_name="himitsubako")
def main() -> None:
    """himitsubako — multi-backend credential management for solo developers."""


main.add_command(init)
main.add_command(get_secret)
main.add_command(set_secret)
main.add_command(delete_secret)
main.add_command(list_secrets)
main.add_command(rotate_key)
main.add_command(direnv_export)
