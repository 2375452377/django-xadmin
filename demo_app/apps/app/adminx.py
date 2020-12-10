from django.contrib.auth.models import User

import xadmin


class UserAdmin:
    pass


xadmin.site.register(User, UserAdmin)
