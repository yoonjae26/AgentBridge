"""Command line interface."""

import sys

from shop.cart import add_item, item_count


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    cart = {}
    for sku in args:
        add_item(cart, sku)
    print(item_count(cart))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
