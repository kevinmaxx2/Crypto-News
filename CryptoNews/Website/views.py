import requests  # Import requests module
import time
import json
import logging
import io
import base64
import matplotlib
matplotlib.use('Agg')
from datetime import datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import User
from django.core.cache import cache, caches
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm, EmailAuthenticationForm
from django.contrib.auth import get_user_model
from Website.models import CustomUser
from .models import Portfolio
from .forms import PortfolioForm 
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import pandas as pd
# Create your views here.
def home_view(request):
    return render(request, 'home.html')

def fetch_and_transform_crypto_data():
    cached_data = cache.get('crypto_data')
    if cached_data:
        logger.debug('Returning cached data')
        return cached_data

    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 30,
        'page': 1,
        'sparkline': False,
        'price_change_percentage': '24h'
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        transformed_data = []
        for crypto in data:
            transformed_data.append({
                'name': crypto.get('name', ''),
                'symbol': crypto.get('symbol', '').upper(),
                'price': _format_price(crypto.get('current_price', 0)),
                'price_change_percentage_24h': crypto.get('price_change_percentage_24h', 'N/A'),
                'marketcap': _format_marketcap(crypto.get('market_cap', 0)),
                'image': crypto.get('image', '')
            })

        cache.set('crypto_data', transformed_data, timeout=3600)  # Cache for 1 hour
        logger.debug('Fetched and cached new data')
        return transformed_data

    except requests.RequestException as e:
        logger.error(f'Error fetching data: {str(e)}')
        return []  # Return an empty list in case of an error
    
def get_crypto_data(request):
    cache_key = 'crypto_data'
    cache_time = 300  # Cache data for 5 minutes (300 seconds)
    data = cache.get(cache_key)

    if not data:
        transformed_data = fetch_and_transform_crypto_data()
        if not isinstance(transformed_data, dict):  # Check if it's not an error dictionary
            cache.set(cache_key, transformed_data, cache_time)
        data = transformed_data

    return JsonResponse(data, safe=False)

def get_crypto_list_data(request):
    cache_key = 'crypto_data'
    cache_time = 300  # Cache data for 5 minutes (300 seconds)
    data = cache.get(cache_key)

    if not data:
        transformed_data = fetch_and_transform_crypto_data()
        if not isinstance(transformed_data, dict):  # Check if it's not an error dictionary
            cache.set(cache_key, transformed_data, cache_time)
        data = transformed_data

    return JsonResponse(data, safe=False)

logger = logging.getLogger('CryptoNews')

@login_required
def get_portfolio_data(request):
    cache_key = 'crypto_data'
    cache_time = 300  # Cache data for 5 minutes (300 seconds)
    data = cache.get(cache_key)

    if not data:
        transformed_data = fetch_and_transform_crypto_data()
        if not isinstance(transformed_data, dict) and 'error' not in transformed_data:  # Check if it's not an error dictionary
            cache.set(cache_key, transformed_data, cache_time)
        data = transformed_data

    # Debugging: Log data retrieved
    logger.debug(f"Fetched crypto data: {data}")

    portfolios = Portfolio.objects.filter(user=request.user)
    portfolio_data = []

    for portfolio in portfolios:
        try:
            current_value = _calculate_current_value(portfolio.crypto_name, data, portfolio.amount_owned)
            profit_loss = _calculate_profit_loss(portfolio.crypto_name, portfolio.purchase_price, data, portfolio.amount_owned)
            portfolio_data.append({
                'crypto_name': portfolio.crypto_name,
                'amount_owned': portfolio.amount_owned,
                'purchase_price': portfolio.purchase_price,
                'current_value': current_value,
                'profit_loss': profit_loss
            })
        except Exception as e:
            logger.error(f"Error calculating portfolio data for {portfolio.crypto_name}: {str(e)}")

    # Ensure data is a dictionary before adding 'portfolio' key
    if not isinstance(data, dict):
        data = {'data': data}  # Handle appropriately if data is a list or another type
    
    data['portfolio'] = portfolio_data

    return JsonResponse(data, safe=False)

def fetch_dropdown_data():
    transformed_data = fetch_and_transform_crypto_data()  # Fetch cryptocurrency data
    if isinstance(transformed_data, list):
        dropdown_data = [{'symbol': crypto.get('symbol', ''), 'name': crypto.get('name', '')} for crypto in transformed_data]
        logger.debug(f"Dropdown Data: {dropdown_data}")
    else:
        logger.error(f"Unexpected data format in transformed_data: {transformed_data}")
        dropdown_data = []

    return dropdown_data

def _calculate_current_value(crypto_name, crypto_data, amount_owned):
    for crypto in crypto_data:
        if crypto['symbol'].upper() == crypto_name.upper():
            current_price = float(crypto['price'].replace(',', '').replace('$', ''))  # Extract and convert current price
            amount_owned = float(amount_owned)
            return round(amount_owned * current_price, 2)
    return 0

