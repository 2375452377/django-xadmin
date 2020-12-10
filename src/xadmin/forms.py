from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import ugettext_lazy, ugettext as _

ERROR_MESSAGE = ugettext_lazy(
    'Please enter the correct username and password '
    'for a staff account. Note that both fields are case-sensitive.'
)


class AdminAuthenticationForm(AuthenticationForm):
    """
    A custom authentication form used in the admin app.
    """

    def get_invalid_login_error(self):
        username = self.cleaned_data.get('username')
        message = ERROR_MESSAGE
        if '@' in username:
            User = get_user_model()
            # Mistakenly entered e-mail address instead of username? Look it up.
            try:
                user = User.object.get(email=username)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                # Nothing to do here, moving along.
                pass
            else:
                password = self.cleaned_data.get('password')
                if user.check_password(password):
                    message = _("Your e-mail address is not your username. Try '%s' instead.") % user.username
        raise forms.ValidationError(message)

    def confirm_login_allowed(self, user):
        if not user.is_active or not user.is_staff:
            raise forms.ValidationError(ERROR_MESSAGE)
