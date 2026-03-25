"""
Shared extension instances.
Kept separate from app factory to avoid circular imports.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
