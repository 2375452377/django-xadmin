from django.apps import AppConfig


class XAdminConfig(AppConfig):
    name = 'xadmin'

    def ready(self):
        self.module.autodiscover()
