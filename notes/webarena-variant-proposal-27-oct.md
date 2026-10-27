Thank you for WebArena-Verified. I am a final-year student at the National University of Singapore studying how shopping agents handle prices and availability that become visible only after selecting a product variant. Would an **opt-in shopping environment extension and small task set** for this be useful to the project?

In the shopping instance I audited on 8 September 2026, the catalogue contained 104,368 products, no configurable products, and no non-zero price adjustments among its custom options. This is a finding about that instance, not a limitation of Magento or a claim about every WebArena distribution. The measurement and query are recorded in my [environment notes](https://github.com/kr7001/fyp-shopping-agent/blob/98988269fce34e504d72631f0b97fe15d53f8820/env/README.md).

A motivating task is: “Which seller has the cheapest size M that can actually be bought?” A listing's advertised “from” price may belong to another size; its parent-level stock status may also differ from size M's availability. Selecting the requested variant can therefore change the correct answer without any prompt-injection instruction.

The existing research prototype includes:

- A [Magento REST seeder](https://github.com/kr7001/fyp-shopping-agent/blob/98988269fce34e504d72631f0b97fe15d53f8820/env/seed_variants.py) for namespaced configurable products, with fixtures and manifests that separate added products from the original catalogue.
- A [seeded market generator](https://github.com/kr7001/fyp-shopping-agent/blob/98988269fce34e504d72631f0b97fe15d53f8820/env/generate_apparel.py) with distinct prices and absent, sold-out and buyable size states, plus answer keys computed from the fixtures.
- An [optional theme](https://github.com/kr7001/fyp-shopping-agent/blob/98988269fce34e504d72631f0b97fe15d53f8820/env/install_gated_theme.py), selected by a browser user-agent marker, that removes readable option surcharges and reveals the selected variant's price.
- A [browser checker](https://github.com/kr7001/fyp-shopping-agent/blob/98988269fce34e504d72631f0b97fe15d53f8820/env/check_market.py) that compares the rendered cards, menus, availability and selected prices against the fixture, including a control that detects the ordinary theme's price leakage.

There is an important observation-model limitation: the theme still sends an encoded price table to the browser. It studies what is initially readable in the rendered page; it does **not** make prices inaccessible to an agent that inspects and decodes page scripts. That capability would need to be stated explicitly in any benchmark task specification.

For an initial contribution, I propose one fixture and a few unambiguous retrieval tasks, such as cheapest buyable target size and a specified variant's availability. I would adapt them to WebArena-Verified's typed response schema and add evaluator tests. The current research task files have not yet been validated with your evaluator. Additional promotional-label or ambiguous-query conditions would be separate extensions.

Before a PR, the prototype needs packaging for a fresh pinned image, configurable endpoints/container names, namespaced setup and teardown, explicit store-configuration handling, and checks that existing tasks remain valid. Although the theme is user-agent selected, the catalogue additions and settings are shared, so I would keep this on a dedicated opt-in instance. Licence notices also need packaging review: one template is derived from Magento, and the research repository is not yet a separately licensed extension release.

Would you prefer an optional extension in this repository, or an independently packaged companion linked from the documentation? If this scope is useful, which task-ID conventions, evaluator expectations and environment checks would you want in a first PR?
