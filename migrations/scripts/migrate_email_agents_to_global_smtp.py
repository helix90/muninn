#!/usr/bin/env python3
"""
Migration Script: Email Agents to Global SMTP Configuration

This script migrates existing email agents from per-agent SMTP configuration
to the new global SMTP configuration pattern.

Changes:
- Removes smtp_server, smtp_port, use_tls, username, password, from_email from config
- Preserves to_email, cc_email, bcc_email, subject_template, body_template, html

Usage:
    python migrations/scripts/migrate_email_agents_to_global_smtp.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making changes
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app
from app.models import Job
from app.extensions import db


def migrate_email_agents(dry_run=False):
    """
    Migrate email agents to use global SMTP configuration.

    Args:
        dry_run: If True, only show what would be changed without making changes

    Returns:
        dict: Migration statistics
    """
    app = create_app()

    with app.app_context():
        # Find all email agents
        email_agents = Job.query.filter_by(job_type='email_agent', is_active=True).all()

        print(f"Found {len(email_agents)} email agent(s)")
        print()

        if not email_agents:
            print("No email agents found. Migration not needed.")
            return {
                'total': 0,
                'migrated': 0,
                'skipped': 0,
                'errors': 0
            }

        # Fields to remove (these are now in global config)
        smtp_fields = {
            'smtp_server', 'smtp_port', 'use_tls', 'use_ssl',
            'username', 'password', 'from_email'
        }

        # Fields to keep (per-agent configuration)
        keep_fields = {
            'to_email', 'cc_email', 'bcc_email',
            'subject_template', 'body_template', 'html'
        }

        stats = {
            'total': len(email_agents),
            'migrated': 0,
            'skipped': 0,
            'errors': 0
        }

        for agent in email_agents:
            print(f"Agent {agent.id}: {agent.name}")
            print(f"  Current config: {agent.config}")

            # Check if migration is needed
            has_smtp_fields = any(field in agent.config for field in smtp_fields)

            if not has_smtp_fields:
                print(f"  ✓ Already migrated (no SMTP fields found)")
                stats['skipped'] += 1
                print()
                continue

            try:
                # Create new config with only keep_fields
                new_config = {}
                removed_fields = []

                for key, value in agent.config.items():
                    if key in smtp_fields:
                        removed_fields.append(key)
                    elif key in keep_fields:
                        new_config[key] = value
                    else:
                        # Keep any other fields (future-proofing)
                        new_config[key] = value

                print(f"  Removed fields: {', '.join(removed_fields)}")
                print(f"  New config: {new_config}")

                if not dry_run:
                    agent.config = new_config
                    stats['migrated'] += 1
                    print(f"  ✓ Migrated successfully")
                else:
                    stats['migrated'] += 1
                    print(f"  ✓ Would migrate (dry-run mode)")

            except Exception as e:
                print(f"  ✗ Error migrating: {e}")
                stats['errors'] += 1

            print()

        if not dry_run:
            db.session.commit()
            print("✓ All changes committed to database")
        else:
            print("ℹ DRY RUN MODE - No changes were made")

        print()
        print("=== Migration Summary ===")
        print(f"Total email agents: {stats['total']}")
        print(f"Migrated: {stats['migrated']}")
        print(f"Skipped (already migrated): {stats['skipped']}")
        print(f"Errors: {stats['errors']}")

        return stats


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description='Migrate email agents to global SMTP configuration'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making changes'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Email Agent SMTP Configuration Migration")
    print("=" * 60)
    print()
    print(f"Started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    if not args.dry_run:
        print("⚠️  WARNING: This will modify your database!")
        print("⚠️  Make sure you have a backup before proceeding.")
        print()
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled.")
            return
        print()

    stats = migrate_email_agents(dry_run=args.dry_run)

    print()
    print(f"Completed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # Exit with error code if there were errors
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
