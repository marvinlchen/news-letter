#!/usr/bin/env python3
"""
Check if today is a trading day for the A-share market (Shanghai and Shenzhen).
Trading days are weekdays (Mon-Fri) that are not holidays.
"""
from datetime import date, datetime
import sys

def is_trading_day(check_date=None):
    """Check if the given date is a trading day."""
    if check_date is None:
        check_date = date.today()
    
    # Check if it's a weekend
    if check_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False, "Weekend"
    
    # Hardcoded holidays for 2026 (Chinese A-share market)
    # Based on the 2026 Chinese holiday schedule
    holidays_2026 = [
        # New Year's Day
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
        # Spring Festival (Chinese New Year)
        date(2026, 1, 28), date(2026, 1, 29), date(2026, 1, 30),
        date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2), date(2026, 2, 3),
        # Qingming Festival (Tomb Sweeping Day)
        date(2026, 4, 4), date(2026, 4, 5), date(2026, 4, 6),
        # Labor Day
        date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3),
        date(2026, 5, 4), date(2026, 5, 5),
        # Dragon Boat Festival
        date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
        # Mid-Autumn Festival
        date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26),
        # National Day
        date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3),
        date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6),
        date(2026, 10, 7),
    ]
    
    if check_date in holidays_2026:
        return False, "Holiday"
    
    return True, "Trading day"

if __name__ == "__main__":
    check_date = date.today()
    
    # Allow checking a specific date via command line argument
    if len(sys.argv) > 1:
        try:
            check_date = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Error: Invalid date format. Use YYYY-MM-DD.")
            sys.exit(1)
    
    is_trading, reason = is_trading_day(check_date)
    
    if is_trading:
        print(f"{check_date} is a trading day.")
        sys.exit(0)
    else:
        print(f"{check_date} is NOT a trading day ({reason}).")
        sys.exit(1)
