from django.template import Library
from django.utils.safestring import mark_safe

from xadmin.util import vendor as util_vendor

register = Library()


@register.simple_tag(takes_context=True)
def view_block(context, block_name, *args, **kwargs):
    if 'admin_view' not in context:
        return ''

    admin_view = context['admin_view']
    nodes = []
    method_name = f'block_{block_name}'

    for view in [admin_view] + admin_view.plugins:
        if hasattr(view, method_name) and callable(getattr(view, method_name)):
            block_func = getattr(view, method_name)
            result = block_func(context, nodes, *args, **kwargs)
            if result and isinstance(result, str):
                nodes.append(result)
    if nodes:
        return mark_safe(''.join(nodes))
    return ''


@register.simple_tag
def vendor(*tags):
    return util_vendor(*tags).render()
