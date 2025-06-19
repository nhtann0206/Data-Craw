# Apply PyTorch fix before importing other modules
import sys
import os

# Add src to path
sys.path.insert(0, '/app')

# Apply PyTorch fix
try:
    from src.ui.torch_fix import apply_torch_fix
    apply_torch_fix()
except Exception as e:
    print(f"Warning: Could not apply PyTorch fix: {e}")

# Now import other modules
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
import json
from datetime import datetime, timedelta
import uuid

# Configure Streamlit to avoid watching certain modules
os.environ['STREAMLIT_WATCHDOG_MODULES'] = 'torch,tensorflow'

# Import our chatbot after applying fixes
from src.chatbot.chatbot import StockAnalystChatbot

# Configure page
st.set_page_config(
    page_title="Stock Market Analysis Dashboard",
    page_icon="📈",
    layout="wide",
)

# Initialize session state for chat
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

# Get environment variables
gemini_api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyA60tPjj2QuH1Txqi3--cCAhswdc3tKNiQ")
gemini_url = os.environ.get("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent")

# Function to check data status
def check_data_status():
    try:
        response = requests.get("http://fastapi:8000/stock/status")
        if response.status_code == 200:
            return response.json()
        else:
            return {"has_data": False, "error": f"Error {response.status_code}"}
    except Exception as e:
        return {"has_data": False, "error": str(e)}

# Display environment and data status for debugging
data_status = check_data_status()
with st.sidebar.expander("Debug Info"):
    st.write({
        "GEMINI_API_KEY": "Available" if gemini_api_key else "Missing",
        "GEMINI_URL": gemini_url,
        "Data Status": "Available" if data_status.get("has_data") else "Not Available",
        "Data Error": data_status.get("error", "None")
    })

# Initialize chatbot
@st.cache_resource
def get_chatbot():
    postgres_connection = os.environ.get(
        "POSTGRES_CONNECTION_STRING",
        "postgresql://postgresadmin:postgresadmin@postgres:5432/postgres"
    )
    return StockAnalystChatbot(
        gemini_api_key=gemini_api_key,
        gemini_url=gemini_url,
        postgres_connection_string=postgres_connection,
        analysis_dir="/app/volume/analyses"
    )

try:
    chatbot = get_chatbot()
    st.sidebar.success("Chatbot initialized successfully!")
except Exception as e:
    st.sidebar.error(f"Failed to initialize chatbot: {str(e)}")
    chatbot = None

# Function to get stock data from FastAPI
def get_stock_data(symbol, period="1d"):
    try:
        response = requests.get(f"http://fastapi:8000/stock/data/{symbol}?period={period}")
        if response.status_code == 200:
            data = response.json()
            if not data:
                st.warning(f"No data returned from API for {symbol}")
                return pd.DataFrame()
                
            df = pd.DataFrame(data)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            else:
                st.warning(f"Missing 'timestamp' column in data for {symbol}")
                st.write("Available columns:", df.columns.tolist() if not df.empty else "None")
                return pd.DataFrame()
        else:
            st.error(f"Error fetching data for {symbol}: {response.status_code}")
            try:
                st.write("Error details:", response.json())
            except:
                st.write("No error details available")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Exception when fetching {symbol} data: {str(e)}")
        return pd.DataFrame()

# Function to plot stock chart
def plot_stock_chart(df, symbol):
    if df.empty:
        return None
    
    # Ensure we have all required columns
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_columns):
        missing = [col for col in required_columns if col not in df.columns]
        st.warning(f"Missing required columns for {symbol}: {missing}")
        return None
    
    fig = go.Figure()
    
    # Add candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name=symbol
        )
    )
    
    # Add volume as bar chart
    fig.add_trace(
        go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='Volume',
            marker_color='rgba(0, 0, 255, 0.3)',
            opacity=0.3,
            yaxis='y2'
        )
    )
    
    # Layout
    fig.update_layout(
        title=f'{symbol} Stock Price',
        yaxis_title='Price ($)',
        xaxis_title='Date',
        yaxis2=dict(
            title='Volume',
            overlaying='y',
            side='right',
            showgrid=False
        ),
        height=600,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

# App layout
st.title("📈 Stock Market Analysis Dashboard")

# Sidebar
st.sidebar.title("Navigation")

# Show data status in sidebar
if data_status.get("has_data"):
    st.sidebar.success(f"✅ Data available ({data_status.get('total_records', 0)} records)")
    with st.sidebar.expander("Data Details"):
        for symbol in data_status.get("symbols_data", []):
            st.write(f"{symbol['symbol']}: {symbol['count']} records")
            st.caption(f"Latest: {symbol['latest_data']}")
else:
    st.sidebar.warning("⚠️ No stock data available")
    if data_status.get("error"):
        st.sidebar.error(f"Error: {data_status['error']}")
    st.sidebar.info("Please run the Airflow DAG to crawl data")

# Navigation
page = st.sidebar.radio("Go to", ["Dashboard", "Chat with StockGPT", "Analysis History"])

# Pages
if page == "Dashboard":
    # Stock symbols
    symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "JPM", "BAC", "V", "MA"]
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_symbols = st.multiselect(
            "Select stocks to display",
            symbols,
            default=["AAPL", "MSFT", "GOOG"]
        )
    
    with col2:
        # Time period
        time_period = st.selectbox(
            "Select time period",
            ["1h", "1d", "1w", "1m"],
            index=1
        )
        
        # Add caching setting
        use_cache = st.checkbox("Use cached data", value=True)
    
    # Add progress tracking
    progress_bar = None
    if selected_symbols:
        progress_bar = st.progress(0)
    
    # Display charts with improved error handling and caching
    for i, symbol in enumerate(selected_symbols):
        if progress_bar:
            progress_bar.progress((i + 1) / len(selected_symbols))
        
        with st.spinner(f"Loading data for {symbol}..."):
            # Use st.cache_data to cache API results
            @st.cache_data(ttl=300 if use_cache else 0)
            def get_cached_stock_data(symbol, period):
                return get_stock_data(symbol, period)
            
            # Try to get data with the specified timeframe
            df = get_cached_stock_data(symbol, time_period)
            
            if df.empty:
                st.warning(f"No {time_period} data available for {symbol}")
                
                # Automatically try other timeframes
                fallback_timeframes = ["1d", "1h", "1w", "1m"]
                if time_period in fallback_timeframes:
                    fallback_timeframes.remove(time_period)
                
                for fallback in fallback_timeframes:
                    st.info(f"Trying fallback timeframe: {fallback}...")
                    fallback_df = get_stock_data(symbol, fallback)
                    if not fallback_df.empty:
                        df = fallback_df
                        st.success(f"Using {fallback} data instead")
                        break
            
            fig = plot_stock_chart(df, symbol)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error(f"Failed to plot chart for {symbol}")

    if progress_bar:
        progress_bar.empty()

