from xadmin.views.website import IndexView, LoginView


# admin site-wide views
def register_builtin_views(site):
    site.registry_view(path='', admin_view_class=IndexView, name='index')
    site.registry_view(path='login/', admin_view_class=LoginView, name='login')

    site.set_login_view(LoginView)
