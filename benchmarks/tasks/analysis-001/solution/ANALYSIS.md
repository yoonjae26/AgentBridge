# Repository analysis

## Modules in `shop`

- `shop.cart`: add_item, remove_item, item_count
- `shop.pricing`: apply_discount, round_price
- `shop.tax`: tax_for (plus the TAX_RATES table)
- `shop.cli`: main

## Entry point

The command-line entry point is `shop.cli.main` (run `python -m shop.cli`).

## Test coverage

Only `shop.cart` has tests (tests/test_cart.py).

- pricing: untested
- tax: untested
- cli: untested
