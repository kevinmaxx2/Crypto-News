import requests  # Import requests module
import time
import json
import logging
import io
import base64
import matplotlib
import random
matplotlib.use('Agg')
import re
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
from decimal import Decimal, InvalidOperation
from io import BytesIO
from django.core.exceptions import ValidationError
from requests.exceptions import HTTPError
def sanitize_price(price_str):
    if not isinstance(price_str, str):
        price_str = str(price_str)  # Convert non-string inputs to string
    # Remove commas and other non-numeric characters
    cleaned_price = re.sub(r'[^\d.]', '', price_str)
    try:
        return Decimal(price_str.replace(',', ''))
    except Exception as e:
        logger.error(f"Error sanitizing price: {e}")
        return Decimal('0.00')
    
def home_view(request):
    return render(request, 'home.html')

def fetch_and_transform_crypto_data():
    logger.debug("Fetching and transforming crypto data")
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
                'price': sanitize_price(crypto.get('current_price', '0')),
                'price_change_percentage_24h': crypto.get('price_change_percentage_24h', 'N/A'),
                'marketcap': _format_marketcap(crypto.get('market_cap', 0)),
                'image': crypto.get('image', '')
            })

        cache.set('crypto_data', transformed_data, timeout=3600)  # Cache for 1 hour
        logger.debug('Fetched and cached new data')
        logger.debug(f'Transformed data: {transformed_data}')
        return transformed_data

    except requests.RequestException as e:
        logger.error(f'Error fetching data: {str(e)}')
        return []
    
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
    logger.debug("Fetching portfolio data")
    cache_key = 'crypto_data'
    cache_time = 300  # Cache data for 5 minutes (300 seconds)
    data = cache.get(cache_key)

    if not data:
        transformed_data = fetch_and_transform_crypto_data()
        if not isinstance(transformed_data, dict) and 'error' not in transformed_data:
            cache.set(cache_key, transformed_data, cache_time)
        data = transformed_data

    logger.debug(f"Fetched crypto data: {data}")

    portfolios = Portfolio.objects.filter(user=request.user)
    portfolio_data = []

    for portfolio in portfolios:
        try:
            logger.debug(f"Calculating values for portfolio: {portfolio.crypto_name}")
            current_value = _calculate_current_value(portfolio.crypto_symbol, data, portfolio.amount_owned)
            profit_loss = _calculate_profit_loss(portfolio.crypto_symbol, portfolio.purchase_price, data, portfolio.amount_owned)
            portfolio_data.append({
                'crypto_name': portfolio.crypto_name,
                'amount_owned': portfolio.amount_owned,
                'purchase_price': portfolio.purchase_price,
                'current_value': current_value,
                'profit_loss': profit_loss
            })
            logger.debug(f"Calculated data for {portfolio.crypto_name}: Current Value: {current_value}, Profit/Loss: {profit_loss}")
        except Exception as e:
            logger.error(f"Error calculating portfolio data for {portfolio.crypto_name}: {str(e)}")

    if not isinstance(data, dict):
        data = {'data': data}
    
    data['portfolio'] = portfolio_data

    return JsonResponse(data, safe=False)

def fetch_dropdown_data():
    transformed_data = fetch_and_transform_crypto_data()
    if isinstance(transformed_data, list):
        dropdown_data = [{'symbol': crypto.get('symbol', ''), 'name': crypto.get('name', '')} for crypto in transformed_data]
        logger.debug(f"Dropdown Data: {dropdown_data}")
    else:
        logger.error(f"Unexpected data format in transformed_data: {transformed_data}")
        dropdown_data = []

    return dropdown_data


def _fetch_current_price(crypto_symbol, crypto_data):
    logger.debug(f"Fetching current price for symbol: {crypto_symbol}")
    for crypto in crypto_data:
        if crypto['symbol'] == crypto_symbol:
            price_str = crypto.get('price', '0')
            price = sanitize_price(price_str)
            logger.debug(f"Found price for {crypto_symbol}: {price}")
            return price
    logger.error(f"No price found for symbol: {crypto_symbol}")
    return Decimal('0.00')  # Default value if symbol is not found in the list

