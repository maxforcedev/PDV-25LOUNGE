from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, localcontext


CALCULATION_PRECISION = 60


def exact_content_equivalent(content, package_content):
    if content is None or package_content is None:
        raise ValueError('content and package_content are required')
    content = Decimal(content)
    package_content = Decimal(package_content)
    if package_content <= 0:
        raise ValueError('package_content must be positive')
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return content / package_content


def exact_weighted_average(previous_quantity, previous_cost, incoming_quantity, incoming_cost):
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        total_quantity = previous_quantity + incoming_quantity
        return (
            previous_quantity * previous_cost
            + incoming_quantity * incoming_cost
        ) / total_quantity


def exact_multiply_quantized(left, right, quantum=Decimal('0.000000000001')):
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return (Decimal(left) * Decimal(right)).quantize(
            quantum, rounding=ROUND_HALF_UP
        )


def exact_multiply(left, right):
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return Decimal(left) * Decimal(right)


def exact_sum(values):
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        return sum((Decimal(value) for value in values), Decimal('0'))


def content_breakdown(content, package_content):
    if content is None or package_content is None:
        raise ValueError('content and package_content are required')
    content = Decimal(content)
    package_content = Decimal(package_content)
    if package_content <= 0:
        raise ValueError('package_content must be positive')
    sign = Decimal('-1') if content < 0 else Decimal('1')
    absolute = abs(content)
    with localcontext() as context:
        context.prec = CALCULATION_PRECISION
        complete = (absolute / package_content).to_integral_value(rounding=ROUND_FLOOR)
        residual = absolute - complete * package_content
    return sign * complete, sign * residual
