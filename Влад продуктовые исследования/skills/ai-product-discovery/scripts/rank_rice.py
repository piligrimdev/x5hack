"""Rank RICE scenarios without replacing unknown factors with fabricated values."""
import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def rank(rows):
    if not isinstance(rows, list):
        raise ValueError('Input must be a JSON array')
    result, seen = [], set()
    for original in rows:
        if not isinstance(original, dict):
            raise ValueError('Each hypothesis must be an object')
        row = dict(original)
        identifier = row.get('id')
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)) or identifier == '':
            raise ValueError('Each hypothesis needs a string or integer id')
        if str(identifier) in seen:
            raise ValueError(f'Duplicate id: {identifier}')
        seen.add(str(identifier))
        factors = {}
        for field in ('reach', 'impact', 'confidence', 'effort'):
            if field not in row:
                raise ValueError(f'{identifier}: missing {field}; use null for unknown')
            value = row[field]
            if value is None:
                factors[field] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{identifier}: {field} must be numeric or null')
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError(f'{identifier}: non-finite {field}')
            factors[field] = number
        r, i, c, e = (factors[k] for k in ('reach', 'impact', 'confidence', 'effort'))
        if r is not None and (r < 0 or r != r.to_integral_value()):
            raise ValueError(f'{identifier}: reach must be a nonnegative integer')
        if i is not None and i not in map(Decimal, ('0.25', '0.5', '1', '2', '3')):
            raise ValueError(f'{identifier}: invalid impact scale')
        if c is not None and not 0 <= c <= 1:
            raise ValueError(f'{identifier}: confidence must be between 0 and 1')
        if e is not None and (e < Decimal('0.5') or e % Decimal('0.5')):
            raise ValueError(f'{identifier}: effort must be >= 0.5 in steps of 0.5')
        if any(v is None for v in factors.values()):
            score = None
            row.update(rice_score=None, scoring_status='needs_estimate')
        else:
            score = r * i * c / e
            row.update(rice_score=float(score.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)), scoring_status='computed')
        result.append((row, score, factors))
    result.sort(key=lambda x: (x[1] is None, -x[1] if x[1] is not None else 0,
                              -x[2]['impact'] if x[1] is not None else 0,
                              -x[2]['reach'] if x[1] is not None else 0,
                              x[2]['effort'] if x[1] is not None else 0))
    return [row for row, _, _ in result]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        result = rank(json.loads(args.input.read_text(encoding='utf-8')))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'RICE error: {exc}\n')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
