import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import os
import logging
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Move yfinance import inside functions to prevent DAG import timeout
# This way, Airflow can load the DAG without waiting for yfinance to import
has_yfinance = False

class StockCrawler:
    """Crawler for stock market data"""
    
    def __init__(self, api_key: str = None, data_source: str = "yahoo"):
        """
        Initialize the stock crawler.
        
        Args:
            api_key: API key for Alpha Vantage (optional when using Yahoo Finance)
            data_source: 'alphavantage', 'yahoo', or 'mock'
        """
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
        self.base_url = "https://www.alphavantage.co/query"
        self.data_source = data_source
        
        if self.data_source == "alphavantage" and not self.api_key:
            logger.warning("Alpha Vantage API key not provided. Falling back to Yahoo Finance")
            self.data_source = "yahoo"
        
        # Check if yfinance is available only when needed
        if self.data_source == "yahoo":
            self._check_yfinance_available()
    
    def _check_yfinance_available(self):
        """Check if yfinance is available and sets global has_yfinance flag"""
        global has_yfinance
        if not has_yfinance:
            try:
                # Import yfinance here to avoid DAG loading timeout
                import yfinance
                has_yfinance = True
                logger.info("Yahoo Finance library (yfinance) is available")
            except ImportError:
                has_yfinance = False
                logger.warning("Yahoo Finance library (yfinance) not available. Will use mock data.")
                self.data_source = "mock"
    
    def get_intraday_data(self, symbol: str, interval: str = "60min", outputsize: str = "full") -> pd.DataFrame:
        """
        Get intraday stock data.
        
        Args:
            symbol: Stock symbol e.g., 'IBM', 'AAPL'
            interval: Time interval between data points (1min, 5min, 15min, 30min, 60min)
            outputsize: Amount of data to retrieve (compact or full)
            
        Returns:
            DataFrame with stock data
        """
        logger.info(f"Fetching intraday data for {symbol} with interval {interval}")

        if self.data_source == "yahoo":
            return self._get_yahoo_data(symbol, interval)
        elif self.data_source == "alphavantage":
            return self._get_alphavantage_data(symbol, interval, outputsize)
        else:
            return self._get_mock_data(symbol, interval)
    
    def _get_yahoo_data(self, symbol: str, interval: str) -> pd.DataFrame:
        """Get intraday data from Yahoo Finance"""
        try:
            # Import yfinance inside the function to avoid DAG import timeout
            global has_yfinance
            if not has_yfinance:
                logger.warning("Yahoo Finance library not available. Using mock data instead.")
                return self._get_mock_data(symbol, interval)
                
            # Only import when needed and confirmed available
            import yfinance as yf
            
            # Convert interval format from Alpha Vantage to Yahoo Finance
            interval_map = {
                "1min": "1m", 
                "5min": "5m", 
                "15min": "15m", 
                "30min": "30m", 
                "60min": "1h"
            }
            yf_interval = interval_map.get(interval, "1h")
            
            # Determine period based on interval
            period_map = {
                "1m": "1d",
                "5m": "5d",
                "15m": "5d",
                "30m": "5d",
                "1h": "60d",
                "1d": "1y"
            }
            period = period_map.get(yf_interval, "60d")
            
            # Get data from Yahoo Finance
            logger.info(f"Fetching data from Yahoo Finance: {symbol}, interval={yf_interval}, period={period}")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=yf_interval)
            
            if df.empty:
                logger.warning(f"No data returned from Yahoo Finance for {symbol}")
                return pd.DataFrame()
            
            # Process and format the dataframe to match our expected schema
            df = df.reset_index()
            df.rename(columns={
                'Date': 'timestamp',
                'Datetime': 'timestamp',  # Yahoo uses different column names depending on the interval
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close', 
                'Volume': 'volume'
            }, inplace=True)
            
            # Add symbol column
            df['symbol'] = symbol
            
            # Select and order columns to match our schema
            df = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            logger.info(f"Successfully fetched {len(df)} rows from Yahoo Finance for {symbol}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from Yahoo Finance for {symbol}: {str(e)}")
            logger.info("Falling back to mock data")
            return self._get_mock_data(symbol, interval)
    
    def _get_alphavantage_data(self, symbol: str, interval: str, outputsize: str) -> pd.DataFrame:
        """Get intraday data from Alpha Vantage API"""
        params = {
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': symbol,
            'interval': interval,
            'outputsize': outputsize,
            'apikey': self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Check for API error messages
            if "Error Message" in data:
                logger.error(f"Alpha Vantage API Error: {data['Error Message']}")
                return pd.DataFrame()
                
            # Check for rate limit note
            if "Note" in data and "API call frequency" in data["Note"]:
                logger.warning(f"API Rate Limit Warning: {data['Note']}")
                
            # Check for information message
            if "Information" in data:
                logger.error(f"Error in API response: {data}")
                return pd.DataFrame()
                
            # Extract time series data
            time_series_key = f"Time Series ({interval})"
            if time_series_key not in data:
                logger.error(f"Error in API response: {data}")
                return pd.DataFrame()
            
            # Print the full response for debugging
            logger.info(f"API Response Keys: {list(data.keys())}")
                
            time_series = data[time_series_key]
            
            if not time_series:
                logger.warning(f"Empty time series data received for {symbol}")
                return pd.DataFrame()
                
            # Convert to DataFrame
            df = pd.DataFrame.from_dict(time_series, orient='index')
            
            # Convert column names
            df.columns = [col.split('. ')[1] for col in df.columns]
            
            # Convert values to float
            for col in df.columns:
                df[col] = df[col].astype(float)
            
            # Add symbol column
            df['symbol'] = symbol
            
            # Reset index to get datetime as a column
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'timestamp'}, inplace=True)
            
            # Convert to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            logger.info(f"Successfully created DataFrame with {len(df)} rows for {symbol}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from Alpha Vantage for {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def _get_mock_data(self, symbol: str, interval: str) -> pd.DataFrame:
        """Generate mock data when real API sources are not available"""
        logger.info(f"Generating mock data for {symbol}")
        
        # Create mock data
        now = datetime.now()
        rows = []
        
        # Generate 100 data points
        for i in range(100):
            if interval == '1min':
                timestamp = now - timedelta(minutes=i)
            elif interval == '5min':
                timestamp = now - timedelta(minutes=i*5)
            elif interval == '15min':
                timestamp = now - timedelta(minutes=i*15)
            elif interval == '30min':
                timestamp = now - timedelta(minutes=i*30)
            else:  # 60min
                timestamp = now - timedelta(hours=i)
            
            # Create a realistic price pattern with some randomness
            base_price = 150.0 if symbol == 'AAPL' else 100.0
            # Symbols have different price ranges
            if symbol == 'MSFT':
                base_price = 300.0
            elif symbol == 'GOOG':
                base_price = 2500.0
            elif symbol == 'AMZN':
                base_price = 120.0
            elif symbol == 'META':
                base_price = 450.0
            elif symbol == 'TSLA':
                base_price = 200.0
            
            # Add daily cycles and randomness
            import random
            random.seed(i + hash(symbol))
            daily_cycle = 5.0 * (timestamp.hour / 24.0)
            randomness = random.uniform(-2.0, 2.0)
            
            close = base_price + daily_cycle + randomness
            open_price = close - random.uniform(-1.0, 1.0)
            high = max(open_price, close) + random.uniform(0.1, 1.0)
            low = min(open_price, close) - random.uniform(0.1, 1.0)
            volume = int(random.uniform(1000000, 5000000))
            
            rows.append({
                'symbol': symbol,
                'timestamp': timestamp,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        df = pd.DataFrame(rows)
        logger.info(f"Generated {len(df)} rows of mock data for {symbol}")
        
        return df
    
    def get_daily_data(self, symbol: str, outputsize: str = "full") -> pd.DataFrame:
        """
        Get daily stock data.
        
        Args:
            symbol: Stock symbol e.g., 'IBM', 'AAPL'
            outputsize: Amount of data to retrieve (compact or full)
            
        Returns:
            DataFrame with stock data
        """
        if self.data_source == "yahoo":
            # Use Yahoo Finance for daily data
            try:
                logger.info(f"Fetching daily data from Yahoo Finance for {symbol}")
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="1y")  # Get last year of daily data
                
                if df.empty:
                    logger.warning(f"No daily data returned from Yahoo Finance for {symbol}")
                    return pd.DataFrame()
                
                # Process and format the dataframe
                df = df.reset_index()
                df.rename(columns={
                    'Date': 'timestamp',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close', 
                    'Volume': 'volume'
                }, inplace=True)
                
                # Add symbol column
                df['symbol'] = symbol
                
                # Select and order columns to match our schema
                df = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                logger.info(f"Successfully fetched {len(df)} daily data rows from Yahoo Finance for {symbol}")
                
                return df
                
            except Exception as e:
                logger.error(f"Error fetching daily data from Yahoo Finance for {symbol}: {str(e)}")
                return pd.DataFrame()
        
        elif self.data_source == "alphavantage":
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'outputsize': outputsize,
                'apikey': self.api_key
            }
            
            logger.info(f"Fetching daily data for {symbol}")
            
            try:
                response = requests.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Extract time series data
                if "Time Series (Daily)" not in data:
                    logger.error(f"Error in API response: {data}")
                    return pd.DataFrame()
                    
                time_series = data["Time Series (Daily)"]
                
                # Convert to DataFrame
                df = pd.DataFrame.from_dict(time_series, orient='index')
                
                # Convert column names
                df.columns = [col.split('. ')[1] for col in df.columns]
                
                # Convert values to float
                for col in df.columns:
                    df[col] = df[col].astype(float)
                
                # Add symbol column
                df['symbol'] = symbol
                
                # Reset index to get datetime as a column
                df.reset_index(inplace=True)
                df.rename(columns={'index': 'timestamp'}, inplace=True)
                
                # Convert to datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                return df
                
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {str(e)}")
                return pd.DataFrame()
                
        else:
            # Return mock daily data
            return self._get_mock_daily_data(symbol)
    
    def _get_mock_daily_data(self, symbol: str) -> pd.DataFrame:
        """Generate mock daily data"""
        logger.info(f"Generating mock daily data for {symbol}")
        
        # Create mock data
        now = datetime.now()
        rows = []
        
        # Generate 365 days of data
        for i in range(365):
            timestamp = now - timedelta(days=i)
            
            # Create a realistic price pattern with some randomness
            base_price = 150.0 if symbol == 'AAPL' else 100.0
            # Symbols have different price ranges
            if symbol == 'MSFT':
                base_price = 300.0
            elif symbol == 'GOOG':
                base_price = 2500.0
            elif symbol == 'AMZN':
                base_price = 120.0
            elif symbol == 'META':
                base_price = 450.0
            elif symbol == 'TSLA':
                base_price = 200.0
            
            # Add monthly trend and randomness
            import random
            random.seed(i + hash(symbol))
            
            monthly_trend = 10.0 * (i / 365.0)  # Upward trend over the year
            weekly_cycle = 5.0 * ((i % 7) / 7.0)
            randomness = random.uniform(-5.0, 5.0)
            
            close = base_price + monthly_trend + weekly_cycle + randomness
            open_price = close - random.uniform(-2.0, 2.0)
            high = max(open_price, close) + random.uniform(0.5, 3.0)
            low = min(open_price, close) - random.uniform(0.5, 3.0)
            volume = int(random.uniform(5000000, 20000000))
            
            rows.append({
                'symbol': symbol,
                'timestamp': timestamp,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        df = pd.DataFrame(rows)
        logger.info(f"Generated {len(df)} rows of mock daily data for {symbol}")
        
        return df
    
    def get_multiple_stocks(self, symbols: List[str], interval: str = "60min") -> Dict[str, pd.DataFrame]:
        """
        Get data for multiple stock symbols.
        
        Args:
            symbols: List of stock symbols
            interval: Time interval for intraday data
            
        Returns:
            Dictionary with symbol as key and DataFrame as value
        """
        result = {}
        
        for symbol in symbols:
            # Only need rate limiting for Alpha Vantage
            if self.data_source == "alphavantage" and len(result) > 0 and len(result) % 5 == 0:
                logger.info("Rate limiting: Sleeping for 65 seconds")
                time.sleep(65)
                
            df = self.get_intraday_data(symbol, interval)
            
            if not df.empty:
                result[symbol] = df
                logger.info(f"Successfully fetched data for {symbol}")
            else:
                logger.warning(f"No data fetched for {symbol}")
        
        return result

    def get_historical_data(self, symbol: str, timeframe: str = "1d", period: str = "1y") -> pd.DataFrame:
        """
        Get historical stock data for various timeframes.
        
        Args:
            symbol: Stock symbol e.g., 'IBM', 'AAPL'
            timeframe: Time interval between data points (1h, 1d, 1wk, 1mo)
            period: Amount of historical data (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            
        Returns:
            DataFrame with stock data
        """
        logger.info(f"Fetching historical data for {symbol} with timeframe {timeframe} and period {period}")

        if self.data_source == "yahoo":
            try:
                # Check yfinance availability before proceeding
                global has_yfinance
                if not has_yfinance:
                    logger.warning("Yahoo Finance not available, using mock data")
                    return self._get_mock_historical_data(symbol, timeframe, period)
                    
                # Import only when needed
                import yfinance as yf
                
                # Convert to Yahoo Finance format
                yf_timeframe_map = {
                    "1h": "1h",
                    "1d": "1d",
                    "1wk": "1wk",
                    "1mo": "1mo"
                }
                
                # Use default if not in map
                yf_timeframe = yf_timeframe_map.get(timeframe, timeframe)
                
                # Get data from Yahoo Finance
                ticker = yf.Ticker(symbol)
                
                # For intervals less than 1d, period can't be more than 60 days
                if yf_timeframe == "1h" and period in ["1y", "2y", "5y", "10y", "max"]:
                    period = "60d"
                    logger.info(f"Adjusted period to {period} for hourly data (Yahoo Finance limitation)")
                
                df = ticker.history(period=period, interval=yf_timeframe)
                
                if df.empty:
                    logger.warning(f"No historical data returned from Yahoo Finance for {symbol}")
                    return pd.DataFrame()
                
                # Process and format the dataframe
                df = df.reset_index()
                df.rename(columns={
                    'Date': 'timestamp',
                    'Datetime': 'timestamp',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close', 
                    'Volume': 'volume'
                }, inplace=True)
                
                # Add symbol and timeframe columns
                df['symbol'] = symbol
                df['timeframe'] = timeframe
                
                # Select and order columns
                df = df[['symbol', 'timestamp', 'timeframe', 'open', 'high', 'low', 'close', 'volume']]
                
                # Add technical indicators for better analysis
                df = self._add_basic_indicators(df)
                
                logger.info(f"Successfully fetched {len(df)} rows of {timeframe} data for {symbol}")
                return df
            
            except Exception as e:
                logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
                logger.info("Falling back to mock data")
                return self._get_mock_historical_data(symbol, timeframe, period)
        else:
            # Fall back to mock data for other sources
            return self._get_mock_historical_data(symbol, timeframe, period)
    
    def _add_basic_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add basic technical indicators to the dataframe"""
        try:
            # Add SMA (Simple Moving Average) for different periods
            if len(df) >= 20:
                df['sma_20'] = df['close'].rolling(window=20).mean()
            if len(df) >= 50:
                df['sma_50'] = df['close'].rolling(window=50).mean()
            if len(df) >= 200:
                df['sma_200'] = df['close'].rolling(window=200).mean()
            
            # Daily returns
            df['daily_return'] = df['close'].pct_change() * 100
            
            # Volatility (10-day standard deviation of returns)
            if len(df) >= 10:
                df['volatility_10d'] = df['daily_return'].rolling(window=10).std()
            
            # Volume changes
            df['volume_change'] = df['volume'].pct_change() * 100
            
            # Relative strength (close/SMA50)
            if 'sma_50' in df.columns:
                df['rs_50'] = df['close'] / df['sma_50']
                
            return df
        except Exception as e:
            logger.warning(f"Error adding indicators: {str(e)}")
            return df
            
    def _get_mock_historical_data(self, symbol: str, timeframe: str, period: str) -> pd.DataFrame:
        """Generate mock historical data when real API sources are not available"""
        logger.info(f"Generating mock historical data for {symbol} with {timeframe} timeframe")
        
        # Determine number of data points based on timeframe and period
        points = 100  # default
        if timeframe == "1h":
            points = 24 * 30  # ~30 days of hourly data
        elif timeframe == "1d":
            if period == "1mo":
                points = 30
            elif period == "3mo":
                points = 90
            elif period == "6mo":
                points = 180
            elif period == "1y":
                points = 365
            elif period == "5y":
                points = 365 * 5
        elif timeframe == "1wk":
            points = 52 * 5  # 5 years of weekly data
        elif timeframe == "1mo":
            points = 12 * 10  # 10 years of monthly data
        
        # Create mock data similar to _get_mock_data but with timeframe awareness
        now = datetime.now()
        rows = []
        
        for i in range(points):
            if timeframe == "1h":
                timestamp = now - timedelta(hours=i)
            elif timeframe == "1d":
                timestamp = now - timedelta(days=i)
            elif timeframe == "1wk":
                timestamp = now - timedelta(weeks=i)
            else:  # 1mo
                # Approximately subtract months
                timestamp = now - timedelta(days=i*30)
            
            # Create realistic price patterns with some randomness
            # Similar to existing _get_mock_data implementation
            # ...existing mock data generation code...
            base_price = 150.0 if symbol == 'AAPL' else 100.0
            if symbol == 'MSFT':
                base_price = 300.0
            elif symbol == 'GOOG':
                base_price = 2500.0
            elif symbol == 'AMZN':
                base_price = 120.0
            elif symbol == 'META':
                base_price = 450.0
            elif symbol == 'TSLA':
                base_price = 200.0
            
            # Add trend based on timeframe
            import random
            random.seed(i + hash(symbol))
            
            if timeframe in ["1mo", "1wk"]:
                # Long-term trend
                trend_factor = 20.0 * (1 - (i / points))  # Upward trend over time
                cycle = 10.0 * np.sin(i / 10)  # Market cycles
            else:
                # Short-term fluctuations
                trend_factor = 10.0 * (1 - (i / points))
                cycle = 5.0 * np.sin(i / 5)
                
            randomness = random.uniform(-5.0, 5.0)
            
            close = base_price + trend_factor + cycle + randomness
            open_price = close - random.uniform(-2.0, 2.0)
            high = max(open_price, close) + random.uniform(0.5, 3.0)
            low = min(open_price, close) - random.uniform(0.5, 3.0)
            volume = int(random.uniform(5000000, 20000000))
            
            rows.append({
                'symbol': symbol,
                'timestamp': timestamp,
                'timeframe': timeframe,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        df = pd.DataFrame(rows)
        
        # Add technical indicators
        df = self._add_basic_indicators(df)
        
        logger.info(f"Generated {len(df)} rows of mock {timeframe} data for {symbol}")
        return df
