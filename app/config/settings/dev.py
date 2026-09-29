from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
from .base import *
import os

DEBUG = os.getenv('DEMO_MODE', 'false').lower() != 'true'
ALLOWED_HOSTS = ['localhost', '127.0.0.1']