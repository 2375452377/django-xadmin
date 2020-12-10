PLUGINS = (
    'portal',
)


def register_builtin_plugins():
    from importlib import import_module
    from django.conf import settings

    exclude_plugins = getattr(settings, 'XADMIN_EXCLUDE_PLUGINS', [])
    [import_module(f'xadmin.plugins.{plugin}') for plugin in PLUGINS if plugin not in exclude_plugins]
