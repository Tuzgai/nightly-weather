#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
# ]
# ///
"""
Overnight Precipitation Alert Script
Checks recent precipitation and sends email summary for sprinkler decisions
"""

import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import tomllib
from pathlib import Path

# ============ CONFIGURATION ============

def load_config():
    """Load configuration from config.toml"""
    config_path = Path(__file__).parent / "config.toml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Please create config.toml with your settings."
        )

    with open(config_path, "rb") as f:
        return tomllib.load(f)

# ============ SCRIPT ============

def get_nws_observation_station(lat, lon):
    """Get the nearest NWS observation station for given coordinates"""
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    headers = {"User-Agent": "stu@stu.systems"}

    try:
        response = requests.get(points_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Get observation stations URL
        stations_url = data['properties']['observationStations']

        # Fetch the nearest station
        stations_response = requests.get(stations_url, headers=headers, timeout=10)
        stations_response.raise_for_status()
        stations_data = stations_response.json()

        if stations_data['features']:
            station_id = stations_data['features'][0]['properties']['stationIdentifier']
            return station_id
        else:
            raise Exception("No observation stations found for this location")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching NWS station: {e}")


def get_precipitation_data(station_id, hours=12):
    """Fetch precipitation observations from NWS station"""
    observations_url = f"https://api.weather.gov/stations/{station_id}/observations"
    headers = {"User-Agent": "stu@stu.systems"}

    try:
        response = requests.get(observations_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        observations = data['features']
        cutoff_time = datetime.now() - timedelta(hours=hours)
        seven_days_ago = datetime.now() - timedelta(days=7)

        total_precip_mm = 0
        observation_count = 0
        latest_observation = None

        # Dictionary to store daily totals: date -> precip_mm
        daily_totals = {}

        for obs in observations:
            obs_time_str = obs['properties']['timestamp']
            obs_time = datetime.fromisoformat(obs_time_str.replace('Z', '+00:00'))

            # Stop if we've gone back more than 7 days
            if obs_time < seven_days_ago.astimezone():
                break

            if not latest_observation:
                latest_observation = obs_time

            # Get precipitation (last hour)
            precip = obs['properties'].get('precipitationLastHour', {})
            if precip and precip.get('value') is not None:
                precip_mm = precip['value']

                # Add to recent total if within the specified hours
                if obs_time >= cutoff_time.astimezone():
                    total_precip_mm += precip_mm
                    observation_count += 1

                # Add to daily totals
                obs_date = obs_time.date()
                if obs_date not in daily_totals:
                    daily_totals[obs_date] = 0
                daily_totals[obs_date] += precip_mm

        # Convert mm to inches
        total_precip_inches = total_precip_mm / 25.4

        # Convert daily totals to inches and format
        daily_totals_inches = {
            date: round(mm / 25.4, 2)
            for date, mm in sorted(daily_totals.items(), reverse=True)
        }

        return {
            'total_mm': round(total_precip_mm, 2),
            'total_inches': round(total_precip_inches, 2),
            'observation_count': observation_count,
            'latest_observation': latest_observation,
            'station_id': station_id,
            'daily_totals': daily_totals_inches
        }

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching precipitation data: {e}")


def get_pressure_data(station_id):
    """Fetch barometric pressure observations from NWS station"""
    observations_url = f"https://api.weather.gov/stations/{station_id}/observations"
    headers = {"User-Agent": "SprinklerCheckScript/1.0"}

    try:
        response = requests.get(observations_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        observations = data['features']
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        current_pressure = None
        yesterday_pressure = None
        current_time = None
        yesterday_time = None

        for obs in observations:
            obs_time_str = obs['properties']['timestamp']
            obs_time = datetime.fromisoformat(obs_time_str.replace('Z', '+00:00'))

            # Get barometric pressure
            pressure = obs['properties'].get('barometricPressure', {})
            if pressure and pressure.get('value') is not None:
                pressure_pa = pressure['value']
                # Convert Pascals to hectopascals (1 hPa = 100 Pa)
                pressure_hpa = pressure_pa / 100

                # Get most recent pressure (current)
                if current_pressure is None:
                    current_pressure = pressure_hpa
                    current_time = obs_time

                # Get pressure from approximately 24 hours ago
                time_diff = abs((obs_time - yesterday.astimezone()).total_seconds())
                if time_diff < 3600:  # Within 1 hour of 24 hours ago
                    if yesterday_pressure is None or time_diff < abs((yesterday_time - yesterday.astimezone()).total_seconds()):
                        yesterday_pressure = pressure_hpa
                        yesterday_time = obs_time

        if current_pressure and yesterday_pressure:
            pressure_change = current_pressure - yesterday_pressure
        else:
            pressure_change = None

        return {
            'current_pressure': round(current_pressure, 1) if current_pressure else None,
            'yesterday_pressure': round(yesterday_pressure, 1) if yesterday_pressure else None,
            'pressure_change': round(pressure_change, 1) if pressure_change else None,
            'current_time': current_time,
            'yesterday_time': yesterday_time
        }

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching pressure data: {e}")


def get_forecast(lat, lon):
    """Fetch daily forecast from NWS"""
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    headers = {"User-Agent": "SprinklerCheckScript/1.0"}

    try:
        # Get grid endpoint for forecast
        response = requests.get(points_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        forecast_url = data['properties']['forecast']

        # Fetch forecast
        forecast_response = requests.get(forecast_url, headers=headers, timeout=10)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        periods = forecast_data['properties']['periods']

        if not periods:
            return None

        # Get today's forecast (first period is usually current day or tonight)
        today = periods[0]

        return {
            'name': today['name'],
            'temperature': today['temperature'],
            'temperature_unit': today['temperatureUnit'],
            'wind_speed': today['windSpeed'],
            'wind_direction': today['windDirection'],
            'short_forecast': today['shortForecast'],
            'detailed_forecast': today['detailedForecast']
        }

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching forecast: {e}")


def send_email(config, subject, body):
    """Send email via SMTP"""
    email_config = config['email']

    # Support both old (to_email) and new (to_emails) format for backward compatibility
    if 'to_emails' in email_config:
        to_emails = email_config['to_emails']
        if isinstance(to_emails, str):
            # Handle case where to_emails is accidentally a string
            to_emails = [to_emails]
    elif 'to_email' in email_config:
        # Old format: single email as string
        to_emails = [email_config['to_email']]
    else:
        raise Exception("No recipient email configured. Use 'to_emails' (list) or 'to_email' (string) in config")

    msg = MIMEMultipart()
    msg['From'] = email_config['from_email']
    msg['To'] = ', '.join(to_emails)
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(email_config['smtp_host'], email_config['smtp_port']) as server:
            server.starttls()
            server.login(email_config['smtp_username'], email_config['smtp_password'])
            server.send_message(msg)
        print(f"Email sent successfully to {len(to_emails)} recipient(s): {', '.join(to_emails)}")
    except Exception as e:
        raise Exception(f"Error sending email: {e}")


def main():
    """Main script execution"""
    try:
        # Load configuration
        config = load_config()

        location = config['location']
        sprinkler = config['sprinkler']

        latitude = location['latitude']
        longitude = location['longitude']
        hours_to_check = sprinkler['hours_to_check']
        threshold = sprinkler['threshold']

        print(f"Checking precipitation for last {hours_to_check} hours...")
        print(f"Location: {latitude}, {longitude}")

        # Get observation station
        station_id = get_nws_observation_station(latitude, longitude)
        print(f"Using NWS station: {station_id}")

        # Get precipitation data
        precip_data = get_precipitation_data(station_id, hours_to_check)

        # Get barometric pressure data
        print("Fetching barometric pressure data...")
        pressure_data = get_pressure_data(station_id)

        # Get forecast
        print("Fetching forecast...")
        forecast = get_forecast(latitude, longitude)

        # Determine sprinkler recommendation
        total_precip = precip_data['total_inches']
        if total_precip >= threshold:
            recommendation = "NO - Sufficient rainfall"
            emoji = "✓"
        else:
            recommendation = "YES - Run sprinkler"
            emoji = "✗"

        # Format daily totals
        daily_summary = []
        for date, inches in precip_data['daily_totals'].items():
            daily_summary.append(f"  {date.strftime('%Y-%m-%d (%a)')}: {inches:.2f} inches")

        daily_totals_text = "\n".join(daily_summary) if daily_summary else "  No data available"

        # Format barometric pressure information
        # Get threshold from config, default to 6 hPa if not specified
        pressure_threshold = sprinkler.get('pressure_change_threshold', 6)

        if pressure_data['current_pressure'] and pressure_data['pressure_change'] is not None:
            change = pressure_data['pressure_change']
            abs_change = abs(change)

            # Pressure drops are more significant than pressure rises
            if abs_change >= pressure_threshold and change < 0:
                significance = "SIGNIFICANT"
                trend = "falling"
            else:
                significance = "normal"
                if change > 0:
                    trend = "rising"
                else:
                    trend = "falling slightly"

            pressure_text = f"""  Current: {pressure_data['current_pressure']:.1f} hPa
  24h ago: {pressure_data['yesterday_pressure']:.1f} hPa
  Change: {change:+.1f} hPa ({significance} - {trend})
  Migraines are commonly triggered with pressures <1007 hPa or changes >6 hPa.
  """
        else:
            pressure_text = "  Data unavailable"

        # Format forecast
        if forecast:
            forecast_text = f"""{forecast['name'].upper()}:
  Temperature: {forecast['temperature']}°{forecast['temperature_unit']}
  Wind: {forecast['wind_speed']} {forecast['wind_direction']}
  Conditions: {forecast['short_forecast']}

  {forecast['detailed_forecast']}"""
        else:
            forecast_text = "  Forecast unavailable"

        # Build email body
        email_body = f"""Overnight Precipitation Report
{'=' * 50}

Time Period: Last {hours_to_check} hours
Location: {latitude}, {longitude}
Weather Station: {station_id}

PRECIPITATION TOTAL:
  {precip_data['total_inches']:.2f} inches ({precip_data['total_mm']:.2f} mm)

RUN SPRINKLER TODAY?
  {emoji} {recommendation}

BAROMETRIC PRESSURE (24-hour change):
{pressure_text}

FORECAST:
{forecast_text}

LAST 7 DAYS (Daily Totals):
{daily_totals_text}

Details:
  - Threshold: {threshold} inches
  - Hours of precipitation: {precip_data['observation_count']}
  - Latest observation: {precip_data['latest_observation']}

{'=' * 50}
Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        # Print to console
        print("\n" + email_body)

        # Send email
        subject = f"Weather update!"
        send_email(config, subject, email_body)

        print("\nScript completed successfully!")

    except Exception as e:
        error_msg = f"Error: {e}"
        print(error_msg)

        # Try to send error email
        try:
            config = load_config()
            send_email(config, "Weather update - ERROR", error_msg)
        except:
            print("Failed to send error notification email")

        return 1

    return 0


if __name__ == "__main__":
    exit(main())
