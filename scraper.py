"""
Shopee AMS → Google Sheets Scraper
Dùng cookie trực tiếp, không cần Selenium/Chrome
"""

import os
import json
import logging
from datetime import datetime

import requests
import gspread
from google.oauth2.service_account import Credentials

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG – đọc từ GitHub Secrets
# ══════════════════════════════════════════════════════════════════════════════

AMS_COOKIE       = os.environ["AMS_COOKIE"]
AMS_API_BASE     = "https://ams.ssc.shopee.com/vn/api/admin/asset/sku_map/list"
SPREADSHEET_ID   = os.environ["SPREADSHEET_ID"]
SHEET_NAME       = os.environ.get("SHEET_NAME", "AMS_Inventory")
GCP_SA_JSON      = os.environ["GCP_SERVICE_ACCOUNT_JSON"]
COUNT_PER_PAGE   = 100

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CÁC CỘT XUẤT RA SHEET
# ══════════════════════════════════════════════════════════════════════════════

COLUMNS = [
    "sku_id", "sku_name", "station_id", "station_name",
    "available_usage_quantity", "locked_usage_quantity",
    "available_storage_quantity", "locked_storage_quantity",
    "usage_quantity", "storage_quantity", "investigation_quantity",
    "pending_put_away_quantity", "unit_tracking", "consume_flag",
    "can_carry_outside", "print_status", "printed_quantity",
    "modify_version", "ctime", "mtime", "remark",
]

HEADERS = [
    "SKU ID", "SKU Name", "Station ID", "Station Name",
    "Available Usage Qty", "Locked Usage Qty",
    "Available Storage Qty", "Locked Storage Qty",
    "Usage Quantity", "Storage Quantity", "Investigation Qty",
    "Pending Put Away Qty", "Unit Tracking", "Consume Flag",
    "Can Carry Outside", "Print Status", "Printed Quantity",
    "Modify Version", "Created Time", "Modified Time", "Remark",
]

# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 1 – GỌI API
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_records() -> list:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Referer"   : "https://ams.ssc.shopee.com/",
        "Accept"    : "application/json, text/plain, */*",
        "Cookie"    : AMS_COOKIE,
    })

    all_records, page = [], 1

    while True:
        params = {"pageno": page, "count": COUNT_PER_PAGE}
        log.info(f"Gọi API trang {page}...")

        resp = session.get(AMS_API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retcode") != 0:
            raise RuntimeError(f"API lỗi: {data.get('message')} / {data.get('sub_message')}")

        records = data["data"]["list"]
        total   = data["data"]["total"]
        all_records.extend(records)
        log.info(f"  → {len(all_records)}/{total} records")

        if not records or len(all_records) >= total:
            break

        page += 1

    log.info(f"Tổng: {len(all_records)} records.")
    return all_records

# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 2 – GHI LÊN GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════════════════

def push_to_sheets(records: list):
    log.info("Kết nối Google Sheets...")

    sa_info = json.loads(GCP_SA_JSON)
    creds   = Credentials.from_service_account_info(
        sa_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=5000, cols=len(COLUMNS))
        log.info(f"Tạo sheet mới: {SHEET_NAME}")

    ws.clear()
    log.info("Đã xoá dữ liệu cũ.")

    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_row = [f"Cập nhật: {now_str}", f"Tổng: {len(records)} records"]

    rows = [meta_row, HEADERS]
    for r in records:
        row = []
        for col in COLUMNS:
            val = r.get(col, "")
            if col in ("ctime", "mtime") and val:
                try:
                    val = datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            row.append(val)
        rows.append(row)

    ws.update(range_name="A1", values=rows)

    # Format header
    col_end = _col_letter(len(COLUMNS))
    ws.format(f"A2:{col_end}2", {
        "textFormat"     : {"bold": True, "foregroundColor": {"red":1,"green":1,"blue":1}},
        "backgroundColor": {"red":0.16,"green":0.39,"blue":0.63},
    })

    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    log.info(f"✓ Ghi xong {len(records)} records → {url}")


def _col_letter(n):
    result = ""
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 50)
    log.info(f"START – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 50)

    records = fetch_all_records()
    push_to_sheets(records)

    log.info("DONE ✓")