elif page == "Chat with StockGPT":
    st.header("💬 Chat with StockGPT")
    st.markdown("*Ask questions about stock performance, trends, and get AI-powered insights*")
    
    if chatbot is None:
        st.error("Chatbot initialization failed. Please check the sidebar for details.")
    else:
        # Force container size to ensure chat window is visible
        chat_container = st.container()
        with chat_container:
            # Display chat messages from history
            for message in st.session_state.chat_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message.get("used_crawled_data"):
                        st.caption("✅ Using crawled market data")
            
            # Display prior analyses section
            with st.expander("📊 View Prior Analyses"):
                try:
                    prior_analyses = chatbot.get_prior_analyses(limit=3)
                    if prior_analyses:
                        for i, analysis in enumerate(prior_analyses):
                            st.subheader(f"{analysis['title']}")
                            st.markdown(f"**Time Period:** {analysis['time_period']}")
                            st.markdown(f"**Symbols:** {', '.join(analysis['symbols']) if analysis['symbols'] else 'N/A'}")
                            st.markdown(f"**Analysis:**\n{analysis['content']}")
                            if i < len(prior_analyses) - 1:
                                st.divider()
                    else:
                        st.info("No prior analyses found. Start chatting to generate analyses.")
                except Exception as e:
                    st.warning(f"Could not load prior analyses: {str(e)}")
        
        # Chat input - Outside the container to ensure it's always visible
        st.write("") # Add some space
        st.write("") # Add more space
        prompt = st.chat_input("Ask about stock trends, performance, etc.")
        if prompt:
            # Add user message to chat history
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            
            # Display user message in chat
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Process with chatbot and display response
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing stocks..."):
                        response = chatbot.query(prompt, user_id=st.session_state.user_id)
                        st.markdown(response["answer"])
                        if response.get("used_crawled_data"):
                            st.caption("✅ Using crawled market data")
                
                # Add assistant response to chat history
                st.session_state.chat_messages.append({
                    "role": "assistant", 
                    "content": response["answer"],
                    "used_crawled_data": response.get("used_crawled_data", False)
                })
            
            # Auto-scroll to bottom by rerunning the app
            st.rerun()

elif page == "Analysis History":
    st.header("📝 Analysis History")
    
    if chatbot is None:
        st.error("Chatbot initialization failed. Please check the sidebar for details.")
    else:
        # Try to get analyses from the database
        try:
            analyses = chatbot.get_prior_analyses(limit=10)
            
            # Create tabs for different views
            tab1, tab2 = st.tabs(["Analysis Feed", "Search"])
            
            with tab1:
                for analysis in analyses:
                    with st.expander(f"{analysis['title']}"):
                        st.markdown(f"**Time:** {datetime.fromisoformat(analysis['created_at']).strftime('%Y-%m-%d %H:%M')}")
                        st.markdown(f"**Symbols:** {', '.join(analysis['symbols']) if analysis['symbols'] else 'N/A'}")
                        st.markdown(f"**Time Period:** {analysis['time_period']}")
                        st.markdown(f"**Analysis:**\n{analysis['content']}")
            
            with tab2:
                search_query = st.text_input("Search analyses", "")
                if search_query:
                    filtered_analyses = [a for a in analyses if search_query.lower() in a['content'].lower()]
                    st.write(f"Found {len(filtered_analyses)} results")
                    
                    for analysis in filtered_analyses:
                        with st.expander(f"{analysis['title']}"):
                            st.markdown(f"**Time:** {datetime.fromisoformat(analysis['created_at']).strftime('%Y-%m-%d %H:%M')}")
                            st.markdown(f"**Symbols:** {', '.join(analysis['symbols']) if analysis['symbols'] else 'N/A'}")
                            st.markdown(f"**Analysis:**\n{analysis['content']}")
        except Exception as e:
            st.error(f"Error loading analyses: {str(e)}")

