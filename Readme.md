# AutoRia Scraper

An automated Python application for scraping used car listings from AutoRia.

## Features
- Periodically scrapes the platform using schedule settings from `.env`.
- Avoids duplicates by storing data in a PostgreSQL database.
- Performs automated daily database dumps to the `/dumps` folder.
- Runs via Docker Compose for easy deployment.

## Getting Started

1. **Environment Variables**: Configure your `.env` file based on the provided settings. Make sure to set `SCRAPE_TIME` and `DUMP_TIME` (e.g., `12:00`).
2. **Build and Run**: Start the application using Docker Compose:
   ```bash
   docker-compose up -d --build