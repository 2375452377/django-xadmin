from xadmin.views import BaseAdminPlugin


class BasePortalPlugin(BaseAdminPlugin):
    # Media
    def get_media(self, media):
        return media + self.vendor('xadmin.plugin.portal.js')


class ModelFormPlugin(BasePortalPlugin):
    def block_form_top(self, context, nodes):
        # put portal key and submit url to page
        return f'<input type="hidden" id="_portal_key" value="{self._portal_key()}" />'

    def _portal_key(self):
        return f'{self.opts.app_label}_{self.opts.model_name}_editform_portal'
