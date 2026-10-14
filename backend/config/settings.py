"""Django settings. Every value comes from environment variables (see docs/spec.md S14)."""

from pathlib import Path

import environ

from agent.guardrails import AgentLimits
from config.logging import logging_config

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "backend"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "core",
    "videos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

# Uploads always go to a temp file on disk, so ffprobe can read them (spec S4.2).
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.TemporaryFileUploadHandler"]
MAX_UPLOAD_BYTES = int(env.float("MAX_UPLOAD_MB", default=200) * 1024 * 1024)
MAX_VIDEO_SECONDS = env.int("MAX_VIDEO_SECONDS", default=130)

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# LLM provider. The model name only comes from env (<PROVIDER>_MODEL, e.g. GEMINI_MODEL).
LLM_PROVIDER = env("LLM_PROVIDER", default="gemini")
LLM_MODEL = env(f"{LLM_PROVIDER.upper()}_MODEL", default="")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="")
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=60)
LLM_MAX_RETRIES = env.int("LLM_MAX_RETRIES", default=3)
LLM_MAX_REQUESTS_PER_MINUTE = env.int("LLM_MAX_REQUESTS_PER_MINUTE", default=8)

# Analysis run and frame extraction (spec S5, S6.4, S9).
AGENT_RUN_TIMEOUT_SECONDS = env.int("AGENT_RUN_TIMEOUT_SECONDS", default=600)
SURVEY_INTERVAL_S = env.float("SURVEY_INTERVAL_S", default=2)
SCENE_THRESHOLD = env.float("SCENE_THRESHOLD", default=0.4)
FRAME_MAX_SIDE = env.int("FRAME_MAX_SIDE", default=768)
INSPECT_FPS = env.float("INSPECT_FPS", default=2)
WINDOW_PADDING_S = env.float("WINDOW_PADDING_S", default=2)

# Agent (spec S6, S7). Event types file paths are relative to the backend directory.
EVENT_TYPES_FILE = BASE_DIR / env("EVENT_TYPES_FILE", default="agent/event_types.yaml")
FRAMES_PER_CALL = env.int("FRAMES_PER_CALL", default=12)
CONFIDENCE_THRESHOLD = env.float("CONFIDENCE_THRESHOLD", default=0.6)
LLM_INPUT_PRICE_PER_MTOK = env.float("LLM_INPUT_PRICE_PER_MTOK", default=0)
LLM_OUTPUT_PRICE_PER_MTOK = env.float("LLM_OUTPUT_PRICE_PER_MTOK", default=0)
MOCK_LATENCY_MS = env.int("MOCK_LATENCY_MS", default=300)
AGENT = AgentLimits(
    max_iterations=env.int("AGENT_MAX_ITERATIONS", default=3),
    max_frames=env.int("AGENT_MAX_FRAMES", default=120),
    max_tokens=env.int("AGENT_MAX_TOKENS", default=200000),
    max_cost_usd=env.float("AGENT_MAX_COST_USD", default=0.50),
    max_llm_calls=env.int("AGENT_MAX_LLM_CALLS", default=20),
    report_reserve_tokens=env.int("AGENT_REPORT_RESERVE_TOKENS", default=4000),
)

LOG_LEVEL = env("LOG_LEVEL", default="INFO")

# JSON logs on stdout with context and secret redaction (spec S16). Celery uses it too.
LOGGING = logging_config(LOG_LEVEL)

# Every variable documented in .env.example (spec S14). A test keeps the two lists equal.
ENV_VARS = [
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "DJANGO_ALLOWED_HOSTS",
    "DATABASE_URL",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "CORS_ALLOWED_ORIGINS",
    "MEDIA_ROOT",
    "LOG_LEVEL",
    "MAX_UPLOAD_MB",
    "MAX_VIDEO_SECONDS",
    "EVENT_TYPES_FILE",
    "LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "LLM_INPUT_PRICE_PER_MTOK",
    "LLM_OUTPUT_PRICE_PER_MTOK",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_MAX_REQUESTS_PER_MINUTE",
    "AGENT_MAX_ITERATIONS",
    "AGENT_MAX_FRAMES",
    "AGENT_MAX_TOKENS",
    "AGENT_MAX_COST_USD",
    "AGENT_MAX_LLM_CALLS",
    "AGENT_REPORT_RESERVE_TOKENS",
    "AGENT_RUN_TIMEOUT_SECONDS",
    "SURVEY_INTERVAL_S",
    "SCENE_THRESHOLD",
    "INSPECT_FPS",
    "WINDOW_PADDING_S",
    "FRAMES_PER_CALL",
    "FRAME_MAX_SIDE",
    "CONFIDENCE_THRESHOLD",
    "MOCK_LATENCY_MS",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_MAX_UPLOAD_MB",
]
