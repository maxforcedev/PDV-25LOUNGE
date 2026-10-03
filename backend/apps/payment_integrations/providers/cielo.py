"""Cielo Smart Deep Link adapter.

The generated URI embeds credentials in Base64. It is intentionally returned only
to a future client launcher and must never be logged, audited, or persisted.
"""

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlunsplit

from django.conf import settings

from apps.payment_integrations.models import (
    PaymentAttemptStatus, PaymentProviderIntegrationType,
)
from apps.payment_integrations.services import PaymentIntegrationConflict
from apps.sales.models import PaymentMethodCode

from .base import (
    PaymentProviderAdapter, ProviderLaunchCommand, ProviderPaymentResult,
    ProviderReversalResult,
)
from .registry import register_adapter


_INSTALLMENT_CODES = {
    'store': 'CREDITO_PARCELADO_LOJA',
    'administrator': 'CREDITO_PARCELADO_ADM',
    'bank': 'CREDITO_PARCELADO_BNCO',
}
_ERROR_STATUS = {
    '1': (PaymentAttemptStatus.CANCELLED, 'Pagamento cancelado pelo usuário.'),
    '2': (PaymentAttemptStatus.ERROR, 'Erro genérico informado pela Cielo.'),
    '3': (PaymentAttemptStatus.ERROR, 'Erro no pagamento informado pela Cielo.'),
    '4': (PaymentAttemptStatus.ERROR, 'Erro de autenticação informado pela Cielo.'),
}
_PAN_LIKE = re.compile(r'\d')
_SENSITIVE_TEXT = re.compile(
    r'\b(access[_ -]?token|client[_ -]?id|authorization|secret|password)\s*[:=]\s*\S+',
    re.IGNORECASE,
)
_MERCHANT_CODE = re.compile(r'\d{16}\Z')
_BASE64_TRANSPORT_WHITESPACE = re.compile(r'[\t\n\r\f\v ]+')
logger = logging.getLogger('payment_integrations.cielo')


@dataclass(frozen=True)
class CieloCredentials:
    client_id: str
    access_token: str

    def __repr__(self):
        return f'{type(self).__name__}(redacted=True)'


def get_cielo_credentials():
    client_id = getattr(settings, 'CIELO_SMART_CLIENT_ID', None)
    access_token = getattr(settings, 'CIELO_SMART_ACCESS_TOKEN', None)
    if not client_id or not access_token:
        raise PaymentIntegrationConflict(
            'cielo_credentials_missing',
            'As credenciais da Cielo Smart não estão configuradas.',
        )
    return CieloCredentials(client_id=client_id, access_token=access_token)


def amount_to_cents(amount):
    if isinstance(amount, (bool, float)):
        raise PaymentIntegrationConflict('cielo_amount_invalid', 'O valor deve ser um Decimal exato.')
    try:
        decimal_amount = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PaymentIntegrationConflict('cielo_amount_invalid', 'O valor é inválido.') from error
    if not decimal_amount.is_finite() or decimal_amount <= 0 or decimal_amount.as_tuple().exponent < -2:
        raise PaymentIntegrationConflict('cielo_amount_invalid', 'O valor deve ser positivo e possuir no máximo duas casas.')
    cents = decimal_amount * 100
    if cents != cents.to_integral_value():
        raise PaymentIntegrationConflict('cielo_amount_invalid', 'O valor não pode sofrer arredondamento.')
    return int(cents)


def _reference(attempt):
    return f'CORE-{attempt.id}'


def _safe_text(value, *, limit=500):
    text = _SENSITIVE_TEXT.sub(r'\1=[redacted]', ' '.join(str(value or '').split()))
    return text[:limit]


def _safe_mask(value):
    text = _safe_text(value, limit=32)
    digits = ''.join(_PAN_LIKE.findall(text))
    # A full PAN is neither a mask nor a token and must never enter the ledger.
    return '' if len(digits) >= 12 else text


