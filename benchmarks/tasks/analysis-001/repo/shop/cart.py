"""Shopping cart."""


def add_item(cart, sku, quantity=1):
    cart[sku] = cart.get(sku, 0) + quantity
    return cart


def remove_item(cart, sku):
    cart.pop(sku, None)
    return cart


def item_count(cart):
    return sum(cart.values())
