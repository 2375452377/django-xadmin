from xadmin.sites import site, AdminSite

default_app_config = 'xadmin.apps.XAdminConfig'


def autodiscover():
    """
    Auto-discover INSTALLED_APPS adminx.py modules and fail silently when
    not present. This forces an import on them to register any admin bits they
    may want.
    """
    from importlib import import_module
    from django.apps import apps
    from django.conf import settings
    from django.utils.module_loading import module_has_submodule
    from xadmin.plugins import register_builtin_plugins
    from xadmin.views import register_builtin_views

    setattr(settings, 'CRISPY_TEMPLATE_PACK', 'bootstrap3')
    setattr(settings, 'CRISPY_CLASS_CONVERTERS', {
        'textinput': 'textinput textInput form-control',
        'fileinput': 'fileinput fileUpload form-control',
        'passwordinput': 'textinput textInput form-control',
    })

    register_builtin_views(site)
    register_builtin_plugins()

    for app_config in apps.get_app_configs():
        mod = import_module(app_config.name)
        # Attempt to import the app's adminx module.
        try:
            before_import_registry = site.copy_registry()
            import_module(f'{app_config.name}.adminx')
        except Exception as e:
            # Reset the model registry to the state before the last import as
            # this import will have to reoccur on the next request and this
            # could raise NotRegistered and AlreadyRegistered exceptions
            # (see #8245).
            site.restore_registry(before_import_registry)

            # Decide whether to bubble up this error. If the app just
            # doesn't have an admin module, we can ignore the error
            # attempting to import it, otherwise we want it to bubble up.
            if module_has_submodule(mod, 'adminx'):
                raise e