def _calculate_profit_loss(crypto_name, purchase_price, crypto_data, amount_owned):
    for crypto in crypto_data:
        if crypto['symbol'].upper() == crypto_name.upper():
            current_price = float(crypto['price'].replace(',', '').replace('$', ''))  # Extract and convert current price
            amount_owned = float(amount_owned)
            purchase_price = float(purchase_price)  # Convert purchase price to float
            return round((current_price - purchase_price) * amount_owned, 2)
    return 0
@login_required
def add_to_portfolio(request):
    if request.method == 'POST':
        crypto_symbol = request.POST.get('crypto_symbol')
        amount_owned = request.POST.get('amount_owned')
        purchase_price = request.POST.get('purchase_price')

        # Validate and save the form data
        if crypto_symbol and amount_owned and purchase_price:
            Portfolio.objects.create(
                user=request.user,
                crypto_name=crypto_symbol,
                amount_owned=float(amount_owned),  # Convert to float for consistency
                purchase_price=float(purchase_price)  # Convert to float for consistency
            )
            return redirect('portfolio')  # Redirect to the portfolio page

    # Fetch dropdown data
    dropdown_data = fetch_dropdown_data()
    logger.debug(f"Dropdown Data passed to template: {dropdown_data}")

    return render(request, 'portfolio.html', {'dropdown_data': dropdown_data})

@login_required
def delete_portfolio(request, portfolio_id):
    portfolio_entry = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    portfolio_entry.delete()
    
    # Fetch and store the updated dropdown data in the session
    dropdown_data = fetch_dropdown_data()  # Ensure this function returns the correct data
    request.session['dropdown_data'] = dropdown_data
    
    return redirect('portfolio')

def _format_price(price):

    # Convert price to float
    price_float = float(price)
    
    # Round up if decimal part is >= 0.60
    if price_float % 1 >= 0.60:
        return f"{int(price_float) + 1:,}"
    else:
        # Show two decimal places if price is lower than 100
        if price_float < 100:
            return f"{price_float:.2f}"
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

@require_POST
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True, 'message': 'Registration successful!'})
        else:
            errors = form.errors.as_json()
            # Customize error messages for specific fields if needed
            if 'email' in form.errors:
                errors['email'] = ['Email already in use. Please choose a different one.']
            if 'phone_number' in form.errors:
                errors['phone_number'] = ['Phone number already in use. Please choose a different one.']
            return JsonResponse({'success': False, 'errors': errors}, status=400)
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
    

@login_required
def portfolio_view(request):
    portfolios = Portfolio.objects.filter(user=request.user)
    portfolio_data = []

    crypto_data = fetch_and_transform_crypto_data() or []

    for portfolio in portfolios:
        portfolio_data.append({
            'id': portfolio.id,
            'crypto_name': portfolio.crypto_name,
            'crypto_symbol': portfolio.crypto_symbol,  # Ensure this field is used
            'amount_owned': portfolio.amount_owned,
            'purchase_price': portfolio.purchase_price,
            'current_value': _calculate_current_value(portfolio.crypto_symbol, crypto_data, portfolio.amount_owned),
            'profit_loss': _calculate_profit_loss(portfolio.crypto_symbol, portfolio.purchase_price, crypto_data, portfolio.amount_owned)
        })

    dropdown_data = fetch_dropdown_data() or []

    # Calculate portfolio summary
    summary, total_value = calculate_portfolio_summary(portfolio_data, crypto_data)

    # Calculate valuation over time
    valuation = calculate_valuation_over_time(portfolio_data, crypto_data)

    # Generate charts
    pie_chart = create_pie_chart(summary)
    valuation_chart = create_valuation_chart(valuation)

    pie_chart_div = pie_chart if pie_chart else ""
    valuation_chart_div = valuation_chart if valuation_chart else ""
    context = {
        'portfolios': portfolio_data,
        'dropdown_data': dropdown_data,
        'pie_chart': pie_chart_div,
        'valuation_chart': valuation_chart_div,
        'total_value': total_value
    }

    return render(request, 'portfolio.html', context)

def calculate_portfolio_summary(portfolio_data, crypto_data):
    summary = {}
    total_value = 0
    
    # Convert crypto_data to a dictionary for quick lookup
    crypto_dict = {crypto['symbol']: float(crypto['price'].replace(',', '').replace('$', '')) for crypto in crypto_data}

    for entry in portfolio_data:
        symbol = entry.get('crypto_symbol')  # Use 'crypto_symbol' instead of 'crypto_name'
        amount_owned = float(entry.get('amount_owned', 0))
        
        if symbol in crypto_dict:
            current_price = crypto_dict[symbol]
            value = current_price * amount_owned
            summary[symbol] = value
            total_value += value
        else:
            summary[symbol] = 0  # Handle cases where the symbol is not in the crypto data

    return summary, total_value

