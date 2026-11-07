"""Sales tax."""

TAX_RATES = {"standard": 0.2, "reduced": 0.05}


def tax_for(amount, category="standard"):
    return amount * TAX_RATES[category]
