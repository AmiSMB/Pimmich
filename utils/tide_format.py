from datetime import datetime, timedelta


FRENCH_WEEKDAYS = {
    "Mon": "Lun",
    "Tue": "Mar",
    "Wed": "Mer",
    "Thu": "Jeu",
    "Fri": "Ven",
    "Sat": "Sam",
    "Sun": "Dim",
}


def format_tide_day(tide_dt: datetime, language: str = "fr", compact: bool = False) -> str:
    """Format a tide date in French or English for the slideshow and web UI."""
    today = datetime.now().astimezone().date()
    tide_date = tide_dt.date()
    is_english = language == "en"

    if tide_date == today:
        if is_english:
            return "Today"
        return "Auj." if compact else "Aujourd'hui"
    if tide_date == today + timedelta(days=1):
        if is_english:
            return "Tomorrow"
        return "Dem." if compact else "Demain"

    weekday = tide_dt.strftime("%a")
    return weekday if is_english else FRENCH_WEEKDAYS.get(weekday, weekday)


def format_tide_type(tide_type: str, language: str = "fr", compact: bool = False) -> str:
    """Return a localized tide label."""
    is_high = tide_type == "high"
    if language == "en":
        if compact:
            return "High" if is_high else "Low"
        return "High tide" if is_high else "Low tide"
    if compact:
        return "PM" if is_high else "BM"
    return "Pleine Mer" if is_high else "Basse Mer"
