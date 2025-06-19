import os
import logging
import shutil
from datetime import datetime
import sys

class LogManager:
    """Centralized log management for the Data Platform"""
    
    def __init__(self, base_dir="log_management"):
        """Initialize the log manager with the base log directory"""
        self.base_log_dir = base_dir
        self.setup_log_directories()
        
        # Configure root logger
        self.configure_root_logger()
    
    def setup_log_directories(self):
        """Create log directory structure if it doesn't exist"""
        # Create main log directory
        if not os.path.exists(self.base_log_dir):
            os.makedirs(self.base_log_dir, exist_ok=True)
        
        # Create subdirectories for different components
        components = ["airflow", "fastapi", "streamlit", "postgres", "minio", "system", "crawlers"]
        for component in components:
            component_dir = os.path.join(self.base_log_dir, component)
            os.makedirs(component_dir, exist_ok=True)
    
    def configure_root_logger(self):
        """Configure the root logger to use our centralized log system"""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Create handlers
        console_handler = logging.StreamHandler(sys.stdout)
        file_handler = logging.FileHandler(os.path.join(self.base_log_dir, "system", "system.log"))
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
    
    def get_logger(self, name, component="system"):
        """Get a logger configured for the specified component"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        
        # Remove any existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create log file path
        log_file = os.path.join(self.base_log_dir, component, f"{name}.log")
        
        # Create handlers
        file_handler = logging.FileHandler(log_file)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(file_handler)
        
        return logger
    
    def cleanup_old_logs(self, component="all", days_to_keep=30):
        """Clean up old log files"""
        now = datetime.now()
        
        components_to_clean = [component] if component != "all" else os.listdir(self.base_log_dir)
        
        for comp in components_to_clean:
            comp_dir = os.path.join(self.base_log_dir, comp)
            if os.path.isdir(comp_dir):
                for file in os.listdir(comp_dir):
                    file_path = os.path.join(comp_dir, file)
                    if os.path.isfile(file_path) and file.endswith('.log'):
                        file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if (now - file_modified).days > days_to_keep:
                            os.remove(file_path)
                            print(f"Removed old log: {file_path}")

    def migrate_existing_logs(self):
        """Migrate existing logs to the new structure"""
        # List of potential log directories in the project
        log_dirs = [
            "volume/logs",
            "volume/airflow/logs",
            "logs",
            "src/logs"
        ]
        
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                print(f"Migrating logs from: {log_dir}")
                # Determine target component based on path
                if "airflow" in log_dir:
                    target = "airflow"
                else:
                    target = "system"
                
                # Copy log files
                target_dir = os.path.join(self.base_log_dir, target)
                for root, _, files in os.walk(log_dir):
                    for file in files:
                        if file.endswith('.log'):
                            src_path = os.path.join(root, file)
                            dst_path = os.path.join(target_dir, file)
                            # If file already exists, append content
                            if os.path.exists(dst_path):
                                with open(src_path, 'r') as src, open(dst_path, 'a') as dst:
                                    dst.write(f"\n# Migrated content from {src_path} at {datetime.now()} #\n")
                                    dst.write(src.read())
                            else:
                                shutil.copy2(src_path, dst_path)
                            print(f"Migrated: {src_path} -> {dst_path}")

# Function to run the initial setup
def setup_log_management():
    """Set up centralized log management"""
    log_manager = LogManager()
    log_manager.migrate_existing_logs()
    return log_manager

# For testing/direct execution
if __name__ == "__main__":
    log_manager = setup_log_management()
    logger = log_manager.get_logger("test_logger", "system")
    logger.info("Log management system initialized successfully")
