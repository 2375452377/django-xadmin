import copy
import inspect
from functools import update_wrapper

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models.base import ModelBase
from django.template import Engine
from django.views.decorators.cache import never_cache


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class MergeAdminMetaclass(type):
    def __new__(mcs, name, bases, attrs):
        return type.__new__(mcs, str(name), bases, attrs)


class AdminSite:
    def __init__(self, name='xadmin'):
        self.name = name
        self.app_name = 'xadmin'
        self.login_view = None

        self._registry = {}  # model_class class -> admin_class class
        self._registry_avs = {}  # admin_view_class class -> admin_class class
        self._registry_settings = {}  # settings name -> admin_class class
        # url instance contains (path, admin_view class, name)
        self._registry_views = []
        # url instance contains (path, admin_view class, name)
        self._registry_modelviews = []
        self._registry_plugins = {}  # view_class class -> plugin_class class

        self._admin_view_cache = {}

        self.model_admins_order = 0

    def copy_registry(self):
        return {
            'models': copy.copy(self._registry),
            'avs': copy.copy(self._registry_avs),
            'views': copy.copy(self._registry_views),
            'settings': copy.copy(self._registry_settings),
            'modelviews': copy.copy(self._registry_modelviews),
            'plugins': copy.copy(self._registry_plugins),
        }

    def restore_registry(self, data):
        self._registry = data['models']
        self._registry_avs = data['avs']
        self._registry_views = data['views']
        self._registry_settings = data['settings']
        self._registry_modelviews = data['modelviews']
        self._registry_plugins = data['plugins']

    def register_modelview(self, path, admin_view_class, name):
        from xadmin.views import BaseAdminView

        if issubclass(admin_view_class, BaseAdminView):
            self._registry_modelviews.append((path, admin_view_class, name))
        else:
            raise ImproperlyConfigured(f"The registered view class {admin_view_class.__name__} "
                                       f"isn't subclass of {BaseAdminView.__name__}")

    def registry_view(self, path, admin_view_class, name):
        self._registry_views.append((path, admin_view_class, name))

    def register_plugin(self, plugin_class, admin_view_class):
        from xadmin.views import BaseAdminPlugin

        if issubclass(plugin_class, BaseAdminPlugin):
            self._registry_plugins.setdefault(admin_view_class, []).append(plugin_class)
        else:
            raise ImproperlyConfigured(f"The registered plugin class {plugin_class.__name__} "
                                       f"isn't subclass of {BaseAdminPlugin.__name__}")

    def register_settings(self, name, admin_class):
        self._registry_settings[name.lower()] = admin_class

    def register(self, model_or_iterable, admin_class=None, **options):
        from xadmin.views.base import BaseAdminView

        if isinstance(model_or_iterable, ModelBase) or issubclass(model_or_iterable, BaseAdminView):
            model_or_iterable = [model_or_iterable]

        if admin_class is None:
            admin_class = object

        for model in model_or_iterable:
            if isinstance(model, ModelBase):
                if model._meta.abstract:
                    raise ImproperlyConfigured(
                        f'The model {model.__name__} is abstract, so it cannot be registered with admin.'
                    )
                if model in self._registry:
                    raise AlreadyRegistered(f'The model {model.__name__} is already registered')

                # If we got **options then dynamically construct a subclass of
                # admin_class with those **options.
                if options:
                    # For reasons I don't quite understand, without a __module__
                    # the created class appears to "live" in the wrong place,
                    # which causes issues later on.
                    options['__module__'] = __name__

                admin_class = type(
                    f'{model._meta.app_label}{model._meta.model_name}Admin',
                    (admin_class,),
                    options or {}
                )
                admin_class.model = model
                admin_class.order = self.model_admins_order
                self.model_admins_order += 1
                self._registry[model] = admin_class
            else:
                if model in self._registry_avs:
                    raise ImproperlyConfigured(f'The admin_view_class {model.__name__} is already registered')

                if options:
                    options['__module__'] = __name__
                    admin_class = type(f'{model.__name__}Admin', (admin_class,), options)

                # Instantiate the admin class to save in the registry
                self._registry_avs[model] = admin_class

    def unregister(self, model_or_iterable):
        """
        Unregisters the given model(s).

        If a model isn't already registered, this will raise NotRegistered.
        """
        from xadmin.views import BaseAdminView

        if isinstance(model_or_iterable, ModelBase) or issubclass(model_or_iterable, BaseAdminView):
            model_or_iterable = [model_or_iterable]

        for model in model_or_iterable:
            if isinstance(model, ModelBase):
                if model not in self._registry:
                    raise NotRegistered(f'The model {model.__name__} is not registered')
                del self._registry[model]
            else:
                if model not in self._registry_avs:
                    raise NotRegistered(f'The admin_view_class {model.__name__} is not registered')
                del self._registry_avs[model]

    def set_login_view(self, login_view):
        self.login_view = login_view

    def has_permission(self, request):
        """
        Return True if the given HttpRequest has permission to view
        *at least one* page in the admin site.
        """
        return request.user.is_active and request.user.is_staff

    def check_dependencies(self):
        """
        Check that all things needed to run the admin have been correctly installed.

        The default implementation checks that LogEntry, ContentType and the
        auth context processor are installed.
        """
        from django.contrib.contenttypes.models import ContentType

        if not ContentType._meta.installed:
            raise ImproperlyConfigured("Put 'django.contrib.contenttypes' in "
                                       "your INSTALLED_APPS setting in order to use the admin application.")

        default_template_engine = Engine.get_default()
        context_processors = default_template_engine.context_processors
        if not (
                'django.contrib.auth.context_processors.auth' in context_processors
                or 'django.core.context_processors.auth' in context_processors
        ):
            raise ImproperlyConfigured("Put 'django.contrib.auth.context_processors.auth' "
                                       "in your TEMPLATE_CONTEXT_PROCESSORS setting "
                                       "in order to use the admin application.")

    def admin_view(self, view, cacheable=False):
        """
        Decorator to create an admin view attached to this ``AdminSite``. This
        wraps the view and provides permission checking by calling
        ``self.has_permission``.

        You'll want to use this from within ``AdminSite.get_urls()``:

            class MyAdminSite(AdminSite):

                def get_urls(self):
                    from django.urls import path

                    urls = super().get_urls()
                    urls += [
                        path('my_view/', self.admin_view(some_view))
                    ]
                    return urls

        By default, admin_views are marked non-cacheable using the
        ``never_cache`` decorator. If the view can be safely cached, set
        cacheable=True.
        """

        def inner(request, *args, **kwargs):
            if not self.has_permission(request):
                return self.create_admin_view(self.login_view)(request, *args, **kwargs)
            return view(request, *args, **kwargs)

        if not cacheable:
            inner = never_cache(inner)
        return update_wrapper(wrapper=inner, wrapped=view)

    def _get_settings_class(self, admin_view_class):
        name = admin_view_class.__name__.lower()

        if name in self._registry_settings:
            return self._registry_settings[name]
        elif name.endswith('admin') and name[0:-5] in self._registry_settings:
            return self._registry_settings[name[0:-5]]
        elif name.endswith('adminview') and name[0:-9] in self._registry_settings:
            return self._registry_settings[name[0:-9]]

        return None

    def _get_merge_attrs(self, option_class, plugin_class):
        return {
            name: getattr(option_class, name)
            for name in dir(option_class)
            if name[0] != '_' and hasattr(plugin_class, name) and not callable(getattr(option_class, name))
        }

    def _create_plugin(self, option_classes):
        def merge_class(plugin_class):
            if option_classes:
                attrs = {}
                bases = [plugin_class]
                for oc in option_classes:
                    attrs.update(self._get_merge_attrs(oc, plugin_class))
                    meta_class = getattr(
                        oc,
                        plugin_class.__name__,
                        getattr(oc, plugin_class.__name__.replace('Plugin', ''), None),
                    )
                    if meta_class:
                        bases.insert(0, meta_class)
                if attrs:
                    plugin_class = MergeAdminMetaclass(
                        f'{"".join(oc.__name__ for oc in option_classes)}{plugin_class.__name__}',
                        tuple(bases),
                        attrs
                    )
            return plugin_class
        return merge_class

    def get_plugins(self, admin_view_class, *option_classes):
        from xadmin.views import BaseAdminView

        plugins = []
        opts = [oc for oc in option_classes if oc]
        for klass in admin_view_class.mro():
            if klass == BaseAdminView or issubclass(klass, BaseAdminView):
                merge_opts = []
                admin_class = self._registry_avs.get(klass)
                if admin_class:
                    merge_opts.append(admin_class)
                settings_class = self._get_settings_class(klass)
                if settings_class:
                    merge_opts.append(settings_class)
                merge_opts.extend(opts)
                ps = self._registry_plugins.get(klass, [])
                plugins.extend(map(self._create_plugin(merge_opts), ps) if merge_opts else ps)
        return plugins

    def get_view_class(self, admin_view_class, option_class=None, **opts):
        """ 创建继承自 view 类, admin 类, plugin 类的子类 """
        merges = [option_class] if option_class else []
        for klass in admin_view_class.mro():
            admin_class = self._registry_avs.get(klass)
            if admin_class:
                merges.append(admin_class)
            settings_class = self._get_settings_class(admin_view_class)
            if settings_class:
                merges.append(admin_class)
            merges.append(klass)

        new_class_name = ''.join(c.__name__ for c in merges)
        if new_class_name not in self._admin_view_cache:
            plugins = self.get_plugins(admin_view_class, option_class)
            self._admin_view_cache[new_class_name] = MergeAdminMetaclass(
                new_class_name,
                tuple(merges),
                dict({'plugin_classes': plugins, 'admin_site': self}, **opts),
            )
        return self._admin_view_cache[new_class_name]

    def create_admin_view(self, admin_view_class):
        return self.get_view_class(admin_view_class).as_view()

    def create_model_admin_view(self, admin_view_class, model, option_class):
        return self.get_view_class(admin_view_class, option_class).as_view()

    def get_urls(self):
        from django.urls import path, re_path, include
        from xadmin.views import BaseAdminView

        if settings.DEBUG:
            self.check_dependencies()

        def wrap(view, cacheable=False):
            def wrapper(*args, **kwargs):
                return self.admin_view(view, cacheable)(*args, **kwargs)

            wrapper.admin_site = self
            return update_wrapper(wrapper, wrapped=view)

        # Admin-site-wide views.
        urlpatterns = [
            path('jsi18n/', wrap(self.i18n_javascript, cacheable=True), name='jsi18n')
        ]

        # Register admin views
        urlpatterns += [
            path(
                _path,
                wrap(self.create_admin_view(clz_or_fun))
                if inspect.isclass(clz_or_fun) and issubclass(clz_or_fun, BaseAdminView)
                else include(clz_or_fun(self)),
                name=name,
            )
            for _path, clz_or_fun, name in self._registry_views
        ]

        # Add in each model's views.
        for model, admin_class in self._registry.items():
            view_urls = [
                re_path(
                    _path,
                    wrap(self.create_model_admin_view(admin_view_class, model, option_class=admin_class)),
                    name=name % (model._meta.app_label, model._meta.model_name),
                )
                for _path, admin_view_class, name in self._registry_modelviews
            ]
            urlpatterns += [
                path(f'{model._meta.app_label}/{model._meta.model_name}/', include(view_urls))
            ]
        return urlpatterns

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    def i18n_javascript(self, request, extra_context=None):
        """
        Display the i18n JavaScript that the Django admin requires.

        `extra_context` is unused but present for consistency with the other
        admin views.
        """
        from django.views.i18n import JavaScriptCatalog
        return JavaScriptCatalog.as_view(packages=['django.contrib.admin', 'xadmin'])(request)


site = AdminSite()
