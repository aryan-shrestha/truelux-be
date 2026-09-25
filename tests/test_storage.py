import tempfile
from pathlib import Path

from django.conf import settings


def test_default_storage_is_filesystem_under_test_settings():
    assert settings.STORAGES["default"]["BACKEND"] == (
        "django.core.files.storage.FileSystemStorage"
    )


def test_media_root_is_temporary_in_tests():
    media_root = Path(settings.MEDIA_ROOT)

    assert media_root.is_relative_to(Path(tempfile.gettempdir()))
    assert not media_root.is_relative_to(settings.BASE_DIR)
