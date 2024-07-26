import requests  # Import requests module
import time
import json
import logging
import io
import base64
import matplotlib
import random
import matplotlib.dates as mdates
matplotlib.use('Agg')
import re
from datetime import datetime, timedelta
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
        coin_map = {}

        for crypto in data:
            symbol = crypto.get('symbol', '').upper()
            coin_id = crypto.get('id', '')
            image_url = crypto.get('image', '') or '/static/default_crypto_image.png'
            
            transformed_data.append({
                'name': crypto.get('name', 'Unknown'),
                'symbol': symbol,
                'price': sanitize_price(crypto.get('current_price', 'N/A')),
                'price_change_percentage_24h': crypto.get('price_change_percentage_24h', 'N/A'),
                'marketcap': _format_marketcap(crypto.get('market_cap', 0)),
                'image': image_url
            })

            if symbol and coin_id:
                coin_map[symbol] = coin_id

        cache.set('crypto_data', (transformed_data, coin_map), timeout=60*5)
        logger.debug(f'Fetched and cached new data. Sample: {transformed_data[:2]}')
        return transformed_data, coin_map

    except requests.RequestException as e:
        logger.error(f'Error fetching data from CoinGecko: {e}')
        return [], {}
    
def get_crypto_data(request):
    data, _ = fetch_and_transform_crypto_data()
    return JsonResponse(data, safe=False)


def get_crypto_list_data(request):
    data, _ = fetch_and_transform_crypto_data()
    return JsonResponse(data, safe=False)

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
    transformed_data, coin_map = fetch_and_transform_crypto_data()
    
    if isinstance(transformed_data, list):
        dropdown_data = [{'symbol': crypto.get('symbol', ''), 'name': crypto.get('name', '')} for crypto in transformed_data]
        logger.debug(f"Dropdown Data: {dropdown_data}")
    else:
        logger.error(f"Unexpected data format in transformed_data: {transformed_data}")
        dropdown_data = []

    return dropdown_data

