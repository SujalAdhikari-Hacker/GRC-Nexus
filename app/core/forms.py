from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User, Department


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name',
                  'department', 'is_hod', 'groups')


class CustomUserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name',
                  'department', 'is_hod', 'is_active', 'groups')
        widgets = {
            'groups': forms.SelectMultiple(attrs={'size': 8}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ('name', 'parent')
