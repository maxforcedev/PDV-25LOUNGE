import re

from django.core.exceptions import ValidationError


def normalize_tax_id(value):
    if value is None or value == '':
        return None
    digits = re.sub(r'\D', '', str(value))
    if not digits:
        raise ValidationError('Informe um CPF ou CNPJ válido.')
    return digits or None


def _cpf_is_valid(value):
    if len(value) != 11 or len(set(value)) == 1:
        return False
    numbers = [int(digit) for digit in value]
    for length in (9, 10):
        total = sum(numbers[index] * (length + 1 - index) for index in range(length))
        remainder = total % 11
        check_digit = 0 if remainder < 2 else 11 - remainder
        if numbers[length] != check_digit:
            return False
    return True


def _cnpj_is_valid(value):
    if len(value) != 14 or len(set(value)) == 1:
        return False
    numbers = [int(digit) for digit in value]
    for length, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(numbers[index] * weights[index] for index in range(length)) % 11
        check_digit = 0 if remainder < 2 else 11 - remainder
        if numbers[length] != check_digit:
            return False
    return True


def validate_tax_id(value):
    value = normalize_tax_id(value)
    if value is None:
        return
    if len(value) == 11 and _cpf_is_valid(value):
        return
    if len(value) == 14 and _cnpj_is_valid(value):
        return
    raise ValidationError('Informe um CPF ou CNPJ válido.')
