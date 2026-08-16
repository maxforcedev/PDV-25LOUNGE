import re

from django.core.exceptions import ValidationError


ALLOWED_CNPJ_CHARACTERS = re.compile(r'^[0-9.\-/\s]+$')


def normalize_cnpj(value):
    if value in (None, ''):
        return None
    if not ALLOWED_CNPJ_CHARACTERS.fullmatch(value):
        raise ValidationError('Informe um CNPJ contendo apenas digitos e pontuacao.')
    return re.sub(r'[.\-/\s]', '', value)


def validate_cnpj(value):
    if value in (None, ''):
        return

    digits = normalize_cnpj(value)
    if len(digits) != 14 or not digits.isascii() or not digits.isdigit():
        raise ValidationError('O CNPJ deve conter 14 digitos.')
    if len(set(digits)) == 1:
        raise ValidationError('Informe um CNPJ valido.')

    def calculate_digit(numbers, weights):
        total = sum(int(number) * weight for number, weight in zip(numbers, weights))
        remainder = total % 11
        return '0' if remainder < 2 else str(11 - remainder)

    first = calculate_digit(digits[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    second = calculate_digit(
        digits[:12] + first,
        (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
    )
    if digits[-2:] != first + second:
        raise ValidationError('Informe um CNPJ valido.')
