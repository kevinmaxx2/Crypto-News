from django.urls import path
from .views import register_view, login_view, logout_view, home_view, get_crypto_data

urlpatterns = [
    path('', home_view, name='home'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('api/crypto-data/', get_crypto_data, name='crypto-data')
]
