from django.contrib.auth.mixins import LoginRequiredMixin


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