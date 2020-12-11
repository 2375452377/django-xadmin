import copy
import datetime
import decimal
import functools
import json
from collections import OrderedDict
from functools import update_wrapper
from inspect import getfullargspec

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import classonlymethod
from django.utils.encoding import force_text, smart_text
from django.utils.functional import Promise
from django.utils.text import capfirst
from django.utils.translation import ugettext as _
from django.views import View

from xadmin.util import vendor, sortkeypicker


class IncorrectPluginArg(Exception):
    pass


def filter_chain(filters, token, func, *args, **kwargs):
    if token == -1:
        return func()
    else:
        def _inner_method():
            fm = filters[token]
            fargs = getfullargspec(fm)[0]
            if len(fargs) == 1:
                # Only self arg
                result = func()
                if result is None:
                    return fm()
                else:
                    raise IncorrectPluginArg('Plugin filter method need a arg to receive parent method result.')
            else:
                return fm(func if fargs[1] == '__' else func(), *args, **kwargs)

        return filter_chain(filters, token - 1, _inner_method, *args, **kwargs)


def filter_hook(func):
    tag = func.__name__
    func.__doc__ = "``filter_hook``\n\n" + (func.__doc__ or "")

    @functools.wraps(func)
    def method(self, *args, **kwargs):

        def _inner_method():
            return func(self, *args, **kwargs)

        if self.plugins:
            filters = [
                (getattr(getattr(p, tag), 'priority', 10), getattr(p, tag))
                for p in self.plugins if callable(getattr(p, tag, None))
            ]
            filters = [f for p, f in sorted(filters, key=lambda x: x[0])]
            return filter_chain(filters, len(filters) - 1, _inner_method, *args, **kwargs)
        else:
            return _inner_method()

    return method


class JSONEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            if timezone.is_naive(o):
                o = timezone.make_aware(value=o)
            return o.astimezone().strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(o, datetime.date):
            return o.strftime('%Y-%m-%d')
        elif isinstance(o, decimal.Decimal):
            return str(o)
        elif isinstance(o, Promise):
            return force_text(o)
        else:
            try:
                return super(JSONEncoder, self).default(o)
            except Exception:
                smart_text(o)


class BaseAdminObject:
    def get_admin_url(self, name, *args, **kwargs):
        return reverse(f'{self.admin_site.app_name}:{name}', args=args, kwargs=kwargs)

    def get_model_url(self, model, name, *args, **kwargs):
        return reverse(
            f'{self.admin_site.app_name}:{model._meta.app_label}_{model._meta.model_name}_{name}',
            args=args,
            kwargs=kwargs,
            current_app=self.admin_site.name
        )

    def get_model_perm(self, model, name):
        return f'{model._meta.app_label}.{name}_{model._meta.model_name}'

    def render_to_response(self, content, response_type='json'):
        if response_type == 'json':
            return JsonResponse(data=content, encoder=JSONEncoder)
        return HttpResponse(content)

    def template_response(self, template, context):
        return TemplateResponse(self.request, template, context)

    def vendor(self, *tags):
        return vendor(*tags)


class BaseAdminPlugin(BaseAdminObject):
    def __init__(self, admin_view):
        self.admin_view = admin_view
        self.admin_site = admin_view.admin_site

        if hasattr(admin_view, 'model'):
            self.model = admin_view.model
            self.opts = admin_view.model._meta

    def init_request(self, *args, **kwargs):
        """ 判断是否启用插件，True 为启用，False 为禁用 """


class BaseAdminView(BaseAdminObject, View):
    """ Base Admin view, support some comm attrs."""

    base_template = 'xadmin/base.html'

    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.request_method = request.method.lower()
        self.user = request.user

        self.plugins = []
        self.base_plugins = [p(self) for p in getattr(self, 'plugin_classes', [])]

        self.args = args
        self.kwargs = kwargs

        self.init_request(*args, **kwargs)
        self.init_plugin(*args, **kwargs)

    @classonlymethod
    def as_view(cls):
        def view(request, *args, **kwargs):
            self = cls(request, *args, **kwargs)
            if hasattr(self, 'get') and not hasattr(self, 'head'):
                self.head = self.get

            if self.request_method in self.http_method_names:
                handle = getattr(self, self.request_method, self.http_method_not_allowed)
            else:
                handle = self.http_method_not_allowed

            return handle(request, *args, **kwargs)

        # take name and docstring from class
        update_wrapper(view, cls, updated=())
        return view

    def init_request(self, *args, **kwargs):
        """ override """

    def init_plugin(self, *args, **kwargs):
        plugins = []
        for p in self.base_plugins:
            p.request = self.request
            p.user = self.user
            p.args = self.args
            p.kwargs = self.kwargs
            result = p.init_request(*args, **kwargs)
            if result is not False:
                plugins.append(p)
        self.plugins = plugins

    @filter_hook
    def get_context(self):
        return {'admin_view': self, 'media': self.media, 'base_template': self.base_template}

    @property
    def media(self):
        return self.get_media()

    @filter_hook
    def get_media(self):
        return forms.Media()