def calculate_valuation_over_time(portfolio_data, crypto_data):
    valuation = {}
    for item in portfolio_data:
        # Use 'crypto_symbol' instead of 'crypto_name'
        historical_prices = next((crypto['historical_prices'] for crypto in crypto_data if crypto['symbol'] == item['crypto_symbol']), {})
        for date, price in historical_prices.items():
            date = datetime.strptime(date, '%Y-%m-%d')
            if date not in valuation:
                valuation[date] = 0
            valuation[date] += item['amount_owned'] * price
    return sorted(valuation.items())

def create_pie_chart(summary):
    if not summary:
        return None  # Return None if no data
    
    # Create a DataFrame from the summary data
    df = pd.DataFrame(list(summary.items()), columns=['Cryptocurrency', 'Value'])
    
    # Plotting
    fig, ax = plt.subplots()
    ax.pie(df['Value'], labels=df['Cryptocurrency'], autopct='%1.1f%%')
    ax.set_title('Portfolio Composition')
    
    # Save to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    
    # Encode image to base64
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"



def create_valuation_chart(valuation):
    if not valuation:
        return None  # Return None if no data
    
    # Example data structure: Convert valuation data to a DataFrame
    df = pd.DataFrame(list(valuation.items()), columns=['Period', 'Value'])
    
    # Plotting
    fig, ax = plt.subplots()
    ax.bar(df['Period'], df['Value'])
    ax.set_xlabel('Period')
    ax.set_ylabel('Total Portfolio Value (USD)')
    ax.set_title('Portfolio Value Over Time')
    
    # Save to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    
    # Encode image to base64
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"

@login_required
def create_portfolio_view(request):
    if request.method == 'POST':
        form = PortfolioForm(request.POST)
        if form.is_valid():
            portfolio = form.save(commit=False)
            portfolio.user = request.user
            portfolio.save()
            return JsonResponse({'success': True, 'message': 'Portfolio entry added successfully'})
        else:
            errors = form.errors
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = PortfolioForm()
    
    context = {
        'form': form,
    }
    return render(request, 'create_portfolio.html', context)

@login_required
def settings_view(request):
    return render(request, 'settings.html')

class CustomLogoutView(LogoutView):
    next_page = '/'

logger = logging.getLogger('CryptoNews')

@csrf_protect
def ajax_login_view(request):
    logger.debug(f"Request method: {request.method}")
    logger.debug(f"Request headers: {request.headers}")

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        username = request.POST.get('username')
        password = request.POST.get('password')

        logger.debug(f"Username: {username}, Password: {password}")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            logger.debug("Authentication successful")
            login(request, user)  # Log the user in
            return JsonResponse({'success': True})
        else:
            logger.debug("Authentication failed")
            return JsonResponse({'success': False, 'error': 'Invalid email or password. Please try again.'})

    logger.debug("Method not allowed")
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def check_duplicate(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email', None)
        phone_number = data.get('phone_number', None)

        response_data = {
            'email_exists': CustomUser.objects.filter(email=email).exists() if email else False,
            'phone_number_exists': CustomUser.objects.filter(phone_number=phone_number).exists() if phone_number else False,
        }

        return JsonResponse(response_data)

    # Handle other HTTP methods if needed
    return JsonResponse({'error': 'POST request required'}, status=400)
def get_crypto_id_from_symbol(symbol):
    url = f'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'ids': symbol.lower()  # Use lower case for the API
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if data:
        return data[0]['id']
    return None

def fetch_historical_data(crypto_symbol, days_ago):
    # Modify the URL to use 'crypto_symbol'
    url = f'https://api.coingecko.com/api/v3/coins/{crypto_symbol}/market_chart'
    params = {
        'vs_currency': 'usd',
        'days': days_ago,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data['prices'][-1][1]  # Return the price on the last date of the given period

def fetch_portfolio_values(portfolio):
    values = {}
    for crypto in portfolio:
        crypto_symbol = crypto['crypto_symbol']
        values[crypto_symbol] = {
            '7d': fetch_historical_data(crypto_symbol, '7'),
            '1m': fetch_historical_data(crypto_symbol, '30'),
            '6m': fetch_historical_data(crypto_symbol, '180'),
            '1y': fetch_historical_data(crypto_symbol, '365'),
            'current': fetch_historical_data(crypto_symbol, '1')  # Latest data
        }
    return values

def calculate_portfolio_values(portfolio, historical_data):
    values = {
        '7d': 0,
        '1m': 0,
        '6m': 0,
        '1y': 0
    }
    for crypto in portfolio:
        symbol = crypto['crypto_symbol']
        amount_owned = crypto['amount_owned']
        for period in values.keys():
            values[period] += historical_data[symbol][period] * amount_owned
    return values