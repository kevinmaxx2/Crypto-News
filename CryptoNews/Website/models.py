from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20)

    def __str__(self):
        return self.email
    
    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',  # Changed related_name
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_permissions_set',  # Changed related_name
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )