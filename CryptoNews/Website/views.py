from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .forms import CustomUserCreationForm, EmailAuthenticationForm
import requests  # Import requests module
from django.core.cache import cache, caches
from django.utils import timezone
import time
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.views.decorators.csrf import csrf_exempt
import json
from django.db import IntegrityError
# Create your views here.
def home_view(request):
    return render(request, 'home.html')

cache = caches['default']
def get_crypto_data(request):
    cache_key = 'crypto_data'
    cache_time = 300  # Cache data for 5 minutes (300 seconds)
    data = cache.get(cache_key)

    if not data:
        url = 'https://api.coingecko.com/api/v3/coins/markets'
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 10,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '24h'
        }
        response = requests.get(url, params=params)
        data = response.json()

        transformed_data = [
            {
                'name': crypto['name'],
                'symbol': crypto['symbol'].upper(),
                'price': _format_price(crypto['current_price']),
                'marketcap': _format_marketcap(crypto['market_cap']),
                'image': crypto['image']
            }
            for crypto in data
        ]

        cache.set(cache_key, transformed_data, cache_time)
        data = transformed_data

    return JsonResponse(data, safe=False)

def _format_price(price):
    # Convert price to float
    price_float = float(price)
    
    # Round up if decimal part is >= 0.60
    if price_float % 1 >= 0.60:
        return f"{int(price_float) + 1:,}"
    else:
        return f"{int(price_float):,}"

def _format_marketcap(market_cap):
    if market_cap >= 1_000_000_000:
        return f"{round(market_cap / 1_000_000_000)}B"
    elif market_cap >= 1_000_000:
        return f"{round(market_cap / 1_000_000)}M"
    else:
        return f"{market_cap}"


def login_view(request):
    if request.method == 'POST':
        form = EmailAuthenticationForm(request, request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = EmailAuthenticationForm(request)
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True, 'message': 'Registration successful!'})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)
    
class CustomLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = 'login.html'

@csrf_exempt
def register_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            form = CustomUserCreationForm({
                'email': data['email'],
                'phone_number': data['phone_number'],
                'password1': data['password'],
                'password2': data['confirmPassword']
            })
            if form.is_valid():
                user = form.save()
                return JsonResponse({'success': True, 'message': 'User registered successfully'})
            else:
                errors = form.errors
                return JsonResponse({'success': False, 'errors': errors}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON request'}, status=400)
        except IntegrityError as e:
            return JsonResponse({'success': False, 'message': 'Username already exists.'}, status=400)
    else:
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)