# gofresh_stockpro/utils.py
import datetime
from urllib.parse import urlencode as JinjaUrlencode, parse_qs, urlsplit, urlunsplit, quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Union

def format_thai_datetime(value: Optional[Union[datetime.datetime, datetime.date]], format_str: str = "%d/%m/%Y %H:%M") -> str:
    """Jinja2 filter to convert UTC or naive datetime to Thai time and format it."""
    if value is None:
        return "-"
    try:
        thai_tz = ZoneInfo("Asia/Bangkok")
    except ZoneInfoNotFoundError:
        print("!!! Timezone 'Asia/Bangkok' not found. Using UTC fallback. Install tzdata? (pip install tzdata)")
        try:
            return value.strftime(format_str)
        except Exception:
            return str(value)

    if isinstance(value, datetime.datetime):
        # If naive, assume UTC
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(thai_tz).strftime(format_str)
    elif isinstance(value, datetime.date):
        date_only_format = "%d/%m/%Y"
        if any(c in format_str for c in ['H', 'I', 'M', 'S', 'p', 'z', 'Z', 'X', 'x']):
            return value.strftime(date_only_format)
        return value.strftime(format_str)
    return str(value)

def format_thai_date(value: Optional[Union[datetime.datetime, datetime.date]], format_str: str = "%d/%m/%Y") -> str:
    """Jinja2 filter to format date as Thai date. Ensures time components are ignored if a datetime object is passed."""
    if value is None:
        return "-"
    if isinstance(value, datetime.datetime):
        value_date = value.date()
    elif isinstance(value, datetime.date):
        value_date = value
    else:
        return str(value)

    date_only_format_default = "%d/%m/%Y"
    if any(c in format_str for c in ['H', 'I', 'M', 'S', 'p', 'z', 'Z', 'X', 'x']):
        return value_date.strftime(date_only_format_default)
    return value_date.strftime(format_str)


def generate_filter_url_for_template(request_url_str: str, base_path_for_route: str, **new_params_to_set) -> str:
    """
    Generates a URL with updated query parameters, ensuring 'page' resets to 1
    if major filters change, and preserves 'limit'.
    """
    _dummy_scheme, _dummy_netloc, _dummy_path, query_string, _dummy_fragment = urlsplit(str(request_url_str))
    current_params_dict = {k: v[0] for k, v in parse_qs(query_string).items()}

    final_query_params = {}
    major_filter_changed = False

    # Preserve or update limit
    if 'limit' in new_params_to_set and new_params_to_set['limit'] is not None:
        final_query_params['limit'] = str(new_params_to_set['limit'])
    elif 'limit' in current_params_dict:
        final_query_params['limit'] = current_params_dict['limit']

    filter_keys = ['location', 'category', 'type', 'product_id', 'start_date', 'end_date', 'days_ahead']
    for key in filter_keys:
        new_value = new_params_to_set.get(key)
        current_value = current_params_dict.get(key)

        if new_value is not None:
            if str(new_value).strip() != "":
                final_query_params[key] = str(new_value)
                if str(new_value) != current_value:
                    major_filter_changed = True
            elif current_value is not None: # Filter was cleared
                major_filter_changed = True
        elif current_value is not None and str(current_value).strip() != "": # Preserve if not changing and not empty
            final_query_params[key] = current_value

    # Handle page parameter
    if 'page' in new_params_to_set and new_params_to_set['page'] is not None:
        final_query_params['page'] = str(new_params_to_set['page'])
    elif major_filter_changed:
        final_query_params['page'] = '1'
    elif 'page' in current_params_dict:
        final_query_params['page'] = current_params_dict['page']
    # No explicit 'else: final_query_params['page'] = '1'' to avoid forcing page=1 on every non-paginated filter action

    query_string_built = JinjaUrlencode(final_query_params)
    separator = "?" if query_string_built else ""
    return f"{base_path_for_route.rstrip('/')}{separator}{query_string_built}"