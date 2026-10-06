import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError


MAX_BRANDING_ASSET_SIZE = 2 * 1024 * 1024
SAFE_FILENAME = re.compile(r'^[^\x00-\x1f\\/]{1,120}$')
IMAGE_TYPES = {
    '.png': ('image/png', 'PNG'),
    '.jpg': ('image/jpeg', 'JPEG'),
    '.jpeg': ('image/jpeg', 'JPEG'),
    '.webp': ('image/webp', 'WEBP'),
}
FAVICON_TYPES = {**IMAGE_TYPES, '.ico': ('image/x-icon', 'ICO')}


@deconstructible
class PrivateBrandingStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name):
        raise ValueError('Assets de branding nao possuem URL publica direta.')


def branding_asset_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f'branding/{instance.pk or "pending"}/{uuid.uuid4().hex}{suffix}'


def _validate_branding_asset(upload, allowed_types, label):
    if getattr(upload, '_committed', False):
        return
    filename = Path(upload.name).name
    suffix = Path(filename).suffix.lower()
    expected = allowed_types.get(suffix)
    if not SAFE_FILENAME.fullmatch(filename) or not expected:
        formats = 'PNG, JPG, JPEG, WEBP ou ICO' if '.ico' in allowed_types else 'PNG, JPG, JPEG ou WEBP'
        raise ValidationError(f'Envie {label} {formats} com nome seguro.')
    if getattr(upload, 'size', 0) <= 0 or upload.size > MAX_BRANDING_ASSET_SIZE:
        raise ValidationError(f'O {label} deve ter entre 1 byte e 2 MB.')
    content_type = getattr(upload, 'content_type', None)
    allowed_content_types = {value[0] for value in allowed_types.values()}
    if content_type and content_type not in allowed_content_types:
        raise ValidationError(f'O tipo declarado do {label} nao e permitido.')
    position = upload.tell()
    try:
        with Image.open(upload) as image:
            if image.format != expected[1]:
                raise ValidationError(f'O conteudo do {label} nao corresponde ao tipo permitido.')
            image.verify()
        upload.seek(position)
        with Image.open(upload) as image:
            image.load()
    except (OSError, SyntaxError, UnidentifiedImageError):
        raise ValidationError(f'O conteudo do {label} nao corresponde ao tipo permitido.')
    finally:
        upload.seek(position)


def validate_branding_image(upload):
    _validate_branding_asset(upload, IMAGE_TYPES, 'arquivo')


def validate_branding_favicon(upload):
    _validate_branding_asset(upload, FAVICON_TYPES, 'favicon')
