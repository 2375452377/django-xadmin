from functools import update_wrapper

from django.views.decorators.cache import never_cache


class AdminSite:
    def __init__(self, name='xadmin'):
        self.name = name
        self.app_name = 'xadmin'
        self.login_view = None

        # url instance contains (path, admin_view class, name)
        self._registry_view = []

    def registry_view(self, path, admin_view_class, name):
        self._registry_view.append((path, admin_view_class, name))

    def set_login_view(self, login_view):
        self.login_view = login_view

    def has_permission(self, request):
        """
        Return True if the given HttpRequest has permission to view
        *at least one* page in the admin site.
        """
        return request.user.is_active and request.user.is_staff

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

    def create_admin_view(self, admin_view_class):
        return admin_view_class.as_view()

    def get_urls(self):
        from django.urls import path, re_path

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
                wrap(self.create_admin_view(admin_view_class)),
                name=name,
            )
            for _path, admin_view_class, name in self._registry_view
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
