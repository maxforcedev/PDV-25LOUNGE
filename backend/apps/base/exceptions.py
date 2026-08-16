from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


CONSTRAINT_ERRORS = {
    'companies_company_cnpj_unique': {
        'cnpj': ['Ja existe uma empresa com este CNPJ.'],
    },
    'companies_company_trade_name_ci_unique': {
        'trade_name': ['Ja existe uma empresa com este nome fantasia.'],
    },
    'companies_company_legal_name_ci_unique': {
        'legal_name': ['Ja existe uma empresa com esta razao social.'],
    },
    'companies_branch_cnpj_unique': {
        'cnpj': ['Ja existe uma filial com este CNPJ.'],
    },
    'companies_branch_company_name_unique': {
        'name': ['Ja existe uma filial com este nome nesta empresa.'],
    },
    'products_category_company_name_ci_unique': {
        'name': ['Ja existe uma categoria com este nome nesta empresa.'],
    },
    'products_product_company_internal_code_ci_unique': {
        'internal_code': ['Ja existe um produto com este codigo nesta empresa.'],
    },
    'products_product_company_barcode_ci_unique': {
        'barcode': ['Ja existe um produto com este codigo de barras nesta empresa.'],
    },
    'cash_register_branch_name_ci_unique': {
        'name': ['Ja existe um caixa com este nome nesta filial.'],
    },
    'cash_session_one_open_per_register': {
        'cash_register': ['Este caixa ja possui uma sessao aberta.'],
    },
}


class InternalContractError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'O servidor produziu uma resposta em formato invalido.'
    default_code = 'invalid_internal_contract'


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            data = exc.message_dict
        else:
            data = {'non_field_errors': exc.messages}
        return Response(data, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, IntegrityError):
        cause = exc.__cause__
        diagnostics = getattr(cause, 'diag', None)
        constraint_name = getattr(diagnostics, 'constraint_name', None)
        data = CONSTRAINT_ERRORS.get(
            constraint_name,
            {'detail': 'Nao foi possivel salvar porque os dados entram em conflito.'},
        )
        return Response(data, status=status.HTTP_409_CONFLICT)

    return Response(
        {'detail': 'O servidor encontrou um problema inesperado.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
