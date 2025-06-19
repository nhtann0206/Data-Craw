import os
import logging
import json
import requests
from datetime import datetime
import pandas as pd
import uuid
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import prompts
from src.chatbot.prompts import STOCK_ANALYST_PROMPT, FALLBACK_PROMPT

# Attempt to import tensorflow and keras without tf-keras dependency
try:
    import tensorflow as tf
    # Force CPU usage to avoid GPU-related issues
    tf.config.set_visible_devices([], 'GPU')
    
    # Try to import keras (not tf-keras)
    try:
        import keras
        has_keras = True
        logger.info(f"Successfully imported keras version: {keras.__version__}")
    except ImportError:
        logger.warning("Keras not available. Using fallback mode.")
        has_keras = False
except ImportError:
    logger.warning("TensorFlow not available. Using fallback mode.")
    has_keras = False

# Attempt to import LangChain components with updated imports
try:
    # Updated import path for ConversationBufferMemory
    from langchain.memory import ConversationBufferMemory
    # Updated import path for ChatMessageHistory
    from langchain_community.chat_message_histories import ChatMessageHistory
    has_langchain = True
except ImportError:
    logger.warning("Langchain not available. Some features will be disabled.")
    has_langchain = False

try:
    import psycopg2
    has_psycopg = True
except ImportError:
    logger.warning("psycopg2 not available. Database features will be disabled.")
    has_psycopg = False

# Try to import embeddings only if keras is available
if has_keras:
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        has_huggingface = True
        logger.info("Successfully imported HuggingFaceEmbeddings")
    except ImportError:
        logger.warning("HuggingFace embeddings not available. Vector search will be disabled.")
        has_huggingface = False
else:
    has_huggingface = False
    logger.warning("Skipping HuggingFace embeddings import due to missing keras.")

# Try to import PGVector only if all required components are available
try:
    if has_langchain and has_psycopg and has_huggingface:
        from langchain_postgres import PGVector
        has_pgvector = True
        logger.info("Successfully imported PGVector")
    else:
        has_pgvector = False
except ImportError:
    logger.warning("PGVector not available. Vector database features will be disabled.")
    has_pgvector = False

