import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse

# ============================================
# CẤU HÌNH
# ============================================
BASE_URL_SOURCE = "https://raw.githubusercontent.com/leeshin5757/getout/main/txt/xoilactv"
PER_PAGE = 20
OUTPUT_FILE = "xoilactv.m3u"

# ============================================
# HÀM LẤY BASE_URL TỪ GITHUB
# ============================================
def get_base_url_from_github():
    try:
        print(f"📥 Đang lấy BASE_URL từ: {BASE_URL_SOURCE}")
        response = requests.get(BASE_URL_SOURCE, timeout=10)
        if response.status_code == 200:
            base_url = response.text.strip()
            if base_url:
                print(f"✅ Đã lấy được BASE_URL: {base_url}")
                return base_url
            else:
                print("⚠️ Nội dung file rỗng, sử dụng URL mặc định")
                return "https://xoilacz.vip"
        else:
            print(f"⚠️ Không thể lấy file (status: {response.status_code}), sử dụng URL mặc định")
            return "https://xoilacz.vip"
    except Exception as e:
        print(f"⚠️ Lỗi khi lấy BASE_URL: {e}, sử dụng URL mặc định")
        return "https://xoilacz.vip"

# ============================================
# CẬP NHẬT BASE_URL TOÀN CỤC
# ============================================
BASE_URL = get_base_url_from_github()

# ============================================
# HÀM LẤY URL THỰC TẾ SAU CHUYỂN HƯỚNG
# ============================================
def get_actual_base_url():
    global BASE_URL
    try:
        response = requests.get(BASE_URL, allow_redirects=True, timeout=10)
        actual_url = response.url
        if not actual_url.endswith('/'):
            actual_url += '/'
        return actual_url
    except Exception as e:
        print(f"⚠️ Không thể lấy URL thực tế: {e}")
        if not BASE_URL.endswith('/'):
            return BASE_URL + '/'
        return BASE_URL

# ... (Các hàm khác giữ nguyên từ fetch_pages_until trở xuống)

# ============================================
# MAIN
# ============================================
def main():
    print("=" * 60)
    print("        🚀 FETCH MATCHES WITH BLV ONLY")
    print("=" * 60)
    print(f"📌 Base URL: {BASE_URL}")
    print(f"📊 Per page: {PER_PAGE} matches")
    print(f"📌 Only matches with BLV (number-blv > 0)")
    print(f"📌 Live status calculated from match time in title")
    print(f"📌 Output file: {OUTPUT_FILE}")
    print("=" * 60)
    
    TARGET_PAGE = 0
    
    data = fetch_pages_until(TARGET_PAGE)
    
    if data and data['success']:
        matches = data['data']['matches']
        total_matches = len(matches)
        
        print(f"\n📊 Success: {data['success']}")
        print(f"📊 Total pages available: {data['data']['pagination'].get('total_pages', 0)}")
        print(f"📊 Total matches with BLV: {total_matches}")
        
        print("\n📋 Matches found:")
        for i, m in enumerate(matches[:5], 1):
            print(f"  {i}. {m['title']}")
            print(f"     FID: {m['fid']}, Hot: {m['hot']}, Live: {m['live']}")
            if any(k.startswith('link') for k in m.keys()):
                link_count = len([k for k in m.keys() if k.startswith('link')])
                print(f"     Streams: {link_count}")
        
        print("\n📊 Creating M3U file...")
        create_m3u_file(matches, OUTPUT_FILE)
        
        hot_count = sum(1 for m in matches if m['hot'])
        living_count = sum(1 for m in matches if m['live'] == 'living')
        end_count = sum(1 for m in matches if m['live'] == 'end')
        comming_count = sum(1 for m in matches if m['live'] == 'comming')
        total_streams = sum(1 for m in matches for k in m.keys() if k.startswith('link') and m[k])
        
        print(f"\n📊 Statistics:")
        print(f"   🔥 Hot: {hot_count}")
        print(f"   🔴 Living: {living_count}")
        print(f"   ✅ Ended: {end_count}")
        print(f"   ⏳ Coming: {comming_count}")
        print(f"   🔗 Total streams: {total_streams}")
        
        print(f"\n✅ DONE! File saved: {OUTPUT_FILE}")
    else:
        print("❌ Failed to fetch data")

if __name__ == "__main__":
    main()
