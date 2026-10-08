#!/usr/bin/env python3
"""Make the shop stop handing the browser every variant price, for one browser only.

WebArena's Magento publishes the whole price table on first load. It sits in the page as
`optionPrices`, and the configurable widget renders each option label with its surcharge,
"2 x 9.5L +$32.50". Both are readable in the first observation an agent takes, so the price
a shopper asks about is not really gated here the way it is on the live marketplace, where
the page holds exactly one price at a time. Measured across the recorded runs, the agent
selects a pack size in 11 of 122 runs on the fifteen seller markets and adds the surcharge
to the base price instead in 48 of 290 stored answers.

This selects the suppressing theme by **user agent**, which leaves the shop otherwise
untouched. That is the whole point. Every run already recorded was made with an ordinary
user agent and still renders exactly as it did, so no recorded run loses the environment it
was measured in. A run whose browser reports `IGRGated` sees the same products, at the same
prices, at the same URLs, through a theme that suppresses the price table. The two together
are an A and B with nothing else moving, not even the address bar.

A second store view was tried first and abandoned. Magento resolves a theme per store view,
but it carries the store only in the query string or in a URL prefix, and neither survives
the agent following an ordinary product link, so half the pages in a run rendered the wrong
way. The user agent travels with every request by construction.

    python env/install_gated_theme.py --check     # report what is installed
    python env/install_gated_theme.py --install
    python env/install_gated_theme.py --remove    # put the shop back

Run the gated arm by giving the browser that user agent:

    PLAYWRIGHT_MCP_ARGS='-y @playwright/mcp@latest --user-agent "Mozilla/5.0 IGRGated/1.0"' \
        python experiments/runners/suite.py --tasks experiments/tasks/tasks_heldout_gated.json --repeats 3
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
THEME_SRC = HERE / "gated_theme"
CONTAINER = "webarena-shopping"
MAGE = "/var/www/magento2"
THEME_DEST = f"{MAGE}/app/design/frontend/IGR/suppressed"
THEME_PATH = "IGR/suppressed"
UA_MARKER = "IGRGated"

SQL_INSTALL = f"""
INSERT INTO theme (parent_id, theme_path, theme_title, is_featured, area, type, code)
SELECT theme_id, '{THEME_PATH}', 'IGR Suppressed Variant Pricing', 0, 'frontend', 0, '{THEME_PATH}'
FROM theme WHERE theme_path='Magento/blank'
  AND NOT EXISTS (SELECT 1 FROM (SELECT * FROM theme) t WHERE t.theme_path='{THEME_PATH}');

DELETE FROM core_config_data WHERE path='design/theme/ua_regexp';

-- Magento hands this straight to preg_match, so the pattern needs its delimiters, and it
-- reads the key `regexp`. Getting either wrong takes every page of the shop down with a
-- 500, which is how both were found.
INSERT INTO core_config_data (scope, scope_id, path, value)
SELECT 'default', 0, 'design/theme/ua_regexp',
       CONCAT('[{{"regexp":"/{UA_MARKER}/","value":"', theme_id, '"}}]')
FROM theme WHERE theme_path='{THEME_PATH}';
"""

SQL_REMOVE = f"""
DELETE FROM core_config_data WHERE path='design/theme/ua_regexp';
DELETE FROM theme WHERE theme_path='{THEME_PATH}';
"""

SQL_CHECK = f"""
SELECT 'theme', theme_id, theme_path FROM theme WHERE theme_path='{THEME_PATH}';
SELECT 'ua rule', value FROM core_config_data WHERE path='design/theme/ua_regexp';
"""


def mysql(statements: str) -> str:
    """Run SQL in the container. These are the fixed image credentials, not secrets."""
    done = subprocess.run(
        ["docker", "exec", CONTAINER, "mysql", "-u", "magentouser", "-pMyPassword",
         "magentodb", "-N", "-e", statements],
        capture_output=True, text=True,
    )
    return "\n".join(line for line in (done.stdout + done.stderr).splitlines()
                     if "Using a password" not in line)


def flush() -> None:
    subprocess.run(["docker", "exec", CONTAINER, "php", f"{MAGE}/bin/magento", "cache:flush"],
                   capture_output=True, text=True)


def copy_theme() -> None:
    subprocess.run(["docker", "exec", CONTAINER, "mkdir", "-p", THEME_DEST], check=True)
    for path in sorted(THEME_SRC.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(THEME_SRC)
        target = f"{THEME_DEST}/{relative.as_posix()}"
        subprocess.run(["docker", "exec", CONTAINER, "mkdir", "-p",
                        str(pathlib.PurePosixPath(target).parent)], check=True)
        subprocess.run(["docker", "cp", str(path), f"{CONTAINER}:{target}"], check=True)
        print(f"  copied {relative.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.install:
        copy_theme()
        print(mysql(SQL_INSTALL) or "  database rows in place")
        flush()
        print(f"installed. Run the gated arm with a browser reporting {UA_MARKER}:")
        print("  PLAYWRIGHT_MCP_ARGS='-y @playwright/mcp@latest "
              f"--user-agent \"Mozilla/5.0 {UA_MARKER}/1.0\"'")
        return 0

    if args.remove:
        print(mysql(SQL_REMOVE) or "  database rows removed")
        subprocess.run(["docker", "exec", CONTAINER, "rm", "-rf", THEME_DEST], check=False)
        flush()
        print("removed. Ordinary browsing was never touched.")
        return 0

    print(mysql(SQL_CHECK) or "  nothing installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
