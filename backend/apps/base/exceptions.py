import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


CONSTRAINT_ERRORS = {
    'companies_company_cnpj_unique': {
        'cnpj': ['Já existe uma empresa com este CNPJ.'],
    },
    'companies_user_company_one_owner': {
        'is_owner': ['A empresa já possui um proprietário.'],
    },
    'companies_user_company_owner_active': {
        'is_active': ['O acesso do proprietário deve permanecer ativo.'],
    },
    'companies_branch_cnpj_unique': {
        'cnpj': ['Já existe uma filial com este CNPJ.'],
    },
    'companies_branch_company_name_unique': {
        'name': ['Já existe uma filial com este nome nesta empresa.'],
    },
    'products_category_company_name_ci_unique': {
        'name': ['Já existe uma categoria com este nome nesta empresa.'],
    },
    'products_product_company_internal_code_ci_unique': {
        'internal_code': ['Já existe um produto com este código nesta empresa.'],
    },
    'products_product_company_barcode_ci_unique': {
        'barcode': ['Já existe um produto com este código de barras nesta empresa.'],
    },
    'cash_register_branch_name_ci_unique': {
        'name': ['Já existe um caixa com este nome nesta filial.'],
    },
    'cash_session_one_open_per_register': {
        'cash_register': ['Este caixa já possui uma sessão aberta.'],
    },
}

logger = logging.getLogger(__name__)


class InternalContractError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'O servidor produziu uma resposta em formato inválido.'
    default_code = 'invalid_internal_contract'


class DomainValidationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, *, code, message, details=None):
        self.payload = {
            'code': code,
            'message': message,
            'details': details or {},
        }
        super().__init__(self.payload)


def api_exception_handler(exc, context):
    if isinstance(exc, DomainValidationError):
        return Response(exc.payload, status=exc.status_code)
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
            {'detail': 'Não foi possível salvar porque os dados entram em conflito.'},
        )
        return Response(data, status=status.HTTP_409_CONFLICT)

    logger.exception('Unhandled API exception in %s', context.get('view').__class__.__name__)
    return Response(
        {'detail': 'Não foi possível concluir a operação devido a um erro interno. Tente novamente.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