class CommAdminView(BaseAdminView):
    base_template = 'xadmin/base_site.html'
    menu_template = 'xadmin/includes/sitemenu_default.html'

    site_title = getattr(settings, 'XADMIN_TITLE', _('Django XAdmin'))
    site_footer = getattr(settings, "XADMIN_FOOTER_TITLE", _('my-company.inc'))

    global_models_icon = {}
    default_model_icon = None
    apps_label_title = {}
    apps_icons = {}

    def get_site_menu(self):
        return None

    @filter_hook
    def get_nav_menu(self):
        site_menu = list(self.get_site_menu() or [])
        had_urls = []

        # 通过 site_menu 获取 had_urls
        def get_url(menu, had_urls):
            if 'url' in menu:
                had_urls.append(menu['url'])
            if 'menus' in menu:
                for m in menu['menus']:
                    get_url(m, had_urls)

        get_url({'menus': site_menu}, had_urls)
        # 生成 nav_menu
        nav_menu = OrderedDict()
        # 循环获取 self.admin_site._registry
        for model, model_admin in self.admin_site._registry.items():
            # 检查 model_admin 是否有 hidden_menu 属性，有的话跳过循环
            if getattr(model_admin, 'hidden_menu', False):
                continue
            # 生成 model_dict
            model_dict = {
                'title': smart_text(capfirst(model._meta.verbose_name_plural)),
                # 'url': self.get_model_url(model, name='changelist'),
                'url': '#',
                'icon': self.get_model_icon(model),
                'perm': self.get_model_perm(model, 'view'),
                'order': model_admin.order,
            }
            # 如果 model_dict['url'] 已经在 had_urls 里则跳过循环
            if model_dict['url'] in had_urls:
                continue
            # 将 model_dict 放入 nav_menu
            app_icon = None
            app_label = model._meta.app_label
            app_key = f'apps:{app_label}'
            if app_key in nav_menu:
                nav_menu[app_key]['menus'].append(model_dict)
            else:
                lower_app_label = app_label.lower()
                # 获取 app_title 和 app_icon
                if lower_app_label in self.apps_label_title:
                    app_title = self.apps_label_title[lower_app_label]
                else:
                    app_title = smart_text(apps.get_app_config(app_label).verbose_name)
                if lower_app_label in self.apps_icons:
                    app_icon = self.apps_icons[lower_app_label]
                nav_menu[app_key] = {
                    'title': app_title,
                    'menus': [model_dict],
                }
            # 设置 first_icon 和 first_url 到 app_menu
            app_menu = nav_menu[app_key]
            if app_icon:
                app_menu['first_icon'] = app_icon
            elif (
                    'first_icon' not in app_menu
                    or app_menu['first_icon'] == self.default_model_icon
            ) and model_dict['icon']:
                app_menu['first_icon'] = model_dict['icon']
            if 'first_url' not in app_menu and model_dict['url']:
                app_menu['first_url'] = model_dict['url']
        # menus 排序
        for menu in nav_menu.values():
            menu['menus'].sort(key=sortkeypicker(['order', 'title']))
        # nav_menu 排序
        nav_menu = list(nav_menu.values())
        nav_menu.sort(key=lambda x: x['title'])
        # 将 nav_menu 加入 site_menu
        site_menu.extend(nav_menu)
        return site_menu

    @filter_hook
    def get_context(self):
        context = super(CommAdminView, self).get_context()
        # 获取 nav_menu
        if not settings.DEBUG and 'nav_menu' in self.request.session:
            nav_menu = json.loads(self.request.session['nav_menu'])
        else:
            menus = copy.copy(self.get_nav_menu())

            # 过滤没有权限的 menu
            def check_menu_permission(item):
                need_perm = item.pop('perm', None)
                if need_perm is None:
                    return True
                elif callable(need_perm):
                    return need_perm(self.user)
                elif need_perm == 'super':
                    return self.user.is_superuser
                else:
                    return self.user.has_perm(need_perm)

            def filter_item(item):
                if 'menus' in item:
                    before_filter_length = len(item['menus'])
                    item['menus'] = [filter_item(i) for i in item['menus'] if check_menu_permission(i)]
                    after_filter_length = len(item['menus'])
                    if after_filter_length == 0 and before_filter_length > 0:
                        return None
                return item
            nav_menu = [filter_item(item) for item in menus if check_menu_permission(item)]
            # 过滤空的 menu
            nav_menu = list(filter(lambda x: x, nav_menu))
            # 把 nav_menu 放入 session
            if not settings.DEBUG:
                self.request.session['nav_menu'] = json.dumps(nav_menu, cls=JSONEncoder, ensure_ascii=False)
                self.request.session.modified = True

        # 设置被选中的 menu
        def check_selected(menu, path):
            selected = False
            if 'url' in menu:
                chop_index = menu['url'].find('?')
                if chop_index == -1:
                    selected = path.startswith(menu['url'])
                else:
                    selected = path.startswith(menu['url'][chop_index:])
            if 'menus' in menu:
                for m in menu['menus']:
                    _s = check_selected(m, path)
                    if _s:
                        selected = True
            if selected:
                menu['selected'] = selected
            return selected
        for menu in nav_menu:
            check_selected(menu, self.request.path)

        context.update({
            'menu_template': self.menu_template,
            'nav_menu': nav_menu,
            'site_title': self.site_title,
            'site_footer': self.site_footer,
            'breadcrumbs': self.get_breadcrumb()
        })
        return context

    @filter_hook
    def get_model_icon(self, model):
        # 通过 global_models_icon 获取 icon
        icon = self.global_models_icon.get(model)
        # 如果 icon 为 None 则通过 admin_site 的 model_icon 获取
        if icon is None and hasattr(self.admin_site, 'model_icon'):
            icon = self.admin_site.model_icon
        return icon

    @filter_hook
    def get_breadcrumb(self):
        return [{'url': self.get_admin_url('index'), 'title': _('Home')}]