def _unknown(reason, *, metadata=None):
    safe_metadata = {'provider': 'cielo', 'result': 'unknown', **(metadata or {})}
    return ProviderPaymentResult(
        status=PaymentAttemptStatus.UNKNOWN,
        result_data={
            'provider_status': 'unknown',
            'provider_message': _safe_text(reason),
        },
        safe_metadata=safe_metadata,
    )


def _error_result(code, reason):
    status, fallback_message = _ERROR_STATUS[code]
    message = _safe_text(reason) or fallback_message
    provider_status = 'cancelled' if status == PaymentAttemptStatus.CANCELLED else 'error'
    return ProviderPaymentResult(
        status=status,
        result_data={
            'provider_status': provider_status,
            'provider_status_code': code,
            'provider_message': message,
        },
        safe_metadata={
            'provider': 'cielo', 'provider_status': provider_status,
            'provider_status_code': code, 'provider_message': message,
        },
    )


@register_adapter
class CieloSmartAdapter(PaymentProviderAdapter):
    provider_code = 'cielo'

    def _assert_cielo_attempt(self, attempt):
        if attempt.provider_connection.provider.code != self.provider_code:
            raise PaymentIntegrationConflict(
                'cielo_connection_invalid', 'A conexão não pertence ao provider Cielo Smart.',
            )

    def _connection_configuration(self, attempt):
        # Launch uses the current operational connection; callback parsing below
        # intentionally does not depend on this mutable administrative state.
        connection = attempt.provider_connection
        manager = getattr(type(connection), 'objects', None)
        if manager is not None and attempt.provider_connection_id:
            connection = manager.select_related('provider').get(pk=attempt.provider_connection_id)
        provider = connection.provider
        self._assert_cielo_attempt(attempt)
        if provider.integration_type != PaymentProviderIntegrationType.LOCAL_DEEP_LINK:
            raise PaymentIntegrationConflict(
                'cielo_connection_invalid', 'A conexão não pertence ao provider Cielo Smart.',
            )
        configuration = connection.configuration or {}
        if not isinstance(configuration, dict) or set(configuration) - {
            'merchant_code', 'credit_installment_mode',
        }:
            raise PaymentIntegrationConflict(
                'cielo_configuration_invalid', 'A configuração da conexão Cielo é inválida.',
            )
        merchant_code = configuration.get('merchant_code')
        if merchant_code is not None and (
            not isinstance(merchant_code, str)
            or not _MERCHANT_CODE.fullmatch(merchant_code)
        ):
            raise PaymentIntegrationConflict(
                'cielo_configuration_invalid', 'merchant_code deve possuir exatamente 16 dígitos.',
            )
        mode = configuration.get('credit_installment_mode', 'store')
        if mode not in _INSTALLMENT_CODES:
            raise PaymentIntegrationConflict(
                'cielo_configuration_invalid', 'credit_installment_mode é inválido.',
            )
        return _safe_text(merchant_code, limit=150) if merchant_code is not None else None, mode

    def _payment_code(self, attempt, installments, installment_mode):
        if isinstance(installments, (bool, float)):
            raise PaymentIntegrationConflict('cielo_installments_invalid', 'Parcelas inválidas.')
        try:
            installments = int(installments or 1)
        except (TypeError, ValueError) as error:
            raise PaymentIntegrationConflict('cielo_installments_invalid', 'Parcelas inválidas.') from error
        if installments < 1:
            installments = 1
        method = attempt.intent.payment_method.code
        if method == PaymentMethodCode.CASH:
            raise PaymentIntegrationConflict(
                'cielo_payment_method_unsupported', 'Dinheiro não pode ser enviado à Cielo.',
            )
        if method == PaymentMethodCode.DEBIT_CARD:
            return 'DEBITO_AVISTA', 0
        if method == PaymentMethodCode.CREDIT_CARD:
            return (
                ('CREDITO_AVISTA', 0)
                if installments == 1 else (_INSTALLMENT_CODES[installment_mode], installments)
            )
        if method == PaymentMethodCode.PIX:
            return 'PIX', 0
        if method == PaymentMethodCode.FOOD_VOUCHER:
            return 'VOUCHER_ALIMENTACAO', 0
        if method == PaymentMethodCode.MEAL_VOUCHER:
            return 'VOUCHER_REFEICAO', 0
        raise PaymentIntegrationConflict(
            'cielo_payment_method_unsupported', 'A forma de pagamento não é suportada pela Cielo.',
        )

    @staticmethod
    def _validate_items(items):
        if not isinstance(items, list) or not items:
            raise PaymentIntegrationConflict('cielo_items_invalid', 'A Cielo exige ao menos um item.')
        required = {'name', 'quantity', 'sku', 'unitOfMeasure', 'unitPrice'}
        for item in items:
            if not isinstance(item, dict) or required - set(item):
                raise PaymentIntegrationConflict('cielo_items_invalid', 'Item Cielo incompleto.')
            if not _safe_text(item['name']) or not _safe_text(item['sku']) or not _safe_text(item['unitOfMeasure']):
                raise PaymentIntegrationConflict('cielo_items_invalid', 'Item Cielo inválido.')
            if isinstance(item['quantity'], (bool, float)) or isinstance(item['unitPrice'], (bool, float)):
                raise PaymentIntegrationConflict('cielo_items_invalid', 'Item Cielo deve usar valores exatos.')
            try:
                if Decimal(item['quantity']) <= 0 or int(item['unitPrice']) <= 0:
                    raise ValueError
                if int(item['unitPrice']) != item['unitPrice']:
                    raise ValueError
                json.dumps(item, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
            except (InvalidOperation, TypeError, ValueError) as error:
                raise PaymentIntegrationConflict('cielo_items_invalid', 'Item Cielo inválido.') from error

    def build_payment_command(self, *, attempt, callback_url, items, installments=1):
        merchant_code, installment_mode = self._connection_configuration(attempt)
        payment_code, cielo_installments = self._payment_code(attempt, installments, installment_mode)
        self._validate_items(items)
        credentials = get_cielo_credentials()
        amount_cents = amount_to_cents(attempt.amount)
        reference = _reference(attempt)
        request = {
            'clientID': credentials.client_id,
            'accessToken': credentials.access_token,
            'reference': reference,
            'installments': cielo_installments,
            'items': items,
            'paymentCode': payment_code,
            'value': str(amount_cents),
        }
        if merchant_code:
            request['merchantCode'] = merchant_code
        encoded_request = base64.b64encode(json.dumps(
            request, ensure_ascii=True, separators=(',', ':'), sort_keys=True,
        ).encode('utf-8')).decode('ascii')
        uri = urlunsplit(('lio', 'payment', '', urlencode({
            'request': encoded_request, 'urlCallback': callback_url,
        }), ''))
        return ProviderLaunchCommand(
            operation='payment', uri=uri,
            safe_metadata={
                'provider': self.provider_code,
                'payment_code': payment_code,
                'installments': cielo_installments,
                'reference': reference,
                'amount_cents': amount_cents,
                'merchant_code_present': bool(merchant_code),
            },
        )

    def parse_payment_callback(self, *, attempt, response, responsecode=None):
        # Historical callbacks must not be affected by later administrative changes.
        self._assert_cielo_attempt(attempt)
        error_code = str(responsecode).strip() if responsecode not in (None, '') else ''
        try:
            normalized_response = _BASE64_TRANSPORT_WHITESPACE.sub('', str(response or ''))
            raw = base64.b64decode(normalized_response, validate=True)
            payload = json.loads(raw.decode('utf-8'))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            logger.info(
                'cielo_callback_decode_failed attempt_id=%s response_present=%s response_length=%s',
                attempt.pk, bool(response), len(str(response or '')),
            )
            if error_code in _ERROR_STATUS:
                return _error_result(error_code, '')
            return _unknown('Resposta Cielo não comprovável.')
        if not isinstance(payload, dict):
            return _unknown('Estrutura da resposta Cielo é inválida.')
        payload_error_code = str(payload.get('code')).strip() if payload.get('code') is not None else ''
        if payload_error_code in _ERROR_STATUS and 'reason' in payload:
            return _error_result(payload_error_code, payload.get('reason'))
        order = payload
        reference = order.get('reference')
        expected_reference = _reference(attempt)
        if reference not in (None, '') and str(reference) != expected_reference:
            return _unknown('A referência Cielo não pertence a esta tentativa.')
        payments = order.get('payments')
        if not isinstance(payments, list):
            return _unknown('A resposta Cielo não possui pagamentos.')
        expected_cents = amount_to_cents(attempt.amount)
        candidates = []
        for payment in payments:
            if not isinstance(payment, dict):
                continue
            fields = payment.get('paymentFields')
            if not isinstance(fields, dict):
                continue
            try:
                raw_amount = payment.get('amount')
                if isinstance(raw_amount, (bool, float)):
                    continue
                amount = int(raw_amount)
                if str(amount) != str(raw_amount):
                    continue
                status_code = str(fields.get('statusCode'))
            except (TypeError, ValueError):
                continue
            if amount == expected_cents and status_code in {'0', '1', '2'}:
                candidates.append((payment, fields, status_code))
        if len(candidates) != 1:
            return _unknown('Não foi possível identificar unicamente o pagamento Cielo.')
        payment, fields, status_code = candidates[0]
        transaction_id = _safe_text(fields.get('paymentTransactionId'), limit=150)
        if status_code in {'0', '1'} and not transaction_id:
            return _unknown('Pagamento Cielo aprovado sem identificador externo.')
        installments = payment.get('installments', fields.get('numberOfQuotas', 0))
        try:
            installments = int(installments or 0)
        except (TypeError, ValueError):
            return _unknown('Parcelas Cielo inválidas.')
        if installments < 0:
            return _unknown('Parcelas Cielo inválidas.')
        result_status = (
            PaymentAttemptStatus.APPROVED if status_code in {'0', '1'}
            else PaymentAttemptStatus.CANCELLED
        )
        provider_status = 'approved' if result_status == PaymentAttemptStatus.APPROVED else 'cancelled'
        order_id = _safe_text(order.get('id'), limit=150)
        product = _safe_text(fields.get('productName'), limit=50)
        terminal = _safe_text(payment.get('terminal'), limit=150)
        message = _safe_text(payment.get('reason'), limit=500)
        result_data = {
            'provider_transaction_id': transaction_id,
            'provider_order_id': order_id,
            'provider_reference': _safe_text(reference, limit=150),
            'terminal_external_id': terminal,
            'authorization_code': _safe_text(payment.get('authCode'), limit=100),
            'nsu': _safe_text(payment.get('cieloCode'), limit=100),
            'card_brand': _safe_text(payment.get('brand'), limit=50),
            'card_mask': _safe_mask(payment.get('mask') or fields.get('bin')),
            'installments': max(installments, 1),
            'payment_product': product,
            'provider_status': provider_status,
            'provider_status_code': status_code,
            'provider_message': message,
        }
        return ProviderPaymentResult(
            status=result_status,
            result_data=result_data,
            safe_metadata={
                'provider': self.provider_code,
                'order_id': order_id,
                'reference': _safe_text(reference, limit=150),
                'status': provider_status,
                'status_code': status_code,
                'product': product,
                'terminal': terminal,
            },
        )

    def build_reversal_command(self, *, reversal, callback_url):
        attempt = reversal.source_attempt
        self._assert_cielo_attempt(attempt)
        if not attempt.provider_order_id or not attempt.authorization_code or not attempt.nsu:
            raise PaymentIntegrationConflict(
                'cielo_reversal_data_missing',
                'O pagamento original não possui os identificadores necessários para estorno na Cielo.',
            )
        credentials = get_cielo_credentials()
        request = {
            'clientID': credentials.client_id,
            'accessToken': credentials.access_token,
            'orderId': attempt.provider_order_id,
            'cieloCode': attempt.nsu,
            'authCode': attempt.authorization_code,
            'value': str(amount_to_cents(reversal.amount)),
        }
        encoded_request = base64.b64encode(json.dumps(
            request, ensure_ascii=True, separators=(',', ':'), sort_keys=True,
        ).encode('utf-8')).decode('ascii')
        uri = urlunsplit(('lio', 'payment-reversal', '', urlencode({
            'request': encoded_request, 'urlCallback': callback_url,
        }), ''))
        return ProviderLaunchCommand(
            operation='reversal', uri=uri,
            safe_metadata={
                'provider': self.provider_code,
                'source_attempt_id': str(attempt.pk),
                'order_id_present': True,
                'amount_cents': amount_to_cents(reversal.amount),
            },
        )

    def parse_reversal_callback(self, *, reversal, response, responsecode=None):
        attempt = reversal.source_attempt
        self._assert_cielo_attempt(attempt)
        error_code = str(responsecode).strip() if responsecode not in (None, '') else ''
        try:
            normalized_response = _BASE64_TRANSPORT_WHITESPACE.sub('', str(response or ''))
            payload = json.loads(base64.b64decode(normalized_response, validate=True).decode('utf-8'))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            logger.info(
                'cielo_reversal_callback_decode_failed operation_id=%s response_present=%s response_length=%s',
                reversal.pk, bool(response), len(str(response or '')),
            )
            if error_code in _ERROR_STATUS:
                status, fallback = _ERROR_STATUS[error_code]
                return ProviderReversalResult(
                    status=status,
                    result_data={
                        'provider_status': 'cancelled' if status == PaymentAttemptStatus.CANCELLED else 'error',
                        'provider_status_code': error_code, 'provider_message': fallback,
                    },
                    safe_metadata={'provider': self.provider_code, 'status_code': error_code},
                )
            return ProviderReversalResult(
                status=PaymentAttemptStatus.UNKNOWN,
                result_data={'provider_status': 'unknown', 'provider_message': 'Resposta de estorno Cielo não comprovável.'},
                safe_metadata={'provider': self.provider_code, 'result': 'unknown'},
            )
        if not isinstance(payload, dict):
            return ProviderReversalResult(
                status=PaymentAttemptStatus.UNKNOWN,
                result_data={'provider_status': 'unknown', 'provider_message': 'Estrutura do estorno Cielo é inválida.'},
                safe_metadata={'provider': self.provider_code, 'result': 'unknown'},
            )
        code = str(payload.get('code')).strip() if payload.get('code') is not None else ''
        if code in _ERROR_STATUS:
            status, fallback = _ERROR_STATUS[code]
            message = _safe_text(payload.get('reason')) or fallback
            return ProviderReversalResult(
                status=status,
                result_data={
                    'provider_status': 'cancelled' if status == PaymentAttemptStatus.CANCELLED else 'error',
                    'provider_status_code': code, 'provider_message': message,
                },
                safe_metadata={'provider': self.provider_code, 'status_code': code},
            )
        status_code = str(payload.get('statusCode', payload.get('status'))).strip()
        order_id = _safe_text(payload.get('orderId') or payload.get('id'), limit=150)
        if status_code not in {'0', '1'} or order_id != attempt.provider_order_id:
            return ProviderReversalResult(
                status=PaymentAttemptStatus.UNKNOWN,
                result_data={'provider_status': 'unknown', 'provider_message': 'Estorno Cielo não pôde ser confirmado.'},
                safe_metadata={'provider': self.provider_code, 'result': 'unknown'},
            )
        return ProviderReversalResult(
            status=PaymentAttemptStatus.APPROVED,
            result_data={
                'provider_status': 'approved', 'provider_status_code': status_code,
                'provider_message': _safe_text(payload.get('reason')),
            },
            safe_metadata={
                'provider': self.provider_code, 'status': 'approved', 'status_code': status_code,
                'order_id': order_id,
            },
        )
