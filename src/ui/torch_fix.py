"""
Fix for PyTorch and Streamlit compatibility.
This patch is applied to resolve an issue where Streamlit's module watching
feature conflicts with PyTorch's custom class system.
"""

import sys
import importlib

def apply_torch_fix():
    """
    Apply a monkey patch to fix PyTorch compatibility with Streamlit.
    This function should be called at the start of the Streamlit app.
    """
    try:
        import torch._classes

        # Create a safe __getattr__ that won't break Streamlit's file watcher
        original_getattr = torch._classes.__getattr__
        
        def safe_getattr(self, attr):
            if attr == "__path__":
                # Return an object with a _path attribute that can be listed
                class MockPath:
                    _path = []
                return MockPath()
            return original_getattr(self, attr)
        
        # Apply the monkey patch
        torch._classes.__getattr__ = safe_getattr
        print("PyTorch compatibility patch applied")
    except ImportError:
        # PyTorch is not installed, no need for the fix
        print("PyTorch not found, skipping compatibility patch")
    except Exception as e:
        print(f"Failed to apply PyTorch compatibility patch: {e}")