class ModelAdminView(CommAdminView):

    fields = None
    exclude = None
    ordering = None
    model = None
    remove_permissions = []

    def __init__(self, request, *args, **kwargs):
        self.opts = self.model._meta
        self.app_label = self.model._meta.app_label
        self.model_name = self.model._meta.model_name
        self.model_info = (self.app_label, self.model_name)

        super(ModelAdminView, self).__init__(request, *args, **kwargs)

    @filter_hook
    def get_context(self):
        new_context = {
            'opts': self.opts,
            'app_label': self.app_label,
            'model_name': self.model_name,
            'verbose_name': force_text(self.opts.verbose_name),
            'model_icon': self.get_model_icon(self.model),
        }
        context = super(ModelAdminView, self).get_context()
        context.update(new_context)
        return context

    @filter_hook
    def get_breadcrumb(self):
        bcs = super(ModelAdminView, self).get_breadcrumb()
        item = {'title': self.opts.verbose_name_plural}
        if self.has_view_permission():
            item['url'] = self.model_admin_url('changelist')
        bcs.append(item)
        return bcs
    
    @filter_hook
    def get_object(self, object_id):
        """
        Get model object instance by object_id, used for change admin view
        """
        # first get base admin view property queryset, return default model queryset
        model = self.model
        try:
            object_id = model._meta.pk.to_python(object_id)
            return model.objects.get(pk=object_id)
        except (model.DoesNotExist, ValidationError):
            return None

    @filter_hook
    def get_object_url(self, obj):
        if self.has_change_permission(obj):
            return self.model_admin_url('change', getattr(obj, self.opts.pk.attname))
        elif self.has_view_permission(obj):
            return self.model_admin_url('detail', getattr(obj, self.opts.pk.attname))
        else:
            return None

    def model_admin_url(self, name, *args, **kwargs):
        return reverse(
            f'{self.admin_site.app_name}:{self.opts.app_label}_{self.model_name}_{name}', 
            args=args, 
            kwargs=kwargs
        )

    def get_model_perms(self):
        """
        Returns a dict of all perms for this model. This dict has the keys
        ``add``, ``change``, and ``delete`` mapping to the True/False for each
        of those actions.
        """
        return {
            'view': self.has_view_permission(),
            'add': self.has_add_permission(),
            'change': self.has_change_permission(),
            'delete': self.has_delete_permission(),
        }

    def get_template_list(self, template_name):
        opts = self.opts
        return (
            f'xadmin/{opts.app_label}/{opts.object_name.lower()}/{template_name}',
            f'xadmin/{opts.app_label}/{template_name}',
            f'xadmin/{template_name}',
        )

    def get_ordering(self):
        """
        Hook for specifying field ordering.
        """
        return self.ordering or ()  # otherwise we might try to *None, which is bad ;)

    @filter_hook
    def queryset(self):
        """
        Returns a QuerySet of all model instances that can be edited by the
        admin site. This is used by changelist_view.
        """
        return self.model._default_manager.get_queryset()

    def has_view_permission(self, obj=None):
        view_codename = get_permission_codename('view', self.opts)
        change_codename = get_permission_codename('change', self.opts)

        return ('view' not in self.remove_permissions) and (
                self.user.has_perm(f'{self.app_label}.{view_codename}') or
                self.user.has_perm(f'{self.app_label}.{change_codename}')
        )

    def has_add_permission(self):
        codename = get_permission_codename('add', self.opts)
        return ('add' not in self.remove_permissions) and self.user.has_perm(f'{self.app_label}.{codename}')

    def has_change_permission(self, obj=None):
        codename = get_permission_codename('change', self.opts)
        return ('change' not in self.remove_permissions) and self.user.has_perm(f'{self.app_label}.{codename}')

    def has_delete_permission(self, request=None, obj=None):
        codename = get_permission_codename('delete', self.opts)
        return ('delete' not in self.remove_permissions) and self.user.has_perm(f'{self.app_label}.{codename}')
