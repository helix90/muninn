#!/usr/bin/env python3
"""Quick script to query database for debugging."""

import os
import sys
from sqlalchemy import create_engine, text

# Use the same database URL from config
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://muninn:muninn_pass@localhost:5432/muninn_dev')

engine = create_engine(DATABASE_URL)

print("=== Active Agents ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, name, job_type FROM jobs WHERE is_active = true ORDER BY id"))
    for row in result:
        print(f"ID: {row[0]}, Name: {row[1]}, Type: {row[2]}")

print("\n=== Agent Links ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, source_agent_id, target_agent_id, is_active FROM agent_links"))
    for row in result:
        print(f"Link {row[0]}: Agent {row[1]} -> Agent {row[2]} (active: {row[3]})")

print("\n=== Agent Runs by Agent ID ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT agent_id, COUNT(*) FROM agent_runs GROUP BY agent_id"))
    for row in result:
        print(f"Agent {row[0]}: {row[1]} runs total")

print("\n=== Recent Agent Runs (Last 10) ===")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT agent_id, status, started_at, completed_at, manual,
               input_event_ids, output_event_ids
        FROM agent_runs
        ORDER BY started_at DESC
        LIMIT 10
    """))
    for row in result:
        input_count = len(row[5]) if row[5] else 0
        output_count = len(row[6]) if row[6] else 0
        print(f"Agent {row[0]}: {row[1]} started {row[2]} (completed: {row[3]}) - "
              f"Input: {input_count} events, Output: {output_count} events, Manual: {row[4]}")

print("\n=== Events by Agent ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT agent_id, COUNT(*) FROM events GROUP BY agent_id"))
    for row in result:
        print(f"Agent {row[0]}: {row[1]} events created")

print("\n=== Agent Configurations ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, name, job_type, config FROM jobs WHERE is_active = true ORDER BY id"))
    for row in result:
        print(f"\nAgent {row[0]}: {row[1]} ({row[2]})")
        print(f"Config: {row[3]}")

print("\n=== Recent Events (Last 20) ===")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, agent_id, event_type, title, created_at
        FROM events
        ORDER BY created_at DESC
        LIMIT 20
    """))
    for row in result:
        print(f"Event {row[0]}: Agent {row[1]} - {row[2]} - '{row[3][:50]}...' at {row[4]}")
