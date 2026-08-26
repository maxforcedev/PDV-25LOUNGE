import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    '.pdf': ('application/pdf', b'%PDF-'),
    '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
    '.jpg': ('image/jpeg', b'\xff\xd8\xff'),
    '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
}
SAFE_FILENAME = re.compile(r'^[^\x00-\x1f\\/]{1,120}$')


@deconstructible
class PrivatePurchaseStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name):
        raise ValueError('Arquivos privados nao possuem URL publica.')


def purchase_attachment_path(instance, filename):
    filename = Path(filename).name
    return f'purchases/{instance.company_id}/{uuid.uuid4().hex}_{filename}'


def purchase_attachment_download_name(field_file):
    stored_name = Path(field_file.name).name
    return stored_name.split('_', 1)[1] if '_' in stored_name else stored_name


def validate_purchase_attachment(upload):
    # New uploads are validated by the API and again before storage. Existing
    # migrated references may not have a local file to reopen during later saves.
    if getattr(upload, '_committed', False):
        return
    filename = Path(upload.name).name
    extension = Path(filename).suffix.lower()
    expected = ALLOWED_ATTACHMENT_TYPES.get(extension)
    if not SAFE_FILENAME.fullmatch(filename) or not expected:
        raise ValidationError('Use um nome seguro e um arquivo PDF, JPG ou PNG.')
    if getattr(upload, 'size', 0) <= 0 or upload.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError('O anexo deve ter entre 1 byte e 10 MB.')
    content_type = getattr(upload, 'content_type', None)
    if content_type and content_type != expected[0]:
        raise ValidationError('O tipo declarado do anexo nao corresponde a extensao.')
    position = upload.tell()
    header = upload.read(8)
    upload.seek(position)
    if not header.startswith(expected[1]):
        raise ValidationError('O conteudo do anexo nao corresponde ao tipo permitido.')
