from shop.cart import add_item, item_count


def test_add():
    assert item_count(add_item({}, "a", 2)) == 2
