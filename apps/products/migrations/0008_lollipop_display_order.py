from django.db import migrations


def push_lollipops_behind_flagship(apps, schema_editor):
    """
    Kunafa Chocolate stays at the default display_order=0 (pinned first);
    push the newer lollipops to 1 so they sort after it instead of ahead of
    it on -created_at.
    """
    Product = apps.get_model("products", "Product")
    Product.objects.filter(slug__in=["kunafa-lollipop", "biscoff-lollipop"]).update(display_order=1)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0007_product_display_order"),
    ]

    operations = [
        migrations.RunPython(push_lollipops_behind_flagship, reverse_noop),
    ]
