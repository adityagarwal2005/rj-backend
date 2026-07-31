import secrets

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


def backfill_referral_codes(apps, schema_editor):
    """Existing users predate the referral program - give each a real, unique
    code before the field below becomes UNIQUE, so the constraint doesn't
    choke on everyone sharing the blank default."""
    User = apps.get_model("users", "User")
    existing_codes = set()
    for user in User.objects.all():
        while True:
            code = secrets.token_hex(4).upper()
            if code not in existing_codes:
                existing_codes.add(code)
                break
        user.referral_code = code
        user.save(update_fields=["referral_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_order_abandoned_reminder_sent_at_and_more"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="referral_code",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="user",
            name="referral_reward_granted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="referred_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referrals_made",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="ReferralCredit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=8
                    ),
                ),
                ("is_used", models.BooleanField(default=False)),
                (
                    "used_on_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="orders.order",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="referral_credits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(backfill_referral_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="referral_code",
            field=models.CharField(blank=True, max_length=12, unique=True),
        ),
    ]
