#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

from django.contrib.auth.management import create_permissions
from django.db.models.signals import post_migrate


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SIGMA.settings")

    # desativa criação automática de permissões padrão
    try:
        post_migrate.disconnect(
            create_permissions, dispatch_uid="django.contrib.auth.management.create_permissions"
        )
    except Exception:
        pass

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
