from django.contrib.auth.admin import csrf_protect_m
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache

from xadmin.views import filter_hook
from xadmin.views.base import CommAdminView


class Dashboard(CommAdminView):

    widget_customiz = True
    widgets = []
    title = _('Dashboard')
    icon = None

    def get_page_id(self):
        return self.request.path

    def get_portal_key(self):
        return f'dashboard:{self.get_page_id()}:pos'

    @filter_hook
    def get_title(self):
        return self.title

    @filter_hook
    def get_context(self):
        new_context = {
            'title': self.get_title(),
            'icon': self.icon,
            'portal_key': self.get_portal_key(),
        }
        context = super(Dashboard, self).get_context()
        context.update(new_context)
        return context

    @never_cache
    def get(self, request, *args, **kwargs):
        return self.template_response('xadmin/views/dashboard.html', self.get_context())

    @csrf_protect_m
    def post(self, request, *args, **kwargs):
        return self.get(request)

    @filter_hook
    def get_media(self):
        media = super(Dashboard, self).get_media()
        media += self.vendor('xadmin.page.dashboard.js', 'xadmin.page.dashboard.css')
        if self.widget_customiz:
            media = media + self.vendor('xadmin.plugin.portal.js')
        for ws in self.widgets:
            for widget in ws:
                media = media + widget.media()
        return media
