from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from .views import register_view, login_view, logout_view, home_view, get_crypto_data, CustomLoginView, register, portfolio_view, settings_view, CustomLogoutView, ajax_login_view, get_crypto_list_data
from . import views

urlpatterns = [
    path('', home_view, name='home'),
    path('register/', register_view, name='register'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('ajax_login/', ajax_login_view, name='ajax_login'),
    path('api/crypto-data/', get_crypto_data, name='crypto-data'),
    path('api/crypto-list-data/', get_crypto_list_data, name='crypto-list-data'),
    path('portfolio/', portfolio_view, name='portfolio'),
    path('add_to_portfolio/', views.add_to_portfolio, name='add_to_portfolio'),
    path('delete_portfolio/<int:portfolio_id>/', views.delete_portfolio, name='delete_portfolio'),
    path('settings/', settings_view, name='settings'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    path('check_duplicate/', views.check_duplicate, name='check_duplicate'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)