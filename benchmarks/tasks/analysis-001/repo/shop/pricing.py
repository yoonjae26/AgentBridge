"""Prices and discounts."""


def apply_discount(price, percent):
    return price * (100 - percent) / 100


def round_price(price):
    return round(price, 2)
