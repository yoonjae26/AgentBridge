"""List pagination helpers."""


def paginate(items, page, per_page=10):
    """Return the items on a 1-indexed page."""
    if page < 1:
        raise ValueError("page numbers start at 1")
    start = (page - 1) * per_page
    return items[start : start + per_page]


def page_count(total, per_page=10):
    """Number of pages needed for ``total`` items."""
    return -(-total // per_page)
