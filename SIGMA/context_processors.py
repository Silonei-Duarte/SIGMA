from django.conf import settings


def application_name(request):
    return {
        "APPLICATION_NAME": getattr(settings, "APPLICATION_NAME", ""),
    }
