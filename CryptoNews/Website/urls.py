from django.urls import path
from .views import register_view, login_view, logout_view, home_view, get_crypto_data, CustomLoginView, register, portfolio_view, settings_view, CustomLogoutView, ajax_login_view


urlpatterns = [
    path('', home_view, name='home'),
    path('register/', register_view, name='register'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('ajax_login/', ajax_login_view, name='ajax_login'),
    path('api/crypto-data/', get_crypto_data, name='crypto-data'),
    path('portfolio/', portfolio_view, name='portfolio'),
    path('settings/', settings_view, name='settings'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
]
