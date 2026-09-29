_ADAPTERS = {}


def register_adapter(adapter_class):
    code = adapter_class.provider_code
    if not code:
        raise ValueError('Provider adapters must define provider_code.')
    if code in _ADAPTERS:
        raise ValueError(f'Provider adapter already registered for {code}.')
    _ADAPTERS[code] = adapter_class
    return adapter_class


def get_adapter(provider_code):
    try:
        return _ADAPTERS[str(provider_code).strip().lower()]()
    except KeyError as error:
        raise LookupError(f'No payment adapter is registered for {provider_code!r}.') from error


def registered_adapters():
    return dict(_ADAPTERS)
