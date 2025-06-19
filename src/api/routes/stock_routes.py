from fastapi import APIRouter, HTTPException, Query
import pandas as pd
import psycopg2
import os
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

router = APIRouter()

def get_db_connection():
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ.get("POSTGRES_USER", "postgresadmin"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgresadmin")
    )
    return conn

@router.get("/data/{symbol}")
def get_stock_data(
    symbol: str,
    period: str = Query("1d", description="Time period: 1h, 1d, 1w, 1m"),
    timeframe: str = Query("daily", description="Data timeframe: hourly, daily, weekly, monthly"),
    limit: int = Query(100, description="Number of data points to return")
):
    """
    Get stock data for a specific symbol and time period.
    """
    try:
        # Map timeframe parameter to database value
        timeframe_mapping = {
            "1h": "hourly",
            "1d": "daily", 
            "1w": "weekly",
            "1m": "monthly"
        }
        
        # Use parameter directly if it matches, otherwise map it
        db_timeframe = timeframe
        if period in timeframe_mapping:
            db_timeframe = timeframe_mapping[period]
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if we should use the upgraded v2 table
        cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'stock_data_v2')")
        has_v2_table = cursor.fetchone()[0]
        
        if has_v2_table:
            # Try the v2 table first with timeframe support
            check_query = """
            SELECT COUNT(*) FROM stock_data_v2 WHERE symbol = %s AND timeframe = %s
            """
            cursor.execute(check_query, (symbol, db_timeframe))
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Use the new version of the table
                query = """
                SELECT symbol, timestamp, timeframe, open, high, low, close, volume
                FROM stock_data_v2
                WHERE symbol = %s AND timeframe = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """
                cursor.execute(query, (symbol, db_timeframe, limit))
                rows = cursor.fetchall()
                
                # Convert to dict for JSON response
                result = [
                    {
                        "symbol": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "timeframe": row[2],
                        "open": float(row[3]) if row[3] is not None else None,
                        "high": float(row[4]) if row[4] is not None else None,
                        "low": float(row[5]) if row[5] is not None else None,
                        "close": float(row[6]) if row[6] is not None else None,
                        "volume": float(row[7]) if row[7] is not None else None
                    }
                    for row in rows
                ]
                
                # Reverse to get chronological order
                result.reverse()
                return result
        
        # Fall back to original table if v2 doesn't have data
        check_query = """
        SELECT COUNT(*) FROM stock_data WHERE symbol = %s
        """
        cursor.execute(check_query, (symbol,))
        count = cursor.fetchone()[0]
        
        if count == 0:
            # No data found, return empty list
            cursor.close()
            conn.close()
            return []
        
        # Otherwise, get the actual data from original table
        query = """
        SELECT symbol, timestamp, open, high, low, close, volume
        FROM stock_data
        WHERE symbol = %s
        ORDER BY timestamp DESC
        LIMIT %s
        """
        
        cursor.execute(query, (symbol, limit))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Convert to dict for JSON response
        result = [
            {
                "symbol": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "timeframe": db_timeframe,  # Add timeframe field for consistency
                "open": float(row[2]) if row[2] is not None else None,
                "high": float(row[3]) if row[3] is not None else None,
                "low": float(row[4]) if row[4] is not None else None,
                "close": float(row[5]) if row[5] is not None else None,
                "volume": float(row[6]) if row[6] is not None else None
            }
            for row in rows
        ]
        
        # Reverse to get chronological order
        result.reverse()
        
        return result
    
    except Exception as e:
        # Log the full error details
        print(f"Error in get_stock_data: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analysis/recent")
def get_recent_analyses(limit: int = Query(5, description="Number of analyses to return")):
    """
    Get recent stock analyses.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT id, chat_id, title, content, symbols, time_period, created_at
        FROM stock_analyses
        ORDER BY created_at DESC
        LIMIT %s
        """
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Convert to dict for JSON response
        result = [
            {
                "id": row[0],
                "chat_id": row[1],
                "title": row[2],
                "content": row[3],
                "symbols": row[4],
                "time_period": row[5],
                "created_at": row[6].isoformat()
            }
            for row in rows
        ]
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/symbols")
def get_available_symbols():
    """
    Get list of available stock symbols.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT symbol FROM stock_data
        ORDER BY symbol
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Extract symbols
        symbols = [row[0] for row in rows]
        
        return {"symbols": symbols}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def get_data_status():
    """
    Get status of the stock data in the database.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total count of rows
        cursor.execute("SELECT COUNT(*) FROM stock_data")
        total_count = cursor.fetchone()[0]
        
        # Get count by symbol
        cursor.execute("""
        SELECT symbol, COUNT(*) as count, MIN(timestamp) as earliest, MAX(timestamp) as latest
        FROM stock_data
        GROUP BY symbol
        ORDER BY count DESC
        """)
        
        symbol_counts = [
            {
                "symbol": row[0],
                "count": row[1],
                "earliest_data": row[2].isoformat() if row[2] else None,
                "latest_data": row[3].isoformat() if row[3] else None
            }
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return {
            "total_records": total_count,
            "symbols_data": symbol_counts,
            "has_data": total_count > 0
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