def _calculate_current_value(crypto_symbol, crypto_data, amount_owned):
    current_price = _fetch_current_price(crypto_symbol, crypto_data)
    return round(amount_owned * current_price, 2)

def _calculate_profit_loss(crypto_symbol, purchase_price, crypto_data, amount_owned):
    current_price = _fetch_current_price(crypto_symbol, crypto_data)
    try:
        purchase_price = sanitize_price(purchase_price)
    except Exception as e:
        logger.error(f"Invalid purchase price format for {crypto_symbol}: {purchase_price}")
        purchase_price = Decimal('0.00')  # Default value if conversion fails

    profit_loss = (current_price - purchase_price) * amount_owned
    return round(profit_loss, 2)


@login_required
def add_to_portfolio(request):
    if request.method == 'POST':
        crypto_symbol = request.POST.get('crypto_symbol')
        amount_owned = request.POST.get('amount_owned')
        purchase_price = request.POST.get('purchase_price')

        # Fetch dropdown data
        dropdown_data = fetch_dropdown_data()
        valid_symbols = [crypto['symbol'] for crypto in dropdown_data]

        if crypto_symbol in valid_symbols and amount_owned and purchase_price:
            try:
                Portfolio.objects.create(
                    user=request.user,
                    crypto_symbol=crypto_symbol,
                    amount_owned=float(amount_owned),
                    purchase_price=float(purchase_price)
                )
                return redirect('portfolio')  # Redirect to the portfolio page
            except ValidationError as e:
                logger.error(f"Error adding portfolio: {e}")
                error_message = "There was an error processing your request. Please try again."
        else:
            logger.error(f"Invalid crypto_symbol: {crypto_symbol} or missing data")
            error_message = "Invalid input. Please make sure all fields are filled correctly."

        dropdown_data = fetch_dropdown_data()
        return render(request, 'portfolio.html', {
            'dropdown_data': dropdown_data,
            'error': error_message
        })

    dropdown_data = fetch_dropdown_data()
    return render(request, 'portfolio.html', {'dropdown_data': dropdown_data})

@login_required
def delete_portfolio(request, portfolio_id):
    portfolio_entry = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    portfolio_entry.delete()
    
    # Fetch and store the updated dropdown data in the session
    dropdown_data = fetch_dropdown_data()
    request.session['dropdown_data'] = dropdown_data
    
    return redirect('portfolio')

def _format_price(price):
    if not isinstance(price, (float, int, Decimal)):
        logger.error(f"Invalid price type: {type(price)}")
        return '0.00'

    price_float = float(price)
    if price_float % 1 >= 0.60:
        return f"{int(price_float) + 1:,}"
    else:
        if price_float < 100:
            return f"{price_float:.2f}"
        else:
            return f"{int(price_float):,}"

# Format Market Cap
def _format_marketcap(market_cap):
    if market_cap >= 1_000_000_000:
        return f"{round(market_cap / 1_000_000_000, 1)}B"
    elif market_cap >= 1_000_000:
        return f"{round(market_cap / 1_000_000, 1)}M"
    elif market_cap >= 1_000:
        return f"{round(market_cap / 1_000, 1)}K"
    else:
        return str(market_cap)

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
    crypto_data = fetch_and_transform_crypto_data()
    portfolios = Portfolio.objects.filter(user=request.user)

    portfolio_data = []
    for portfolio in portfolios:
        current_price = _fetch_current_price(portfolio.crypto_symbol, crypto_data)
        current_value = Decimal(current_price) * portfolio.amount_owned
        profit_loss = current_value - (portfolio.purchase_price * portfolio.amount_owned)

        portfolio_data.append({
            'id': portfolio.id,
            'crypto_name': portfolio.crypto_name,
            'crypto_symbol': portfolio.crypto_symbol,
            'amount_owned': portfolio.amount_owned,
            'purchase_price': portfolio.purchase_price,
            'purchase_date': portfolio.purchase_date,
            'current_price': Decimal(current_price),
            'current_value': current_value,
            'profit_loss': profit_loss,
        })

    # Fetch the coin map
    coin_map = get_available_coins()

    # Pass coin_map to calculate_valuation_over_time
    valuation_data = calculate_valuation_over_time(portfolio_data, crypto_data, coin_map)
    valuation_chart_url = generate_valuation_chart(valuation_data)

    context = {
        'portfolio_data': portfolio_data,
        'dropdown_data': fetch_dropdown_data(),
        'pie_chart': generate_pie_chart(portfolio_data),
        'valuation_chart': valuation_chart_url,
    }

    return render(request, 'portfolio.html', context)

