from django import template


register = template.Library()


@register.filter
def get_item(obj, key):
    """Return obj[key] if dict-like, else getattr(obj, key, '') for templates."""
    if obj is None or key is None:
        return ''
    try:
        if isinstance(obj, dict):
            return obj.get(key, '')
        # Fallback to attribute access
        return getattr(obj, key, '')
    except Exception:
        return ''


