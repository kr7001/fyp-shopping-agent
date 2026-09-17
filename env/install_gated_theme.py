#!/usr/bin/env python3
"""Install the store view whose pages do not hand the browser every variant price.

WebArena's Magento publishes the whole price table on first load. It sits in the page as
`optionPrices`, and the configurable widget renders each option label with its surcharge,
"2 x 9.5L +$32.50". Both are readable in the first observation an agent takes, so the price
a shopper asks about is not really gated here the way it is on the live marketplace, where
the page holds exactly one price at a time. Measured across the recorded runs, the agent
selects a pack size in 11 of 122 runs on the fifteen seller markets and adds the surcharge
to the base price instead in 48 of 290 stored answers.

This installs a second **store view** rather than changing the shop. That distinction is the
whole point. Every run already recorded was made against store view `default`, and it keeps
rendering exactly as it did, so no recorded run loses the environment it was measured in.
The new store view `gated` shows the same products at the same prices through a theme that
suppresses the price table, and the two together are an A and B with nothing else moving.

    python env/install_gated_theme.py --check     # report what is installed
    python env/install_gated_theme.py --install
    python env/install_gated_theme.py --remove    # put the shop back

After installing, the search index has to be built for the new store view, which this does
not do for you because it is slow and because two reindexes running at once is how this
container gets a stuck index:

    docker exec webarena-shopping php /var/www/magento2/bin/magento indexer:reindex catalogsearch_fulltext
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
STORE_CODE = "gated"

SQL_INSTALL = f"""
INSERT INTO theme (parent_id, theme_path, theme_title, is_featured, area, type, code)
SELECT theme_id, '{THEME_PATH}', 'IGR Suppressed Variant Pricing', 0, 'frontend', 0, '{THEME_PATH}'
FROM theme WHERE theme_path='Magento/blank'
  AND NOT EXISTS (SELECT 1 FROM (SELECT * FROM theme) t WHERE t.theme_path='{THEME_PATH}');

INSERT INTO store (code, website_id, group_id, name, sort_order, is_active)
SELECT '{STORE_CODE}', 1, 1, 'Gated Variant Pricing', 10, 1
FROM dual WHERE NOT EXISTS (SELECT 1 FROM (SELECT * FROM store) s WHERE s.code='{STORE_CODE}');

INSERT INTO core_config_data (scope, scope_id, path, value)
SELECT 'stores', s.store_id, 'design/theme/theme_id', t.theme_id
FROM store s, theme t
WHERE s.code='{STORE_CODE}' AND t.theme_path='{THEME_PATH}'
  AND NOT EXISTS (SELECT 1 FROM (SELECT * FROM core_config_data) c
                  WHERE c.scope='stores' AND c.scope_id=s.store_id
                    AND c.path='design/theme/theme_id');
"""

SQL_REMOVE = f"""
DELETE FROM core_config_data
 WHERE path='design/theme/theme_id' AND scope='stores'
   AND scope_id IN (SELECT store_id FROM (SELECT * FROM store) s WHERE s.code='{STORE_CODE}');
DELETE FROM store WHERE code='{STORE_CODE}';
DELETE FROM theme WHERE theme_path='{THEME_PATH}';
"""

SQL_CHECK = f"""
SELECT 'theme', theme_id, theme_path FROM theme WHERE theme_path='{THEME_PATH}';
SELECT 'store', store_id, code FROM store WHERE code='{STORE_CODE}';
SELECT 'config', scope, scope_id, value FROM core_config_data WHERE path='design/theme/theme_id';
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
        print("installed. Now build the search index for the new store view, on its own:")
        print(f"  docker exec {CONTAINER} php {MAGE}/bin/magento indexer:reindex "
              f"catalogsearch_fulltext")
        return 0

    if args.remove:
        print(mysql(SQL_REMOVE) or "  database rows removed")
        subprocess.run(["docker", "exec", CONTAINER, "rm", "-rf", THEME_DEST], check=False)
        flush()
        print("removed. The default store view was never touched.")
        return 0

    print(mysql(SQL_CHECK) or "  nothing installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
