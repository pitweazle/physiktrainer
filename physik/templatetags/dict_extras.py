from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    if d is None:
        return None

    # 1) Direkt probieren
    try:
        return d[key]
    except Exception:
        pass

    # 2) int-Version probieren
    try:
        ikey = int(key)
        if ikey in d:
            return d[ikey]
    except Exception:
        pass

    # 3) str-Version probieren
    try:
        skey = str(key)
        if skey in d:
            return d[skey]
    except Exception:
        pass

    return None

