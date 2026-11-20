-- Runs once when PostgreSQL initializes an empty volume.
-- Creates a separate database for integration tests.

CREATE DATABASE app_test;
