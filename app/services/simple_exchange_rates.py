# app/services/simple_exchange_rates.py
import requests
from typing import Dict

class SimpleExchangeRates:
    """שירות פשוט לקבלת 5 שערי מטבעות נפוצים מול USD"""
    
    def __init__(self):
        # API חינמי לגמרי - לא צריך מפתח
        self.api_url = "https://api.exchangerate-api.com/v4/latest/USD"
        self.currencies = ["EUR", "GBP", "ILS", "JPY", "CAD"]  # 5 מטבעות נפוצים
        
    def get_rates(self) -> Dict[str, float]:
        """
        קבלת שערי חליפין עדכניים
        מחזיר: {"EUR": 0.85, "GBP": 0.73, "ILS": 3.7, "JPY": 110.0, "CAD": 1.25}
        """
        
        try:
            print("Fetching exchange rates from API...")
            
            # קריאה ל-API
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            all_rates = data.get("rates", {})
            
            # סינון רק המטבעות שאנחנו רוצים
            filtered_rates = {}
            for currency in self.currencies:
                if currency in all_rates:
                    filtered_rates[currency] = round(all_rates[currency], 4)
                else:
                    print(f"Warning: {currency} not found in API response")
            
            print(f"Successfully fetched rates for {len(filtered_rates)} currencies")
            return filtered_rates
            
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return self._get_fallback_rates()
        except Exception as e:
            print(f"Unexpected error: {e}")
            return self._get_fallback_rates()
    
    def _get_fallback_rates(self) -> Dict[str, float]:
        """שערים בסיסיים במקרה של בעיה"""
        print("Using fallback exchange rates")
        return {
            "EUR": 0.85,    # יורו
            "GBP": 0.73,    # לירה שטרלינג  
            "ILS": 3.7,     # שקל ישראלי
            "JPY": 110.0,   # ין יפני
            "CAD": 1.25     # דולר קנדי
        }


# יצירת instance יחיד לכל האפליקציה
exchange_service = SimpleExchangeRates()


# פונקציה נוחה לשימוש מהיר:
def get_current_rates() -> Dict[str, float]:
    """פונקציה מהירה לקבלת שערים נוכחיים"""
    return exchange_service.get_rates()
