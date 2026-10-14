import pytest
from django.db import IntegrityError, transaction

from tests.videos.factories import create_event, create_run, create_video
from videos.models import RunStatus


@pytest.mark.django_db
def test_only_one_active_run_per_video() -> None:
    video = create_video()
    create_run(video, status=RunStatus.QUEUED)

    with pytest.raises(IntegrityError), transaction.atomic():
        create_run(video, status=RunStatus.RUNNING)

    # Finished runs do not count as active.
    create_run(video, status=RunStatus.SUCCEEDED)
    create_run(video, status=RunStatus.FAILED)


@pytest.mark.django_db
def test_event_confidence_must_be_between_0_and_1() -> None:
    run = create_run(create_video())

    with pytest.raises(IntegrityError), transaction.atomic():
        create_event(run, confidence=1.5)
