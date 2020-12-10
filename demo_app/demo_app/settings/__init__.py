from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

if DEBUG:
    from .dev import *

    # debug模式下要配置，不然找不到路径
    # 先在这个路径下查找static文件，找不到再去apps下的static目录查找
    STATICFILES_DIRS = [
        BASE_DIR / 'static',
    ]
else:
    from .prod import *

    # 这个路径只在执行python manage.py collectstatic时才用到，debug模式下没用
    STATIC_ROOT = BASE_DIR / 'static'