class GeminiLLM:
    """Wrapper class for Gemini API"""
    
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        # Make sure we're using the key from the URL if needed
        if "key=" in api_url:
            self.api_url = api_url
        else:
            if "?" in api_url:
                self.api_url = f"{api_url}&key={api_key}"
            else:
                self.api_url = f"{api_url}?key={api_key}"
        
    def invoke(self, prompt: str) -> str:
        """Send prompt to Gemini API and get response"""
        try:
            data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            response = requests.post(
                self.api_url,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extract text from the response
            if "candidates" in result and len(result["candidates"]) > 0:
                if "content" in result["candidates"][0] and "parts" in result["candidates"][0]["content"]:
                    parts = result["candidates"][0]["content"]["parts"]
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
            
            # Fallback if we couldn't parse the response properly
            return str(result)
        
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return f"Error generating response: {str(e)}"

class StockAnalystChatbot:
    """Chatbot for stock market analysis"""
    
    def __init__(
        self, 
        gemini_api_key: str = None,
        gemini_url: str = None,
        postgres_connection_string: str = None,
        analysis_dir: str = "volume/analyses"
    ):
        """Initialize the chatbot."""
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.gemini_url = gemini_url or os.environ.get("GEMINI_URL")
        
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required")
        
        self.postgres_connection_string = postgres_connection_string or os.environ.get(
            "POSTGRES_CONNECTION_STRING",
            "postgresql://postgresadmin:postgresadmin@postgres:5432/postgres"
        )
        
        self.analysis_dir = analysis_dir
        try:
            os.makedirs(self.analysis_dir, exist_ok=True)
            logger.info(f"Analysis directory set to: {self.analysis_dir}")
        except Exception as e:
            logger.warning(f"Failed to create analysis directory {self.analysis_dir}: {str(e)}")
            # Fallback to a directory we know should be writable
            self.analysis_dir = "/tmp/analyses"
            os.makedirs(self.analysis_dir, exist_ok=True)
            logger.info(f"Using fallback analysis directory: {self.analysis_dir}")
        
        # Initialize Gemini LLM
        self.llm = GeminiLLM(self.gemini_api_key, self.gemini_url)
        
        # Initialize simple chat history if LangChain isn't available
        self.chat_history = []
        
        # Initialize embeddings with error handling
        if has_huggingface:
            try:
                self.embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                
                # Set up vector store if possible
                if has_pgvector:
                    try:
                        self.vector_store = PGVector(
                            connection_string=self.postgres_connection_string,
                            embedding_function=self.embeddings,
                            collection_name="stock_embeddings",
                            use_jsonb=True  # Use JSONB for metadata
                        )
                        self.has_vector_store = True
                    except Exception as e:
                        logger.warning(f"Vector store initialization failed: {str(e)}. Falling back to basic mode.")
                        self.vector_store = None
                        self.has_vector_store = False
                else:
                    self.vector_store = None
                    self.has_vector_store = False
                    
            except Exception as e:
                logger.warning(f"Embeddings initialization failed: {str(e)}. Falling back to basic mode.")
                self.embeddings = None
                self.vector_store = None
                self.has_vector_store = False
        else:
            self.embeddings = None
            self.vector_store = None
            self.has_vector_store = False
        
        # Initialize chat ID
        self.chat_id = str(uuid.uuid4())
        
        # Test database connection immediately
        if has_psycopg:
            try:
                logger.info(f"Testing PostgreSQL connection to {self.postgres_connection_string}")
                conn = psycopg2.connect(self.postgres_connection_string)
                cursor = conn.cursor()
                
                # Check if stock_data table exists and has data
                cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'stock_data')")
                table_exists = cursor.fetchone()[0]
                
                if table_exists:
                    cursor.execute("SELECT COUNT(*) FROM stock_data")
                    data_count = cursor.fetchone()[0]
                    logger.info(f"Found {data_count} rows in stock_data table")
                    
                    if data_count > 0:
                        # Sample the data
                        cursor.execute("SELECT symbol, timestamp, close FROM stock_data LIMIT 5")
                        sample_data = cursor.fetchall()
                        logger.info(f"Sample data: {sample_data}")
                else:
                    logger.warning("stock_data table does not exist in database")
                    
                cursor.close()
                conn.close()
                logger.info("PostgreSQL connection test completed")
            except Exception as e:
                logger.error(f"PostgreSQL connection test failed: {str(e)}")
    
    def get_history_text(self) -> str:
        """Get conversation history as text"""
        if not self.chat_history:
            return ""
            
        history_text = []
        for entry in self.chat_history:
            role = "User" if entry["is_user"] else "AI"
            history_text.append(f"{role}: {entry['text']}")
        
        return "\n".join(history_text)
    
    def query(self, user_input: str, user_id: str = "anonymous", save_analysis: bool = True) -> Dict[str, Any]:
        """Process a user query and generate a response."""
        try:
            # Check if there's any stock data available at all
            has_stock_data = False
            retrieved_context = "No stock data available for analysis."
            data_samples = []
            
            # Prepare context from vector store if available
            if self.has_vector_store and self.vector_store:
                try:
                    # Get relevant documents from vector store
                    docs = self.vector_store.similarity_search(user_input, k=5)
                    if docs:
                        retrieved_context = "\n\n".join([doc.page_content for doc in docs])
                        has_stock_data = True
                        logger.info(f"Retrieved {len(docs)} documents from vector store")
                    else:
                        logger.warning("No documents retrieved from vector store")
                except Exception as e:
                    logger.warning(f"Error retrieving from vector store: {str(e)}")
            
            # If we don't have vector store or no docs were retrieved, try a simple DB lookup for stocks
            if not has_stock_data and has_psycopg:
                try:
                    logger.info("Attempting direct database query for stock data")
                    conn = psycopg2.connect(self.postgres_connection_string)
                    cursor = conn.cursor()
                    
                    # Check if we have any stock data
                    cursor.execute("SELECT COUNT(*) FROM stock_data")
                    count = cursor.fetchone()[0]
                    logger.info(f"Found {count} records in stock_data table")
                    
                    if count > 0:
                        # Try to extract stock symbols from the user query
                        common_symbols = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'META', 'TSLA', 'JPM', 'BAC', 'V', 'MA']
                        mentioned_symbols = [symbol for symbol in common_symbols if symbol.lower() in user_input.lower()]
                        
                        # If no specific symbols mentioned, use the most popular ones
                        query_symbols = mentioned_symbols if mentioned_symbols else common_symbols[:4]
                        
                        symbols_list = "', '".join(query_symbols)
                        logger.info(f"Querying for symbols: {symbols_list}")
                        
                        # Try to get some recent data for popular or mentioned stocks
                        cursor.execute(f"""
                        SELECT symbol, timestamp, open, high, low, close, volume
                        FROM stock_data
                        WHERE symbol IN ('{symbols_list}')
                        ORDER BY timestamp DESC
                        LIMIT 50
                        """)
                        
                        rows = cursor.fetchall()
                        if rows:
                            has_stock_data = True
                            retrieved_context = f"Recent stock data available for analysis ({len(rows)} records):\n"
                            
                            # Group by symbol for better context
                            symbols_data = {}
                            for row in rows:
                                symbol = row[0]
                                if symbol not in symbols_data:
                                    symbols_data[symbol] = []
                                symbols_data[symbol].append(row)
                            
                            # Format data by symbol
                            for symbol, data_points in symbols_data.items():
                                retrieved_context += f"\n== {symbol} ==\n"
                                # Take just the 5 most recent points for each symbol
                                for i, point in enumerate(data_points[:5]):
                                    ts = point[1].strftime('%Y-%m-%d %H:%M')
                                    retrieved_context += f"{ts}: open=${point[2]:.2f}, high=${point[3]:.2f}, low=${point[4]:.2f}, close=${point[5]:.2f}, volume={point[6]}\n"
                                
                                # Add basic stats
                                if len(data_points) >= 2:
                                    first_close = data_points[-1][5]  # Oldest point (chronologically first)
                                    last_close = data_points[0][5]   # Latest point
                                    pct_change = ((last_close - first_close) / first_close) * 100
                                    retrieved_context += f"Period change: {pct_change:.2f}% (from ${first_close:.2f} to ${last_close:.2f})\n"
                                
                            # Store sample for logging
                            data_samples = list(symbols_data.keys())
                            logger.info(f"Prepared context with data for symbols: {data_samples}")
                    
                    cursor.close()
                    conn.close()
                    
                except Exception as e:
                    logger.error(f"Error checking database for stock data: {str(e)}")
            
            # Get conversation history
            history = self.get_history_text()
            
            # Choose appropriate prompt based on data availability
            if has_stock_data:
                prompt_template = STOCK_ANALYST_PROMPT
                logger.info(f"Using STOCK_ANALYST_PROMPT with data for {data_samples}")
            else:
                prompt_template = FALLBACK_PROMPT
                logger.warning("No stock data available. Using FALLBACK_PROMPT")
            
            # Fill in the prompt template
            prompt = prompt_template.format(
                context=retrieved_context,
                chat_history=history,
                question=user_input
            )
            
            # Get response from Gemini
            answer = self.llm.invoke(prompt)
            
            # Update memory
            self.chat_history.append({"is_user": True, "text": user_input})
            self.chat_history.append({"is_user": False, "text": answer})
            
            # Save to database
            self._save_message_to_db(user_id, user_input, is_bot=False)
            self._save_message_to_db(user_id, answer, is_bot=True)
            
            # Save analysis if requested
            if save_analysis:
                self._save_analysis(user_input, answer, self.chat_id)
            
            return {
                "answer": answer,
                "chat_id": self.chat_id,
                "timestamp": datetime.now().isoformat(),
                "used_crawled_data": has_stock_data
            }
            
        except Exception as e:
            logger.error(f"Error in processing query: {str(e)}")
            return {
                "answer": "I'm sorry, I encountered an error while processing your request.",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "used_crawled_data": False
            }
    
    def _save_message_to_db(self, user_id: str, message_text: str, is_bot: bool):
        """Save a message to the database"""
        if not has_psycopg:
            logger.warning("Database features are disabled. Message not saved.")
            return
        
        try:
            conn = psycopg2.connect(self.postgres_connection_string)
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO chat_messages (user_id, message_text, is_bot)
            VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (user_id, message_text, is_bot))
            conn.commit()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving message to database: {str(e)}")
    
    def _save_analysis(self, user_question: str, bot_response: str, chat_id: str):
        """Save the analysis to a file and database"""
        try:
            # Make sure directory exists
            os.makedirs(self.analysis_dir, exist_ok=True)
            
            # Extract a title from the response
            title = f"Stock Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Try to extract mentioned symbols
            symbols = []
            common_symbols = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'META', 'TSLA', 'JPM', 'BAC', 'V', 'MA']
            for symbol in common_symbols:
                if symbol in bot_response:
                    symbols.append(symbol)
            
            # Try to determine time period
            time_period = "short-term"
            if "hourly" in bot_response.lower():
                time_period = "hourly"
            elif "daily" in bot_response.lower():
                time_period = "daily"
            
            # Create a structured analysis
            analysis = {
                "title": title,
                "timestamp": datetime.now().isoformat(),
                "chat_id": chat_id,
                "user_question": user_question,
                "analysis": bot_response,
                "symbols": symbols,
                "time_period": time_period
            }
            
            # Save to file
            filename = f"{self.analysis_dir}/analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            try:
                with open(filename, "w") as f:
                    json.dump(analysis, f, indent=2)
                logger.info(f"Analysis saved to {filename}")
            except Exception as file_error:
                logger.error(f"Error saving analysis to file: {str(file_error)}")
            
            # Save to database
            if has_psycopg:
                try:
                    conn = psycopg2.connect(self.postgres_connection_string)
                    cursor = conn.cursor()
                    
                    insert_query = """
                    INSERT INTO stock_analyses (chat_id, title, content, symbols, time_period)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        chat_id,
                        title,
                        bot_response,
                        symbols,
                        time_period
                    ))
                    conn.commit()
                    
                    cursor.close()
                    conn.close()
                    
                except Exception as e:
                    logger.error(f"Error saving analysis to database: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error saving analysis: {str(e)}")
    
    def get_prior_analyses(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get prior analyses to reference in new conversations"""
        if not has_psycopg:
            logger.warning("Database features are disabled. Cannot fetch prior analyses.")
            # Try to read from files instead
            try:
                analyses = []
                if os.path.exists(self.analysis_dir):
                    files = sorted([f for f in os.listdir(self.analysis_dir) if f.endswith('.json')], reverse=True)[:limit]
                    
                    for file in files:
                        with open(os.path.join(self.analysis_dir, file), "r") as f:
                            analysis = json.load(f)
                            analyses.append(analysis)
                
                return analyses
            except Exception as e:
                logger.error(f"Error reading analysis files: {str(e)}")
                return []
        
        try:
            # Get analyses from the database
            conn = psycopg2.connect(self.postgres_connection_string)
            cursor = conn.cursor()
            
            query = """
            SELECT title, content, symbols, time_period, created_at
            FROM stock_analyses
            ORDER BY created_at DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            analyses = [
                {
                    "title": row[0],
                    "content": row[1],
                    "symbols": row[2],
                    "time_period": row[3],
                    "created_at": row[4].isoformat()
                }
                for row in rows
            ]
            
            return analyses
            
        except Exception as e:
            logger.error(f"Error fetching prior analyses: {str(e)}")
            
            # Fallback to reading from files
            try:
                analyses = []
                files = sorted(os.listdir(self.analysis_dir), reverse=True)[:limit]
                
                for file in files:
                    if file.endswith(".json"):
                        with open(os.path.join(self.analysis_dir, file), "r") as f:
                            analysis = json.load(f)
                            analyses.append(analysis)
                
                return analyses
                
            except Exception as inner_e:
                logger.error(f"Error reading analysis files: {str(inner_e)}")
                return []
