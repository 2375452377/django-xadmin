from xadmin.sites import site

default_app_config = 'xadmin.apps.XadminConfig'


def autodiscover():
    from xadmin.views import register_builtin_views
    register_builtin_views(site)
