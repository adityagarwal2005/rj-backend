#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    # `manage.py test` defaults to config.settings.test rather than
    # inheriting the ambient DJANGO_SETTINGS_MODULE. Without this, a plain
    # `manage.py test` picked up DATABASE_URL from .env - which points at
    # the production Supabase Postgres - and ran the whole suite against
    # the live database server over the network: slow, flaky, and doing
    # CREATE/DROP DATABASE against production. See config/settings/test.py.
    #
    # Still overridable: an explicit --settings flag on the command line, or
    # a DJANGO_SETTINGS_MODULE already exported in the environment, both win.
    is_test = len(sys.argv) > 1 and sys.argv[1] == "test"
    has_explicit_settings = any(arg.startswith("--settings") for arg in sys.argv)

    if is_test and not has_explicit_settings and "DJANGO_SETTINGS_MODULE" not in os.environ:
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
