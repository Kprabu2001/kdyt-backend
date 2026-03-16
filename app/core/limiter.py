# app/core/limiter.py
# Shared slowapi Limiter instance.
# Import `limiter` into routes — never instantiate a second one.

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
