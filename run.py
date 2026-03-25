import sys
import os

# Add plugin directory and lib directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), "plugin"))
sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

from plugin.main import BrowserOmnibox

if __name__ == "__main__":
    BrowserOmnibox()
