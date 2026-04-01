"""
Shared Flask extensions — instantiated here and initialised in create_app().
Import from this module to avoid circular imports.
"""
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf    = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
