from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class DepartmentScopedMixin(LoginRequiredMixin):
    """
    Restrict queryset to the current user's department, unless superuser.
    Model must have a department field — override `department_field` if it's
    named something other than 'owner_dept'.
    """
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        if not user.department_id:
            return qs.none()
        return qs.filter(**{self.department_field: user.department})


class HODOrSuperuserMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only HOD users or superusers may access these views."""

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_hod)