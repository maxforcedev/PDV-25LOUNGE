import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024
PRODUCT_IMAGE_TYPES = {
    '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
    '.jpg': ('image/jpeg', b'\xff\xd8\xff'),
    '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
    '.webp': ('image/webp', b'RIFF'),
}
SAFE_FILENAME = re.compile(r'^[^\x00-\x1f\\/]{1,120}$')


@deconstructible
class PrivateProductImageStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name):
        raise ValueError('Fotos de produtos privadas nao possuem URL publica.')


def product_image_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f'product-images/{instance.company_id}/{uuid.uuid4().hex}{suffix}'


def validate_product_image(upload):
    if getattr(upload, '_committed', False):
        return
    filename = Path(upload.name).name
    suffix = Path(filename).suffix.lower()
    expected = PRODUCT_IMAGE_TYPES.get(suffix)
    if not SAFE_FILENAME.fullmatch(filename) or not expected:
        raise ValidationError('Envie uma foto PNG, JPG, JPEG ou WEBP com nome seguro.')
    if getattr(upload, 'size', 0) <= 0 or upload.size > MAX_PRODUCT_IMAGE_SIZE:
        raise ValidationError('A foto deve ter entre 1 byte e 5 MB.')
    content_type = getattr(upload, 'content_type', None)
    if content_type and content_type != expected[0]:
        raise ValidationError('O tipo declarado da foto nao corresponde a extensao.')
    position = upload.tell()
    header = upload.read(12)
    upload.seek(position)
    valid = header.startswith(expected[1])
    if suffix == '.webp':
        valid = valid and header[8:12] == b'WEBP'
    if not valid:
        raise ValidationError('O conteudo da foto nao corresponde ao tipo permitido.')
