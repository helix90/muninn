#!/usr/bin/env python
"""
Simple script to apply database migrations
"""
from flask import Flask
from app.extensions import db, migrate
from alembic import command
from alembic.config import Config
import os

# Create minimal Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_dev')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
migrate.init_app(app, db)

with app.app_context():
    # Configure alembic
    alembic_cfg = Config('alembic.ini')

    # Run upgrade to head
    print("Running database migrations...")
    command.upgrade(alembic_cfg, 'head')
    print("Migration completed successfully!")
