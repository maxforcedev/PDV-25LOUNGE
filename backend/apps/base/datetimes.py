import re
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError


DATETIME_WITH_TIME = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')


def parse_datetime_range(params, *, required=False, default_today=False):
    values = {}
    current_timezone = timezone.get_default_timezone()
    for name in ('start_datetime', 'end_datetime'):
        raw_value = params.get(name)
        if raw_value in (None, ''):
            values[name] = None
            continue
        if not isinstance(raw_value, str) or not DATETIME_WITH_TIME.match(raw_value):
            raise ValidationError({name: 'Informe uma data e hora ISO válida.'})
        try:
            value = parse_datetime(raw_value)
        except (ValueError, OverflowError):
            value = None
        if value is None:
            raise ValidationError({name: 'Informe uma data e hora ISO válida.'})
        if timezone.is_naive(value):
            value = timezone.make_aware(value, current_timezone)
        else:
            value = value.astimezone(current_timezone)
        values[name] = value

    start = values['start_datetime']
    end = values['end_datetime']
    if required and (start is None or end is None):
        errors = {}
        if start is None:
            errors['start_datetime'] = 'Informe a data e hora inicial.'
        if end is None:
            errors['end_datetime'] = 'Informe a data e hora final.'
        raise ValidationError(errors)
    if default_today:
        now = timezone.localtime(timezone.now(), current_timezone)
        start = start or now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end or now
    if start and end and start > end:
        raise ValidationError(
            {'end_datetime': 'A data e hora final deve ser posterior ou igual à inicial.'}
        )
    return start, end


def inclusive_end_exclusive(end):
    return end + (timedelta(seconds=1) if end.microsecond == 0 else timedelta(microseconds=1))


def filter_datetime_range(queryset, field, start, end):
    filters = {}
    if start:
        filters[f'{field}__gte'] = start
    if end:
        filters[f'{field}__lt'] = inclusive_end_exclusive(end)
    return queryset.filter(**filters)


def canonical_datetime_range(start, end):
    current_timezone = timezone.get_default_timezone()
    return {
        'start_datetime': start.astimezone(current_timezone).isoformat(),
        'end_datetime': end.astimezone(current_timezone).isoformat(),
    }
