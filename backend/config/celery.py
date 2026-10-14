import logging
import os

from celery import Celery
from celery.signals import setup_logging, worker_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


@setup_logging.connect
def use_django_logging(**_: object) -> None:
    """Keep Celery from replacing the root logger: the worker logs JSON like Django (S16)."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@worker_init.connect
def check_llm_provider(**_: object) -> None:
    """Fail fast: the worker does not start when the selected provider is misconfigured."""
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    from agent.providers.factory import ProviderConfigError, check_provider_config

    try:
        check_provider_config(settings)
    except ProviderConfigError as exc:
        logger.critical("ImproperlyConfigured: %s", exc)
        # Celery logs and ignores normal exceptions from signal handlers; SystemExit stops it.
        raise SystemExit(f"ImproperlyConfigured: {exc}") from ImproperlyConfigured(str(exc))
