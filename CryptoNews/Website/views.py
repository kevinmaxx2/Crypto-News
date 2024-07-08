from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .forms import UserCreationForm
import requests  # Import requests module

# Create your views here.
def home_view(request):
    return render(request, 'home.html')

def get_crypto_data(request):
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 10,
        'page': 1,
        'sparkline': False
    }
    response = requests.get(url, params=params)  # Correct function name
    data = response.json()

    transformed_data = [
        {
            'name': crypto['name'],
            'symbol': crypto['symbol'].upper(),
            'price': f"{crypto['current_price']:,.2f}",
            'marketcap': f"{crypto['market_cap']:,.0f}"
        }
        for crypto in data
    ]
    return JsonResponse(transformed_data, safe=False)

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('home')
        else:
            return render(request, 'login.html', {'error': 'Invalid username or password'})
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('home')
