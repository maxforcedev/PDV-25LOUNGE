from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderLaunchCommand:
    """A command for a client launcher; uri can carry credentials and is secret."""

    operation: str
    uri: str = field(repr=False)
    safe_metadata: dict

    def __repr__(self):
        return (
            f'{type(self).__name__}(operation={self.operation!r}, '
            f'safe_metadata={self.safe_metadata!r})'
        )


@dataclass(frozen=True)
class ProviderPaymentResult:
    """Normalized callback output for resolve_payment_attempt()."""

    status: str
    result_data: dict
    safe_metadata: dict


@dataclass(frozen=True)
class ProviderReversalResult:
    """Normalized external reversal result; local ledger application is separate."""

    status: str
    result_data: dict
    safe_metadata: dict


class PaymentProviderAdapter:
    provider_code = None

    def build_payment_command(self, *, attempt, callback_url, items, installments=1):
        raise NotImplementedError

    def parse_payment_callback(self, *, attempt, response, responsecode=None):
        raise NotImplementedError

    def build_reversal_command(self, *, reversal, callback_url):
        raise NotImplementedError

    def parse_reversal_callback(self, *, reversal, response, responsecode=None):
        raise NotImplementedError
