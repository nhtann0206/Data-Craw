import requests
import os
import sys
import pandas as pd
from datetime import datetime

def test_alpha_vantage_api():
    """Test Alpha Vantage API connection and functionality"""
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("ERROR: ALPHA_VANTAGE_API_KEY environment variable not found")
        return

    print(f"Using API key: {api_key[:4]}...{api_key[-4:]}")
    
    # Test simple request
    symbol = "AAPL"
    interval = "60min"
    
    url = "https://www.alphavantage.co/query"
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': interval,
        'outputsize': 'compact',  # Use compact to minimize API usage
        'apikey': api_key
    }
    
    print(f"Testing request for {symbol} with {interval} interval...")
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Check for API error messages
        if "Error Message" in data:
            print(f"API ERROR: {data['Error Message']}")
            return
            
        # Check for rate limit note
        if "Note" in data:
            print(f"API NOTE: {data['Note']}")
        
        # Check if there's an Information message (API key limit)
        if "Information" in data:
            print(f"API INFORMATION: {data['Information']}")
            print("Recommended: Try using Yahoo Finance instead")
            return
        
        # Check time series data
        time_series_key = f"Time Series ({interval})"
        if time_series_key not in data:
            print(f"ERROR: Time series data not found. Response keys: {list(data.keys())}")
            return
        
        time_series = data[time_series_key]
        if not time_series:
            print("ERROR: Empty time series data received")
            return
        
        # Print basic statistics about the data
        num_data_points = len(time_series)
        first_timestamp = list(time_series.keys())[0]
        
        print(f"SUCCESS! Received {num_data_points} data points.")
        print(f"Latest data point: {first_timestamp}")
        print(f"Sample data: {time_series[first_timestamp]}")
        
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
    except Exception as e:
        print(f"Error: {e}")

def test_yahoo_finance():
    """Test Yahoo Finance data retrieval"""
    try:
        import yfinance as yf
        print("Yahoo Finance library is available")
        
        symbol = "AAPL"
        print(f"Testing Yahoo Finance data retrieval for {symbol}...")
        
        ticker = yf.Ticker(symbol)
        
        # Get intraday data
        intraday = ticker.history(period="5d", interval="1h")
        print(f"Intraday data (hourly): {len(intraday)} rows")
        if not intraday.empty:
            print(intraday.head(1))
        
        # Get daily data
        daily = ticker.history(period="1mo")
        print(f"Daily data: {len(daily)} rows")
        if not daily.empty:
            print(daily.head(1))
            
        print("Yahoo Finance test SUCCESSFUL!")
    except ImportError:
        print("Yahoo Finance library not available. Install with: pip install yfinance")
    except Exception as e:
        print(f"Error testing Yahoo Finance: {e}")

if __name__ == "__main__":
    print(f"=== Stock Market Data API Tests ({datetime.now()}) ===")
    print("\n1. Testing Alpha Vantage API...")
    test_alpha_vantage_api()
    print("\n2. Testing Yahoo Finance API...")
    test_yahoo_finance()
    print("\n=== Tests completed ===")
