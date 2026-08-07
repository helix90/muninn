-- Muninn Database Initialization Script
-- This script creates the necessary databases for development and testing

-- Create test database
CREATE DATABASE muninn_test;

-- Grant privileges to muninn_user
GRANT ALL PRIVILEGES ON DATABASE muninn_dev TO muninn_user;
GRANT ALL PRIVILEGES ON DATABASE muninn_test TO muninn_user;

-- Connect to test database and grant privileges
\c muninn_test;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muninn_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muninn_user;

-- Connect back to main database
\c muninn_dev;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO muninn_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO muninn_user; 