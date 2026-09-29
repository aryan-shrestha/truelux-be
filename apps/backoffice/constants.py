from zoneinfo import ZoneInfo

LOW_STOCK_THRESHOLD = 5
LOW_STOCK_LIMIT = 10
RECENT_ORDER_LIMIT = 5
SALES_WINDOW_DAYS = 30
# The shop's day: revenue "today" means today in Nepal, not in UTC.
SHOP_TIME_ZONE = ZoneInfo("Asia/Kathmandu")
