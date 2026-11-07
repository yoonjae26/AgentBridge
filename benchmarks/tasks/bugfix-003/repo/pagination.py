"""List pagination helpers."""


def paginate(items, page, per_page=10):
    """Return the items on a 1-indexed page."""
    start = page * per_page
    return items[start : start + per_page]


def page_count(total, per_page=10):
    """Number of pages needed for ``total`` items."""
    return total // per_page
