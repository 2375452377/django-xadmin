import datetime
import decimal
import functools
from functools import update_wrapper
from inspect import getfullargspec

from django import forms
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.decorators import classonlymethod
from django.utils.encoding import force_text, smart_text
from django.utils.functional import Promise
from django.views import View

from xadmin.util import vendor


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
    def render_to_response(self, content, response_type='json'):
        if response_type == 'json':
            return JsonResponse(data=content, encoder=JSONEncoder)
        return HttpResponse(content)

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
        super(BaseAdminView, self).__init__()
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
