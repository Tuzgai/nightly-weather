# Overnight Precipitation Alert Script

## Overview
This script retrieves overnight precipitation data from the National Weather Service (NWS) and sends an email summary to help you decide whether to run your sprinkler system.

## Components

### Weather Data Source
- **API**: Weather.gov/NWS (National Weather Service)
- **Advantages**: Free, no API key required, official NOAA data
- **Coverage**: United States only

### Email Delivery
- **Method**: Standard SMTP
- **Configuration**: Requires SMTP server credentials (host, port, username, password)

### Language
- **Python 3**: Simple, readable, with excellent libraries for HTTP requests and email
- **Package Management**: uv (inline script dependencies, no venv needed)

## Git Workflow

- Commit after each complete feature
- Use clear, descriptive commit messages
- Always include Co-Authored-By line with correct model name:
  ```
  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
  ```

## How It Works
1. Fetches recent precipitation data from NWS for your location
2. Calculates total overnight precipitation
3. Sends an email with the results
4. Can be scheduled to run automatically (e.g., via cron)

## Setup Required

1. **Create your config file**:
   ```bash
   cp config.toml.example config.toml
   ```

2. **Edit `config.toml`** with your settings:
   - Location coordinates (latitude/longitude)
   - SMTP server credentials
   - Email addresses (from/to)
   - Precipitation threshold (optional, defaults to 0.1 inches)
   - Hours to check (optional, defaults to 12 hours)

3. **Note**: `config.toml` is gitignored to protect your credentials

## Running the Script

### Manual Execution
```bash
cd /home/tuzgai/repos/nightly-weather
uv run sprinkler_check.py
```

Or make it executable and run directly:
```bash
chmod +x sprinkler_check.py
./sprinkler_check.py
```

### Scheduled Execution
The script can be scheduled to run automatically each morning using cron. Add to your crontab:
```bash
# Run at 6 AM daily
0 6 * * * cd /home/tuzgai/repos/nightly-weather && uv run sprinkler_check.py
```
