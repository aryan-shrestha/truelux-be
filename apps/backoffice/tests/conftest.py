from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.users.tests.factories import UserFactory


@pytest.fixture
def staff_client(db) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=UserFactory.create(is_staff=True))
    return client


def image_upload(*, image_format: str = "PNG", name: str = "photo.png") -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "#D8A47F").save(buffer, format=image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{image_format.lower()}")
