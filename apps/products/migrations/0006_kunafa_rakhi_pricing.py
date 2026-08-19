from decimal import Decimal

from django.db import migrations


def set_rakhi_pricing(apps, schema_editor):
    """
    One-time Rakhi-special repricing for the (only) live product: 120 for
    one bar, 110/bar once buying 2 or more. Also clears any stale flat
    discount_price so it can't silently override the new base price via
    effective_price (see Product.price_for_quantity).
    """
    Product = apps.get_model("products", "Product")
    Product.objects.filter(slug="kunafa-chocolate").update(
        price=Decimal("120.00"),
        discount_price=None,
        bulk_price=Decimal("110.00"),
        bulk_min_quantity=2,
    )


def reverse_noop(apps, schema_editor):
    # Deliberately no-op: reversing to the old flat 200 price isn't a
    # meaningful "undo" of a real pricing decision - if this needs
    # reverting, do it explicitly via the admin instead.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0005_product_bulk_min_quantity_product_bulk_price"),
    ]

    operations = [
        migrations.RunPython(set_rakhi_pricing, reverse_noop),
    ]
