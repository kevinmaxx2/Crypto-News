from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    # Customize display fields if needed
    list_display = ['username', 'email', 'is_staff', 'is_superuser']

admin.site.register(CustomUser, CustomUserAdmin)