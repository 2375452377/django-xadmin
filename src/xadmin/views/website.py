from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import LoginView as login
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from xadmin.forms import AdminAuthenticationForm
from xadmin.views.base import BaseAdminView


class IndexView(TemplateView):
    template_name = 'xadmin/base_site.html'


class LoginView(BaseAdminView):
    title = _('Please Login')
    login_form = None
    login_template = None

    @never_cache
    def get(self, request, *args, **kwargs):
        context = self.get_context()
        context.update({
            'title': self.title,
            REDIRECT_FIELD_NAME: request.get_full_path(),
        })
        default = {
            'extra_context': context,
            'authentication_form': self.login_form or AdminAuthenticationForm,
            'template_name': self.login_template or 'xadmin/views/login.html'
        }
        return login.as_view(**default)(request)

    @never_cache
    def post(self, request, *args, **kwargs):
        return self.get(request)
