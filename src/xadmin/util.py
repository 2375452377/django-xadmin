from django.conf import settings
from django.forms import Media
from django.templatetags.static import static
from django.utils.translation import get_language


def xstatic(*tags):
    from .vendors import vendors
    node = vendors

    fs = []
    lang = get_language()

    for tag in tags:
        try:
            for p in tag.split('.'):
                node = node[p]
        except Exception as e:
            if tag.startswith('xadmin'):
                file_type = tag.split('.')[-1]
                if file_type in ('css', 'js'):
                    node = f'xadmin/{file_type}/{tag}'
                else:
                    raise e
            else:
                raise e

        if isinstance(node, str):
            files = node
        else:
            mode = 'dev'
            if not settings.DEBUG:
                mode = getattr(settings, 'STATIC_USE_CDN', False) and 'cdn' or 'production'

            if mode == 'cdn' and mode not in node:
                mode = 'production'
            if mode == 'production' and mode not in node:
                mode = 'dev'
            files = node[mode]

        files = type(files) in (list, tuple) and files or [files, ]
        fs.extend([f % {'lang': lang.replace('_', '-')} for f in files])

    return [f.startswith('http://') and f or static(f) for f in fs]


def vendor(*tags):
    css = {'screen': []}
    js = []
    for tag in tags:
        file_type = tag.split('.')[-1]
        files = xstatic(tag)
        if file_type == 'js':
            js.extend(files)
        elif file_type == 'css':
            css['screen'] += files
    return Media(css=css, js=js)


def sortkeypicker(keynames):
    negate = set()
    for index, key in enumerate(keynames):
        # 获取需要反向排序的 key
        if key[:1] == '-':
            keynames[index] = key[1:]
            negate.add(key[1:])

    def getit(adict):
        composite = [adict[k] for k in keynames]
        for i, (k, v) in enumerate(zip(keynames, composite)):
            if k in negate:
                composite[i] = -v
        return composite
    return getit