def calculate_valuation_over_time(portfolio_data, crypto_data, coin_map):
    dates = ['7 days ago', '30 days ago', '180 days ago', '365 days ago']
    valuation_over_time = {date: 0 for date in dates}

    for item in portfolio_data:
        crypto_info = next((crypto for crypto in crypto_data if crypto['symbol'] == item['crypto_symbol']), None)

        if crypto_info:
            historical_prices = {date: fetch_historical_data(item['crypto_symbol'], days_ago, coin_map) for date, days_ago in zip(dates, [7, 30, 180, 365])}

            if not any(historical_prices.values()):  # Check if all values are zero
                logger.warning(f"Incomplete historical prices for symbol {item['crypto_symbol']}")

            for date in dates:
                price = historical_prices.get(date, 0)
                if price > 0:  # Only accumulate if price is valid
                    valuation_over_time[date] += Decimal(price) * item['amount_owned']
                else:
                    logger.warning(f"Invalid price for {item['crypto_symbol']} on {date}: {price}")

        else:
            logger.warning(f"No data found for symbol {item['crypto_symbol']}")

    logger.debug(f"Valuation over time: {valuation_over_time}")
    return valuation_over_time


def calculate_valuation_over_time(portfolio_data, crypto_data, coin_map):
    dates = ['7 days ago', '30 days ago', '180 days ago', '365 days ago']
    valuation_over_time = {date: 0 for date in dates}

    for item in portfolio_data:
        crypto_info = next((crypto for crypto in crypto_data if crypto['symbol'] == item['crypto_symbol']), None)

        if crypto_info:
            historical_prices = {date: fetch_historical_data(item['crypto_symbol'], days_ago, coin_map) for date, days_ago in zip(dates, [7, 30, 180, 365])}

            if not any(historical_prices.values()):  # Check if all values are zero
                logger.warning(f"Incomplete historical prices for symbol {item['crypto_symbol']}")

            for date in dates:
                price = historical_prices.get(date, 0)
                if price > 0:  # Only accumulate if price is valid
                    valuation_over_time[date] += float(price) * float(item['amount_owned'])
                else:
                    logger.warning(f"Invalid price for {item['crypto_symbol']} on {date}: {price}")

        else:
            logger.warning(f"No data found for symbol {item['crypto_symbol']}")

    logger.debug(f"Valuation over time: {valuation_over_time}")
    return valuation_over_time

def generate_pie_chart(portfolio_data):
    labels = [entry['crypto_symbol'] for entry in portfolio_data]
    sizes = [entry['current_value'] for entry in portfolio_data]

    fig, ax = plt.subplots()
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close(fig)
    return f'data:image/png;base64,{image_base64}'


def generate_valuation_chart(valuation_data):
    dates = list(valuation_data.keys())
    values = list(valuation_data.values())

    fig, ax = plt.subplots()
    ax.plot(dates, values, marker='o', linestyle='-', color='b')

    ax.set(xlabel='Date', ylabel='Total Value (USD)',
           title='Portfolio Valuation Over Time')
    ax.grid()
    plt.xticks(rotation=45)  # Rotate x-axis labels for better readability

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close(fig)
    return f'data:image/png;base64,{image_base64}'