def _fetch_current_price(crypto_symbols, coin_map):
    if not isinstance(coin_map, dict):
        raise ValueError("coin_map must be a dictionary")
    
    missing_symbols = [symbol for symbol in crypto_symbols if symbol not in coin_map]
    if missing_symbols:
        raise ValueError(f"Missing symbols in coin_map: {missing_symbols}")
    
    cache_key = 'current_prices'
    cached_data = cache.get(cache_key)
    if cached_data:
        return {symbol: cached_data.get(symbol, 0) for symbol in crypto_symbols}

    url = 'https://api.coingecko.com/api/v3/simple/price'
    params = {
        'ids': ','.join([coin_map.get(symbol, '') for symbol in crypto_symbols]),
        'vs_currencies': 'usd'
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        prices = response.json()
        cache.set(cache_key, prices, timeout=3600)  # Cache for 1 hour
        return {symbol: prices.get(coin_map.get(symbol, ''), {}).get('usd', 0) for symbol in crypto_symbols}
    except requests.RequestException as e:
        logger.error(f"Error fetching current prices: {str(e)}")
        return {symbol: 0 for symbol in crypto_symbols}

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
    logger.debug("Starting portfolio view")

    crypto_data, coin_map = fetch_and_transform_crypto_data()
    portfolios = Portfolio.objects.filter(user=request.user)

    portfolio_data = []
    total_value = Decimal('0')
    total_profit_loss = Decimal('0')

    for portfolio in portfolios:
        try:
            current_price = _fetch_current_price([portfolio.crypto_symbol], coin_map)[portfolio.crypto_symbol]
            current_price_decimal = Decimal(current_price)
            
            current_value = current_price_decimal * portfolio.amount_owned
            profit_loss = current_value - (portfolio.purchase_price * portfolio.amount_owned)
            profit_loss_percentage = (profit_loss / (portfolio.purchase_price * portfolio.amount_owned)) * 100

            portfolio_entry = {
                'id': portfolio.id,
                'crypto_name': portfolio.crypto_name,
                'crypto_symbol': portfolio.crypto_symbol,
                'amount_owned': portfolio.amount_owned,
                'purchase_price': portfolio.purchase_price,
                'current_price': current_price_decimal,
                'current_value': current_value,
                'profit_loss': profit_loss,
                'profit_loss_percentage': profit_loss_percentage
            }
            portfolio_data.append(portfolio_entry)
            
            total_value += current_value
            total_profit_loss += profit_loss

        except Exception as e:
            logger.error(f"Error processing portfolio {portfolio.crypto_symbol}: {e}")

    # Sort portfolio_data by current_value (descending)
    portfolio_data.sort(key=lambda x: x['current_value'], reverse=True)

    context = {
        'portfolio_data': portfolio_data,
        'total_value': total_value,
        'total_profit_loss': total_profit_loss,
        'total_profit_loss_percentage': (total_profit_loss / total_value) * 100 if total_value else 0,
        'dropdown_data': fetch_dropdown_data(),
        'pie_chart': generate_pie_chart(portfolio_data),
        'valuation_chart': generate_valuation_chart(calculate_valuation_over_time(portfolio_data, crypto_data, coin_map))
    }

    return render(request, 'portfolio.html', context)

def calculate_valuation_over_time(portfolio_data, crypto_data, coin_map):
    logger.debug("Calculating valuation over time")
    
    dates = ['7 days ago', '30 days ago', '180 days ago', '365 days ago']
    days_ago_list = [7, 30, 180, 365]
    valuation_over_time = {date: Decimal('0') for date in dates}
    
    crypto_symbols = list(set(item['crypto_symbol'] for item in portfolio_data))
    
    logger.debug(f"Fetching historical data for symbols: {crypto_symbols} over days: {days_ago_list}")
    historical_prices = fetch_historical_data_bulk(crypto_symbols, days_ago_list, coin_map)
    
    for item in portfolio_data:
        symbol = item['crypto_symbol']
        amount_owned = Decimal(item['amount_owned'])
        
        if symbol not in historical_prices:
            logger.warning(f"No historical data found for symbol {symbol}")
            continue
        
        for idx, date in enumerate(dates):
            if idx >= len(historical_prices[symbol]):
                logger.warning(f"No price data available for {symbol} on {date}")
                continue
            
            price = Decimal(historical_prices[symbol][idx])
            if price > 0:
                valuation = price * amount_owned
                valuation_over_time[date] += valuation
                logger.debug(f"Added valuation for {symbol} on {date}: {valuation}")
            else:
                logger.warning(f"Invalid price for {symbol} on {date}: {price}")
    
    # Check for any periods with zero valuation
    for date, value in valuation_over_time.items():
        if value == 0:
            logger.warning(f"Total valuation for {date} is zero. This may indicate missing data.")
    
    logger.debug(f"Final valuation over time: {valuation_over_time}")
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
    current_date = datetime.now().date()
    dates = []
    values = []

    # Sort the data to ensure it's in the correct order
    sorted_data = sorted(valuation_data.items(), key=lambda x: int(x[0].split()[0]), reverse=True)

    for date_str, value in sorted_data:
        days = int(date_str.split()[0])
        dates.append(current_date - timedelta(days=days))
        values.append(value)

    fig, ax = plt.subplots()
    ax.plot(dates, values, marker='o', linestyle='-', color='b')

    ax.set(xlabel='Date', ylabel='Total Value (USD)',
           title='Portfolio Valuation Over Time')
    ax.grid()

    # Format x-axis
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

    # Keep labels horizontal and adjust font size if needed
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center', fontsize=8)

    # Format y-axis to use commas as thousand separators
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close(fig)
    return f'data:image/png;base64,{image_base64}'

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
    
def fetch_historical_data_bulk(crypto_symbols, days_ago_list, coin_map):
    logger.debug(f"Fetching historical data for symbols: {crypto_symbols} over days: {days_ago_list}")

    # Ensure days_ago_list is a list of integers
    if not isinstance(days_ago_list, list) or not all(isinstance(day, int) for day in days_ago_list):
        logger.error(f"Invalid days_ago_list: {days_ago_list}")
        return {}
    
    # Prepare a dictionary to store historical prices
    historical_prices = {symbol: [0] * len(days_ago_list) for symbol in crypto_symbols}

    url_template = 'https://api.coingecko.com/api/v3/coins/{}/market_chart'
    results = {}

    try:
        for symbol in crypto_symbols:
            coin_id = coin_map.get(symbol)
            if not coin_id:
                logger.warning(f"Coin ID for symbol {symbol} not found.")
                continue

            logger.debug(f"Fetching data for {symbol} (ID: {coin_id})")

            # Fetch historical data for the maximum range needed
            params = {
                'vs_currency': 'usd',
                'days': max(days_ago_list)  # Request the maximum days_ago range
            }

            response = requests.get(url_template.format(coin_id), params=params)
            logger.debug(f"Requested URL: {response.url}")
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Response data for {symbol}: {data}")

            # Extract historical prices for each day
            prices = data.get('prices', [])
            for idx, days_ago in enumerate(days_ago_list):
                if len(prices) > days_ago:
                    historical_prices[symbol][idx] = prices[days_ago][1]  # Index 1 for price value
                    logger.debug(f"Price for {symbol} on {days_ago} days ago: {prices[days_ago][1]}")
                else:
                    logger.warning(f"Not enough data for {symbol} on {days_ago} days ago.")
            results[symbol] = historical_prices[symbol]
        
        logger.debug(f"Final historical prices: {historical_prices}")
        return results

    except requests.RequestException as e:
        logger.error(f"Error fetching historical data: {str(e)}")
        return {}
        
    
def fetch_portfolio_values(portfolio):
    values = {}
    for crypto in portfolio:
        crypto_symbol = crypto['crypto_symbol']
        values[crypto_symbol] = {
            '7d': fetch_historical_data_bulk(crypto_symbol, '7'),
            '1m': fetch_historical_data_bulk(crypto_symbol, '30'),
            '6m': fetch_historical_data_bulk(crypto_symbol, '180'),
            '1y': fetch_historical_data_bulk(crypto_symbol, '365'),
            'current': fetch_historical_data_bulk(crypto_symbol, '1')  # Latest data
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