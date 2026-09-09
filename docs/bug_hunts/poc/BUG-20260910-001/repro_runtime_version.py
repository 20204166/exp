"""Read-only reproduction for source/installed-version divergence."""

import importlib.metadata
import sys

import maintenance

print(f"python={sys.executable}")
print(f"metadata={importlib.metadata.version('system-analyzer')}")
print(f"module={maintenance.__version__}")
print(f"maintenance_file={maintenance.__file__}")
print(f"window_file={__import__('window').__file__}")