def create_portfolio_view(request):
    if request.method == 'POST':
        form = PortfolioForm(request.POST)
        if form.is_valid():
            portfolio = form.save(commit=False)
            crypto_symbol = form.cleaned_data.get('crypto_symbol')

            # Fetch dropdown data
            dropdown_data = fetch_dropdown_data()
            valid_symbols = [crypto['symbol'] for crypto in dropdown_data]

            if crypto_symbol in valid_symbols:
                portfolio.user = request.user
                portfolio.save()
                logger.debug(f"Portfolio entry added: {portfolio}")
                return JsonResponse({'success': True, 'message': 'Portfolio entry added successfully'})
            else:
                logger.error(f"Invalid crypto_symbol: {crypto_symbol}")
                return JsonResponse({'success': False, 'errors': {'crypto_symbol': 'Invalid cryptocurrency symbol'}}, status=400)
        else:
            errors = form.errors
            logger.error(f"Form errors: {errors}")
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

def get_available_coins():
    url = 'https://api.coingecko.com/api/v3/coins/list'
    try:
        response = requests.get(url)
        response.raise_for_status()
        coins = response.json()
        logger.debug(f"Available coins fetched: {coins[:10]}")  # Log first 10 entries for a quick check

        # Create a dictionary to hold the mappings with some known correct mappings
        coin_map = {}
        known_coins = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'LTC': 'litecoin',
            'XRP': 'ripple',
            'BCH': 'bitcoin-cash',
            'ADA': 'cardano',
            'DOT': 'polkadot',
            'LINK': 'chainlink',
            'BNB': 'binancecoin',
            'USDT': 'tether',
            'DOGE': 'dogecoin',
            # Add more known mappings as needed
        }

        # Add known mappings to the coin_map first
        for symbol, coin_id in known_coins.items():
            coin_map[symbol] = coin_id

        # Update the coin_map with API data, ensuring known mappings are not overwritten
        for coin in coins:
            symbol = coin['symbol'].upper()
            if symbol not in coin_map:
                coin_map[symbol] = coin['id']

        logger.debug(f"Coin map created: {coin_map}")

        # Check for specific symbols and their corresponding IDs
        for symbol, expected_id in known_coins.items():
            actual_id = coin_map.get(symbol)
            if actual_id == expected_id:
                logger.debug(f"Symbol {symbol} correctly maps to {expected_id}")
            else:
                logger.warning(f"Symbol {symbol} maps to {actual_id} instead of {expected_id}")

        return coin_map
    except requests.RequestException as e:
        logger.error(f"Error fetching available coins: {str(e)}")
        return {}
    
def fetch_historical_data(crypto_symbol, days_ago, coin_map):
    coin_id = coin_map.get(crypto_symbol.upper())  # Ensure we are using upper case for lookup
    if not coin_id:
        logger.error(f"Symbol {crypto_symbol} not found in available coins")
        return 0
    
    cache_key = f'{coin_id}_price_{days_ago}'
    cached_price = cache.get(cache_key)
    if cached_price is not None:
        logger.debug(f"Cache hit for {cache_key}: {cached_price}")
        return cached_price

    logger.debug(f"Fetching historical data for symbol: {crypto_symbol}, days ago: {days_ago}")
    url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart'
    params = {
        'vs_currency': 'usd',
        'days': days_ago,
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['prices']:
            price = data['prices'][-1][1]
            cache.set(cache_key, price, timeout=3600)  # Cache for 1 hour
            logger.debug(f"Price for {coin_id} on {days_ago} days ago: {price}")
            return price
        else:
            logger.warning(f"No price data available for {coin_id} for {days_ago} days ago")
            return 0
    except requests.RequestException as e:
        logger.error(f"Error fetching historical data for {coin_id}: {str(e)}")
        return 0
        
    
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