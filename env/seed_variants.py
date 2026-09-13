#!/usr/bin/env python3
"""Author configurable products with per-variant pricing in a WebArena shopping site.

WebArena ships 104,368 products, all type simple, and 425,384 custom-option values
of which none carries a price delta. The environment therefore reproduces the shape
of interaction-gated options but not interaction-gated *pricing*, which is the
failure this project studies. This script adds that structure.

Everything it creates is prefixed IGR- and recorded in a manifest under manifests/,
so seeded rows stay separable from WebArena's own catalogue and the ground truth
for each seeded question is auditable after the fact.

Usage:
    python seed_variants.py seed
    python seed_variants.py verify
    python seed_variants.py teardown
    python seed_variants.py strip-notes
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

from magento import Magento, MagentoError

HERE = pathlib.Path(__file__).parent
FIXTURES = HERE / "fixtures" / "gated_pricing.json"
MANIFESTS = HERE / "manifests"

# Magento's own ids. 4 is the catalog_product entity type, 1 is Not Visible
# Individually, 4 is Catalog, Search. Children of a configurable are hidden so the
# storefront only surfaces the parent, which is what makes the price gated.
PRODUCT_ENTITY_TYPE_ID = "4"
VISIBILITY_NOT_INDIVIDUALLY = 1
VISIBILITY_CATALOG_SEARCH = 4


def slugify(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


# --------------------------------------------------------------------- attributes


def ensure_attribute(m: Magento, spec: dict, dry_run: bool = False) -> dict:
    """Create the dropdown attribute if absent, then make sure every option exists.

    Configurable attributes must be global scope. Magento silently refuses to use a
    store-scoped attribute in a configurable product, so that is set explicitly.
    """
    code, label = spec["code"], spec["label"]
    existing = m.attribute(code)
    if existing is None:
        if dry_run:
            print(f"  would create attribute {code}")
            return {"attribute_code": code, "attribute_id": None, "options": {}}
        existing = m.post("/products/attributes", {"attribute": {
            "attribute_code": code,
            "entity_type_id": PRODUCT_ENTITY_TYPE_ID,
            "frontend_input": "select",
            "scope": "global",
            "default_frontend_label": label,
            "frontend_labels": [{"store_id": 0, "label": label}],
            "is_required": False,
            "is_unique": False,
            "is_user_defined": True,
            "is_visible_on_front": True,
            "used_in_product_listing": True,
        }})
        print(f"  created attribute {code} (id {existing['attribute_id']})")
    else:
        print(f"  attribute {code} already present (id {existing['attribute_id']})")

    for position, option_label in enumerate(spec["options"]):
        ensure_attribute_option(m, code, option_label, position, dry_run)

    return existing


def ensure_attribute_option(m: Magento, code: str, label: str,
                            position: int, dry_run: bool = False) -> None:
    if label in option_index(m, code, refresh=True):
        return
    if dry_run:
        print(f"    would add option {code}={label}")
        return
    m.post(f"/products/attributes/{code}/options",
           {"option": {"label": label, "sort_order": position}})
    print(f"    added option {code}={label}")


_option_cache: dict[str, dict[str, str]] = {}


def option_index(m: Magento, code: str, refresh: bool = False) -> dict[str, str]:
    """Map option label -> value_index for one attribute.

    Magento returns an empty-label placeholder row for optional attributes; it is
    dropped here so callers can look up by label without guarding.
    """
    if refresh or code not in _option_cache:
        options = m.get(f"/products/attributes/{code}/options")
        _option_cache[code] = {o["label"]: o["value"] for o in options if o["label"]}
    return _option_cache[code]


def ensure_attribute_in_set(m: Magento, code: str, set_id: int,
                            dry_run: bool = False) -> None:
    """Attach the attribute to the attribute set, into the Product Details group."""
    # The REST representation of a group carries a name but not the group code, so
    # the default group is matched by name and falls back to the first group.
    groups = m.attribute_set_groups(set_id)
    group = next((g for g in groups if g["attribute_group_name"] == "Product Details"),
                 groups[0])
    if dry_run:
        print(f"  would attach {code} to set {set_id}/{group['attribute_group_name']}")
        return
    try:
        m.post("/products/attribute-sets/attributes", {
            "attributeSetId": set_id,
            "attributeGroupId": int(group["attribute_group_id"]),
            "attributeCode": code,
            "sortOrder": 100,
        })
        print(f"  attached {code} to attribute set {set_id}")
    except MagentoError as exc:
        # Magento 400s on a duplicate attach rather than treating it as a no-op.
        if exc.status != 400:
            raise
        print(f"  {code} already in attribute set {set_id}")


# ----------------------------------------------------------------------- products


def ensure_child(m: Magento, family: dict, variant: dict, value_index: str,
                 fixture: dict, dry_run: bool = False) -> str:
    """Create one purchasable variant. Hidden from listings so its price is gated."""
    sku = variant["sku"]
    name = f"{family['name']} - {variant['option']}"
    qty = variant["qty"]

    if m.product(sku) is not None:
        print(f"    child {sku} already present")
        return sku
    if dry_run:
        print(f"    would create child {sku} at {variant['price']}")
        return sku

    m.post("/products", {"product": {
        "sku": sku,
        "name": name,
        "attribute_set_id": fixture["attribute_set_id"],
        "price": variant["price"],
        "status": 1,
        "visibility": VISIBILITY_NOT_INDIVIDUALLY,
        "type_id": "simple",
        "extension_attributes": {
            "website_ids": fixture["website_ids"],
            "stock_item": {
                "qty": qty,
                "is_in_stock": qty > 0,
                "manage_stock": True,
                "use_config_manage_stock": False,
            },
        },
        "custom_attributes": [
            {"attribute_code": family["attribute"], "value": value_index},
            {"attribute_code": "url_key", "value": slugify(sku)},
        ],
    }})
    print(f"    created child {sku} at {variant['price']} (qty {qty})")
    return sku


def ensure_parent(m: Magento, family: dict, fixture: dict,
                  dry_run: bool = False) -> None:
    sku = family["parent_sku"]
    if m.product(sku) is not None:
        print(f"    parent {sku} already present")
        return
    if dry_run:
        print(f"    would create parent {sku}")
        return

    m.post("/products", {"product": {
        "sku": sku,
        "name": family["name"],
        "attribute_set_id": fixture["attribute_set_id"],
        "status": 1,
        "visibility": VISIBILITY_CATALOG_SEARCH,
        "type_id": "configurable",
        "extension_attributes": {
            "website_ids": fixture["website_ids"],
            "stock_item": {"is_in_stock": True, "manage_stock": False,
                           "use_config_manage_stock": False},
        },
        # The family's `note` is deliberately not sent. It used to become the product
        # description, and on the hand-written fixture those notes explain each trap and
        # in two cases state the answer ("Ground truth for 'cheapest 2 x 9.5L': this
        # seller, 22.50 against 24.90"). The description renders in the Details section,
        # which is inside the accessibility snapshot the agent reads, so the answer key
        # was in context for 59 of 60 baseline runs. Notes stay in the fixture JSON, where
        # the ground truth belongs, and never reach Magento. See README, 13 Sep 2026.
        "custom_attributes": [
            {"attribute_code": "category_ids",
             "value": [str(c) for c in family["category_ids"]]},
            {"attribute_code": "url_key", "value": slugify(sku)},
        ],
    }})
    print(f"    created parent {sku}")


def ensure_configurable_links(m: Magento, family: dict, attribute: dict,
                              value_indexes: list[str], child_skus: list[str],
                              dry_run: bool = False) -> None:
    """Declare which attribute varies, then attach the children to the parent."""
    parent = family["parent_sku"]
    if dry_run:
        print(f"    would link {len(child_skus)} children to {parent}")
        return

    existing_options = m.get(f"/configurable-products/{parent}/options/all")
    if not any(o["attribute_id"] == str(attribute["attribute_id"])
               for o in existing_options):
        m.post(f"/configurable-products/{parent}/options", {"option": {
            "attribute_id": str(attribute["attribute_id"]),
            "label": attribute["default_frontend_label"],
            "position": 0,
            "is_use_default": True,
            "values": [{"value_index": int(v)} for v in value_indexes],
        }})
        print(f"    declared {family['attribute']} as the varying attribute")

    linked = {c["sku"] for c in m.get(f"/configurable-products/{parent}/children")}
    for sku in child_skus:
        if sku in linked:
            continue
        m.post(f"/configurable-products/{parent}/child", {"childSku": sku})
        print(f"    linked {sku}")


# ------------------------------------------------------------------ ground truth


def unit_price(variant: dict) -> tuple[float, str] | None:
    """Price per litre or per kilo, whichever the variant's metadata supports.

    Returns None for variants with no size metadata, such as apparel sizes, where a
    unit price is not meaningful.
    """
    if "volume_ml" in variant:
        litres = variant["units"] * variant["volume_ml"] / 1000
        return round(variant["price"] / litres, 4), "per_litre"
    if "weight_g" in variant:
        kilos = variant["units"] * variant["weight_g"] / 1000
        return round(variant["price"] / kilos, 4), "per_kg"
    return None


def analyse(fixture: dict) -> dict:
    """Compute what a correct answer looks like, so runs can be scored without the UI.

    Two things matter per family: the 'from' price a card-level probe would see, and
    whether that price points at the same variant a full retrieval would choose. When
    they disagree, the family is a trap for minimal-observation retrieval.
    """
    families = {}
    for family in fixture["families"]:
        variants = family["variants"]
        cheapest_absolute = min(variants, key=lambda v: v["price"])
        priced = [(v, unit_price(v)) for v in variants]
        priced = [(v, u) for v, u in priced if u is not None]

        entry = {
            "parent_sku": family["parent_sku"],
            "gating": family["gating"],
            "from_price": cheapest_absolute["price"],
            "from_price_option": cheapest_absolute["option"],
            "variants": {v["option"]: {"sku": v["sku"], "price": v["price"],
                                       "qty": v["qty"],
                                       "unit_price": (unit_price(v) or [None])[0]}
                         for v in variants},
        }
        if priced:
            best_option, (best_unit, unit_basis) = min(priced, key=lambda p: p[1][0])
            entry["unit_basis"] = unit_basis
            entry["cheapest_by_unit_price"] = best_option["option"]
            entry["cheapest_unit_price"] = best_unit
            entry["card_price_misleads"] = (
                best_option["option"] != cheapest_absolute["option"])
        out_of_stock = [v["option"] for v in variants if v["qty"] == 0]
        if out_of_stock:
            entry["out_of_stock_options"] = out_of_stock
        families[family["key"]] = entry

    return {"families": families, "cross_listing": cross_listing(fixture)}


def cross_listing(fixture: dict) -> dict:
    """Where two families sell the same option, record which listing actually wins.

    This is the deployed-assistant failure in miniature: the listing with the lower
    'from' price is not the listing with the lower price for the size requested.
    """
    by_option: dict[str, list[dict]] = {}
    for family in fixture["families"]:
        for variant in family["variants"]:
            by_option.setdefault(variant["option"], []).append({
                "family": family["key"],
                "price": variant["price"],
                "from_price": min(v["price"] for v in family["variants"]),
            })

    contested = {}
    for option, offers in by_option.items():
        if len(offers) < 2:
            continue
        cheapest_for_option = min(offers, key=lambda o: o["price"])
        cheapest_by_card = min(offers, key=lambda o: o["from_price"])
        contested[option] = {
            "cheapest_listing": cheapest_for_option["family"],
            "cheapest_price": cheapest_for_option["price"],
            "listing_a_card_probe_would_pick": cheapest_by_card["family"],
            "card_probe_wrong": cheapest_for_option["family"] != cheapest_by_card["family"],
        }
    return contested


# ----------------------------------------------------------------------- commands


def expand_skus(fixture: dict) -> dict:
    """Give every variant a deterministic SKU derived from its parent and option."""
    for family in fixture["families"]:
        for variant in family["variants"]:
            variant.setdefault(
                "sku", f"{family['parent_sku']}-{slugify(variant['option']).upper()}")
    return fixture


def load_fixture(name: str | None = None) -> dict:
    """Load a fixture by filename, defaulting to the hand written families.

    Generated catalogues use the same schema, so seed, verify and teardown all work
    against either without change.
    """
    path = FIXTURES.parent / name if name else FIXTURES
    if not path.exists():
        available = sorted(f.name for f in FIXTURES.parent.glob("*.json"))
        raise SystemExit(f"no fixture named {path.name}. Available: {', '.join(available)}")
    return expand_skus(json.loads(path.read_text()))


def cmd_seed(m: Magento, args: argparse.Namespace) -> int:
    fixture = load_fixture(args.fixture)

    print("Attributes")
    attributes = {}
    for spec in fixture["attributes"]:
        attribute = ensure_attribute(m, spec, args.dry_run)
        ensure_attribute_in_set(m, spec["code"], fixture["attribute_set_id"],
                                args.dry_run)
        attributes[spec["code"]] = attribute

    print("\nFamilies")
    for family in fixture["families"]:
        print(f"  {family['key']} ({family['parent_sku']})")
        code = family["attribute"]
        labels = option_index(m, code, refresh=True) if not args.dry_run else {}

        child_skus, value_indexes = [], []
        for variant in family["variants"]:
            value_index = labels.get(variant["option"], "0")
            value_indexes.append(value_index)
            child_skus.append(
                ensure_child(m, family, variant, value_index, fixture, args.dry_run))

        ensure_parent(m, family, fixture, args.dry_run)
        ensure_configurable_links(m, family, attributes[code], value_indexes,
                                  child_skus, args.dry_run)

    if args.dry_run:
        print("\nDry run, nothing written.")
        return 0

    manifest = write_manifest(m, fixture)
    print(f"\nManifest: {manifest}")
    print("Reindex before the storefront reflects this:")
    print("  docker exec -it webarena-shopping php /var/www/magento2/bin/magento "
          "indexer:reindex")
    print("  docker exec -it webarena-shopping php /var/www/magento2/bin/magento "
          "cache:flush")
    return 0


def write_manifest(m: Magento, fixture: dict) -> pathlib.Path:
    MANIFESTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    path = MANIFESTS / f"{stamp}-gated-pricing.json"
    path.write_text(json.dumps({
        "seeded_at": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": m.base_url,
        "fixture": FIXTURES.name,
        "parent_skus": [f["parent_sku"] for f in fixture["families"]],
        "child_skus": [v["sku"] for f in fixture["families"] for v in f["variants"]],
        "ground_truth": analyse(fixture),
    }, indent=2) + "\n")
    return path


def cmd_verify(m: Magento, args: argparse.Namespace) -> int:
    """Read back what is actually in Magento and compare it against the fixture."""
    fixture = load_fixture(args.fixture)
    problems = 0

    for family in fixture["families"]:
        parent_sku = family["parent_sku"]
        parent = m.product(parent_sku)
        if parent is None:
            print(f"MISSING parent {parent_sku}")
            problems += 1
            continue
        if parent["type_id"] != "configurable":
            print(f"WRONG TYPE {parent_sku} is {parent['type_id']}")
            problems += 1

        children = m.get(f"/configurable-products/{parent_sku}/children")
        prices = {c["sku"]: c["price"] for c in children}
        expected = {v["sku"]: v["price"] for v in family["variants"]}

        if set(prices) != set(expected):
            print(f"CHILD MISMATCH {parent_sku}: "
                  f"missing {sorted(set(expected) - set(prices))}, "
                  f"unexpected {sorted(set(prices) - set(expected))}")
            problems += 1
        for sku, price in expected.items():
            if sku in prices and abs(prices[sku] - price) > 0.001:
                print(f"PRICE MISMATCH {sku}: {prices[sku]} != {price}")
                problems += 1

        distinct = len({round(p, 2) for p in prices.values()})
        print(f"{parent_sku}: {len(prices)} variants, {distinct} distinct prices")

    print("\nGround truth")
    print(json.dumps(analyse(fixture)["cross_listing"], indent=2))
    print("OK" if problems == 0 else f"{problems} problem(s)")
    return 1 if problems else 0


def cmd_teardown(m: Magento, args: argparse.Namespace) -> int:
    """Delete every product this script creates. Attributes are left in place."""
    fixture = load_fixture(args.fixture)
    skus = ([v["sku"] for f in fixture["families"] for v in f["variants"]]
            + [f["parent_sku"] for f in fixture["families"]])

    if not args.yes:
        print("Would delete:", *skus, sep="\n  ")
        print("\nRe-run with --yes to actually delete.")
        return 0

    for sku in skus:
        print(("deleted " if m.delete_product(sku) else "absent  ") + sku)
    return 0


def cmd_strip_notes(m: Magento, args: argparse.Namespace) -> int:
    """Blank the description of every parent in a fixture, in both store scopes.

    Undoes the note leak on products seeded before the seeder stopped writing notes.
    `seed` cannot do it, because it skips any parent that already exists. Both scopes
    are cleared because the original REST writes left a copy at store 0 and store 1, and
    clearing only the storefront row would leave the admin copy to resurface.
    """
    fixture = load_fixture(args.fixture)
    for family in fixture["families"]:
        sku = family["parent_sku"]
        if m.product(sku) is None:
            print(f"absent   {sku}")
            continue
        if args.dry_run:
            print(f"would blank description on {sku}")
            continue
        for store in ("all", "default"):
            m.put(f"/products/{sku}", {"product": {
                "sku": sku,
                "custom_attributes": [{"attribute_code": "description", "value": ""}],
            }}, store=store)
        print(f"blanked  {sku}")
    print("\nFlush the page cache before checking the storefront: "
          "docker exec webarena-shopping php /var/www/magento2/bin/magento cache:flush")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:7770")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin1234")
    sub = parser.add_subparsers(dest="command", required=True)

    # --fixture belongs to each subcommand rather than the parent, so it can be written
    # after the verb, which is where anyone would type it.
    fixture_help = "fixture filename under env/fixtures, defaults to gated_pricing.json"

    seed = sub.add_parser("seed", help="create the fixtures, idempotent")
    seed.add_argument("--fixture", help=fixture_help)
    seed.add_argument("--dry-run", action="store_true")
    seed.set_defaults(func=cmd_seed)

    verify = sub.add_parser("verify", help="read back and check against the fixture")
    verify.add_argument("--fixture", help=fixture_help)
    verify.set_defaults(func=cmd_verify, dry_run=False)

    teardown = sub.add_parser("teardown", help="delete every seeded product")
    teardown.add_argument("--fixture", help=fixture_help)
    teardown.add_argument("--yes", action="store_true")
    teardown.set_defaults(func=cmd_teardown, dry_run=False)

    strip = sub.add_parser("strip-notes",
                           help="blank descriptions that carry authoring notes")
    strip.add_argument("--fixture", help=fixture_help)
    strip.add_argument("--dry-run", action="store_true")
    strip.set_defaults(func=cmd_strip_notes)

    args = parser.parse_args(argv)
    m = Magento(base_url=args.base_url, username=args.user, password=args.password)
    try:
        return args.func(m, args)
    except MagentoError as exc:
        print(f"\nMagento rejected a call:\n  {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
