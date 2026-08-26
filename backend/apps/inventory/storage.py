import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


MAX_LOSS_ATTACHMENT_SIZE = 10 * 1024 * 1024
LOSS_IMAGE_TYPES = {
    '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
    '.jpg': ('image/jpeg', b'\xff\xd8\xff'),
    '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
}
SAFE_FILENAME = re.compile(r'^[^\x00-\x1f\\/]{1,120}$')


@deconstructible
class PrivateLossStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name):
        raise ValueError('Arquivos privados nao possuem URL publica.')


def loss_attachment_path(instance, filename):
    return f'losses/{instance.company_id}/{uuid.uuid4().hex}_{Path(filename).name}'


def loss_attachment_download_name(field_file):
    stored_name = Path(field_file.name).name
    return stored_name.split('_', 1)[1] if '_' in stored_name else stored_name


def validate_loss_attachment(upload):
    if getattr(upload, '_committed', False):
        return
    filename = Path(upload.name).name
    expected = LOSS_IMAGE_TYPES.get(Path(filename).suffix.lower())
    if not SAFE_FILENAME.fullmatch(filename) or not expected:
        raise ValidationError('Envie uma foto PNG, JPG ou JPEG com nome seguro.')
    if getattr(upload, 'size', 0) <= 0 or upload.size > MAX_LOSS_ATTACHMENT_SIZE:
        raise ValidationError('A foto deve ter entre 1 byte e 10 MB.')
    content_type = getattr(upload, 'content_type', None)
    if content_type and content_type != expected[0]:
        raise ValidationError('O tipo declarado da foto nao corresponde a extensao.')
    position = upload.tell()
    header = upload.read(8)
    upload.seek(position)
    if not header.startswith(expected[1]):
        raise ValidationError('O conteudo da foto nao corresponde ao tipo permitido.')
