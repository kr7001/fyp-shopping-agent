
## 2026-08-28
- WebArena-Verified shopping site running locally via Docker (amd64 under emulation on M-series)
- Catalogue: 104,368 products, all type_id = simple. No configurable products
- Product options exist (e.g. colour on cake topper SKU B09GFC1D5R) but are Magento custom options, so price does not vary by selection
- Implication: environment provides interaction-gated options but not per-variant pricing. Configurable products with divergent prices will need to be authored for the experiments


docker exec -it webarena-shopping php /var/www/magento2/bin/magento cache:flush