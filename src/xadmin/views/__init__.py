from django.contrib.auth.admin import csrf_protect_m

from .base import BaseAdminObject, BaseAdminPlugin, BaseAdminView, filter_hook
from .website import IndexView, LoginView

__all__ = (
    'BaseAdminObject',
    'BaseAdminPlugin', 'BaseAdminView',
    'IndexView', 'LoginView',
    'filter_hook', 'csrf_protect_m', 'register_builtin_views',
)


# admin site-wide views
def register_builtin_views(site):
    site.registry_view(path='', admin_view_class=IndexView, name='index')
    site.registry_view(path='login/', admin_view_class=LoginView, name='login')

    site.set_login_view(LoginView)
