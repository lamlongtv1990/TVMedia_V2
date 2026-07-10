import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse
import random
import urllib3
import io

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# CẤU HÌNH
# ============================================
BASE_URL = "https://gnolia.com"
PER_PAGE = 20
OUTPUT_FILE = "xoilactv.m3u"

# ============================================
# PROXY CONFIG
# ============================================
USE_PROXY = True

# Danh sách proxy hoạt động tốt
PROXY_LIST = [
    "http://113.160.132.26:8080",        # VN - Elite, ổn định nhất
    "http://202.28.194.139:31280",       # VN
    "http://137.59.47.73:3128",          # VN - Transparent
    "socks5://160.22.17.4:9988",         # VN - SOCKS5
    "http://1.231.81.166:3128",          # KR
    "http://37.49.224.15:3128",          # EE
    "http://185.141.26.131:3128",        # RO
    "http://185.200.188.234:10001",      # RU
]

# Tạo session riêng
session = requests.Session()
session.verify = False

# Session cho fallback (không nén)
fallback_session = requests.Session()
fallback_session.verify = False
fallback_session.headers.update({'Accept-Encoding': 'identity'})

# ============================================
# HÀM LẤY URL THỰC TẾ SAU CHUYỂN HƯỚNG
# ============================================
def get_actual_base_url(use_proxy=False):
    try:
        proxies = get_random_proxy() if use_proxy and USE_PROXY else None
        response = session.get(
            BASE_URL, 
            allow_redirects=True, 
            timeout=15,
            proxies=proxies
        )
        actual_url = response.url
        if not actual_url.endswith('/'):
            actual_url += '/'
        return actual_url
    except Exception as e:
        print(f"⚠️ Không thể lấy URL thực tế: {e}")
        if not BASE_URL.endswith('/'):
            return BASE_URL + '/'
        return BASE_URL

# ============================================
# PROXY FUNCTIONS
# ============================================
def get_random_proxy():
    """Lấy proxy ngẫu nhiên"""
    if not USE_PROXY or not PROXY_LIST:
        return None
    
    # Ưu tiên proxy VN
    vn_proxies = [p for p in PROXY_LIST if '113.160.132.26' in p or '202.28.194.139' in p]
    if vn_proxies and random.random() < 0.7:
        proxy_str = random.choice(vn_proxies)
    else:
        proxy_str = random.choice(PROXY_LIST)
    
    return {
        "http": proxy_str,
        "https": proxy_str
    }

def check_proxy(proxy_dict):
    """Kiểm tra proxy có hoạt động không"""
    if not proxy_dict:
        return False
    try:
        test_url = "https://httpbin.org/ip"
        response = requests.get(
            test_url, 
            proxies=proxy_dict, 
            timeout=10, 
            verify=False
        )
        return response.status_code == 200
    except:
        return False

# ============================================
# HÀM TẠO HEADERS ĐỘNG
# ============================================
def build_dynamic_headers(no_encoding=False):
    actual_url = get_actual_base_url(False)
    parsed = urlparse(actual_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "cache-control": "no-cache",
        "origin": domain,
        "pragma": "no-cache",
        "referer": actual_url,
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }
    
    if no_encoding:
        headers["accept-encoding"] = "identity"
    else:
        # Nếu chưa cài thư viện brotli qua pip, hãy xóa bớt chữ ", br" đi
        headers["accept-encoding"] = "gzip, deflate, br"
    
    return headers

# ============================================
# HÀM XỬ LÝ RESPONSE (ĐÃ FIX LỖI NÉN DỮ LIỆU)
# ============================================
def parse_response(response):
    """Xử lý response, tận dụng requests tự giải nén dựa trên Content-Encoding"""
    if response.status_code != 200:
        return None
    
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' not in content_type:
        print(f"⚠️ Content-Type nhận được: {content_type}")
    
    try:
        # Thư viện requests tự động giải nén gzip, deflate, br hoàn chỉnh thông qua thuộc tính .text
        return response.text
    except Exception as e:
        print(f"⚠️ Không thể đọc dữ liệu dạng text ({e}), thử fallback về giải mã raw bytes...")
        try:
            return response.content.decode('utf-8', errors='ignore')
        except:
            return None

# ============================================
# HÀM LẤY URL THỰC TẾ CỦA DÒNG STREAM TỪ LINK CON
# ============================================
def extract_url_stream_from_link(link_url):
    try:
        headers = build_dynamic_headers(True)
        proxies = get_random_proxy() if USE_PROXY else None
        
        response = session.get(
            link_url, 
            headers=headers, 
            timeout=20,
            proxies=proxies
        )
        
        decoded_text = parse_response(response)
        if not decoded_text:
            return None
        
        soup = BeautifulSoup(decoded_text, 'html.parser')
        scripts = soup.select('script')
        
        for script in scripts:
            content = script.string if script.string else script.get_text()
            if content and 'var urlStream' in content:
                match = re.search(r'var\s+urlStream\s*=\s*["\']([^"\']+)["\'];', content)
                if match:
                    return match.group(1)
        return None
    except Exception:
        return None

# ============================================
# HÀM LẤY STREAM LINKS TỪ TRANG CHI TIẾT Trận đấu
# ============================================
def extract_stream_links(url):
    try:
        headers = build_dynamic_headers(True)
        proxies = get_random_proxy() if USE_PROXY else None
        
        response = session.get(
            url, 
            headers=headers, 
            timeout=20,
            proxies=proxies
        )
        
        decoded_text = parse_response(response)
        if not decoded_text:
            return []
        
        soup = BeautifulSoup(decoded_text, 'html.parser')
        scripts = soup.select('script')
        
        list_stream_script = None
        for script in scripts:
            html_content = script.string if script.string else script.get_text()
            if html_content and 'var list_stream' in html_content:
                list_stream_script = html_content
                break
        
        if not list_stream_script:
            return []
        
        pattern = r'var\s+list_stream\s*=\s*(\[.*?\]);'
        match = re.search(pattern, list_stream_script, re.DOTALL)
        if not match:
            return []
        
        list_stream_str = match.group(1)
        try:
            list_stream = json.loads(list_stream_str)
        except json.JSONDecodeError:
            return []
        
        final_urls = []
        for item in list_stream:
            if isinstance(item, list) and len(item) > 0:
                stream_url = str(item[0]).replace('\\/', '/')
                url_stream = extract_url_stream_from_link(stream_url)
                final_urls.append(url_stream if url_stream else stream_url)
        
        return list(dict.fromkeys(final_urls))
    except Exception:
        return []

# ============================================
# HÀM TÍNH TRẠNG THÁI LIVE TỪ TITLE
# ============================================
def get_live_status_from_title(title):
    try:
        time_match = re.search(r'lúc\s+(\d{2}):(\d{2})', title)
        if not time_match:
            return 'comming'
        
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        
        date_match = re.search(r'ngày\s+(\d{2})/(\d{2})/(\d{4})', title)
        if not date_match:
            return 'comming'
        
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3))
        
        match_time = datetime(year, month, day, hour, minute)
        now = datetime.now()
        
        if now < match_time:
            return 'comming'
        elif now >= match_time and now < match_time + timedelta(minutes=120):
            return 'living'
        else:
            return 'end'
            
    except Exception:
        return 'comming'

# ============================================
# HÀM TRÍCH XUẤT THỜI GIAN/NGÀY TỪ TIÊU ĐỀ
# ============================================
def extract_time_from_title(title):
    try:
        time_match = re.search(r'lúc\s+(\d{2}):(\d{2})', title)
        if time_match:
            return f"{time_match.group(1)}:{time_match.group(2)}"
        return "00:00"
    except Exception:
        return "00:00"

def extract_date_from_title(title):
    try:
        date_match = re.search(r'ngày\s+(\d{2})/(\d{2})/(\d{4})', title)
        if date_match:
            return f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
        return ""
    except Exception:
        return ""

# ============================================
# HÀM PARSE 1 TRẬN ĐẤU CỤ THỂ
# ============================================
def parse_match_from_element(item):
    link = item.select_one('a.redirectPopup')
    if not link:
        return None
    
    href = link.get('href', '')
    title = link.get('title', '')
    
    footer_center = item.select_one('.grid-match-item__footer-center')
    blv_count = 0
    
    if footer_center:
        for class_name in footer_center.get('class', []):
            if class_name.startswith('number-blv-'):
                try:
                    blv_count = int(class_name.replace('number-blv-', ''))
                except:
                    blv_count = 0
                break
    
    if blv_count == 0:
        return None
    
    live_status = get_live_status_from_title(title)
    
    actual_base = get_actual_base_url(False)
    actual_base = actual_base.rstrip('/')
    
    match = {
        'fid': item.get('data-fid', ''),
        'hot': item.get('data-hot', '0') == '1',
        'live': live_status,
        'href': href,
        'title': title,
        'random-streams': link.get('data-random-streams', '')
    }
    
    if href:
        full_url = actual_base + href
        stream_links = extract_stream_links(full_url)
        if stream_links:
            for i, stream_url in enumerate(stream_links, 1):
                match[f'link{i}'] = stream_url
    
    return match

def parse_all_matches(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    items = soup.select('.grid-matches__item-match')
    
    matches = []
    for item in items:
        match = parse_match_from_element(item)
        if match:
            matches.append(match)
    
    return matches

# ============================================
# LẤY DỮ LIỆU CỦA 1 TRANG (ĐÃ FIX KIỂM TRA JSON CHUẨN VÀ AN TOÀN)
# ============================================
def fetch_page(page):
    actual_base = get_actual_base_url(False).rstrip('/')
    url = f"{actual_base}/sport/football/load-more/home/page/{page}/per/{PER_PAGE}?t={int(time.time())}"
    
    try:
        print(f"📤 GET page {page}: {url}")
        headers = build_dynamic_headers()
        
        proxies = get_random_proxy() if USE_PROXY else None
        if proxies:
            print(f"    Using proxy: {proxies['http']}")
        
        response = session.get(
            url, 
            headers=headers, 
            timeout=30,
            proxies=proxies
        )
        
        if response.status_code == 200:
            decoded_text = parse_response(response)
            if not decoded_text:
                print("❌ Không thể giải mã dữ liệu (decoded_text rỗng)")
                return None
            
            try:
                # Thực hiện parse JSON trực tiếp, tránh kiểm tra thủ công chuỗi .startswith('{') dễ dính ký tự ẩn
                data = json.loads(decoded_text)
            except json.JSONDecodeError as e:
                print(f"❌ JSON Decode Error: Phản hồi không phải JSON cấu trúc chuẩn. Chi tiết: {e}")
                print(f"Dữ liệu nhận được (200 ký tự đầu): {decoded_text[:200]}")
                return None
                
            pagination = data.get('data', {}).get('pagination', {})
            html_content = data.get('data', {}).get('html', '')
            matches = parse_all_matches(html_content)
            
            return {
                'success': data.get('success', False),
                'data': {
                    'pagination': pagination,
                    'matches': matches
                }
            }
        else:
            print(f"❌ HTTP Error Code: {response.status_code}")
            return None
            
    except requests.exceptions.ProxyError as e:
        print(f"❌ Proxy Error: {e}, chuyển hướng sang phương thức không dùng proxy...")
        return fetch_page_without_proxy(page)
    except Exception as e:
        print(f"❌ Exception xảy ra: {e}")
        return fetch_page_without_proxy(page)

# ============================================
# FALLBACK - LẤY TRANG KHÔNG DÙNG PROXY KHI PROXY CHẾT
# ============================================
def fetch_page_without_proxy(page):
    actual_base = get_actual_base_url(False).rstrip('/')
    url = f"{actual_base}/sport/football/load-more/home/page/{page}/per/{PER_PAGE}?t={int(time.time())}"
    
    try:
        print(f"📤 GET page {page} (no proxy): {url}")
        headers = build_dynamic_headers(True)  # Ép kiểu dữ liệu thô (identity) không nén
        
        response = fallback_session.get(
            url, 
            headers=headers, 
            timeout=30
        )
        
        if response.status_code == 200:
            decoded_text = parse_response(response)
            if not decoded_text:
                print("❌ Không thể giải mã dữ liệu ở chế độ không proxy")
                return None
            
            try:
                data = json.loads(decoded_text)
            except json.JSONDecodeError:
                print("❌ Lỗi cấu trúc JSON trong phản hồi chế độ không proxy")
                return None
                
            pagination = data.get('data', {}).get('pagination', {})
            html_content = data.get('data', {}).get('html', '')
            matches = parse_all_matches(html_content)
            
            return {
                'success': data.get('success', False),
                'data': {
                    'pagination': pagination,
                    'matches': matches
                }
            }
        else:
            print(f"❌ Error không dùng proxy: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Fallback error: {e}")
        return None

# ============================================
# LẤY NHIỀU TRANG LIÊN TIẾP
# ============================================
def fetch_pages_until(page_target):
    all_matches = []
    total_pages = 0
    success = True
    
    for page in range(0, page_target + 1):
        result = fetch_page(page)
        
        if not result or not result.get('success'):
            print(f"❌ Thất bại khi cào trang {page}")
            success = False
            break
        
        if page == 0:
            total_pages = result['data']['pagination'].get('total_pages', 0)
        
        matches = result['data'].get('matches', [])
        all_matches.extend(matches)
        print(f"   ✅ Trang {page}: Tìm thấy {len(matches)} trận phù hợp (Tổng tích lũy: {len(all_matches)})")
        
        time.sleep(0.5)
    
    return {
        'success': success,
        'data': {
            'pagination': {'total_pages': total_pages},
            'matches': all_matches
        }
    }

# ============================================
# TẠO FILE M3U PLAYLIST
# ============================================
def create_m3u_file(matches, filename="xoilactv.m3u"):
    try:
        all_streams = []
        
        for match in matches:
            link_keys = [k for k in match.keys() if k.startswith('link')]
            for key in link_keys:
                stream_url = match[key]
                if stream_url and stream_url.startswith('http'):
                    time_str = extract_time_from_title(match['title'])
                    date_str = extract_date_from_title(match['title'])
                    
                    clean_title = re.sub(r'lúc\s+\d{2}:\d{2}\s+', '', match['title'])
                    clean_title = re.sub(r'ngày\s+\d{2}/\d{2}/\d{4}', '', clean_title).strip()
                    
                    new_title = ""
                    if match['hot']:
                        new_title += "🔥"
                    if time_str:
                        new_title += time_str + " "
                    new_title += clean_title
                    if date_str and date_str not in new_title:
                        new_title += f" ngày {date_str}"
                    
                    all_streams.append({
                        'title': new_title,
                        'url': stream_url,
                        'fid': match['fid'],
                        'hot': match['hot'],
                        'live': match['live']
                    })
        
        if not all_streams:
            print("❌ Không tìm thấy link luồng phát sóng (Stream links) hợp lệ nào!")
            return False
        
        m3u_content = "#EXTM3U\n"
        m3u_content += "# Xôi Lạc TV Playlist\n"
        m3u_content += f"# Total streams: {len(all_streams)}\n"
        m3u_content += f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for stream in all_streams:
            m3u_content += f'#EXTINF:-1 group-title="Xôi Lạc Z TV",{stream["title"]}\n'
            m3u_content += '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36\n'
            m3u_content += '#EXTVLCOPT:http-referrer=https://xlz.buzzscorelinez.com/\n'
            m3u_content += f'{stream["url"]}\n\n'
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        
        print(f"✅ Đã xuất file M3U thành công: {filename}")
        print(f"   Tổng số luồng đã ghi: {len(all_streams)}")
        return True
    except Exception as e:
        print(f"❌ Thất bại khi tạo file M3U: {e}")
        return False

# ============================================
# MAIN APPLICATION ENTRY POINT
# ============================================
def main():
    print("=" * 60)
    print("        🚀 FETCH MATCHES WITH BLV ONLY (OPTIMIZED)")
    print("=" * 60)
    print(f"📊 Per page: {PER_PAGE} matches")
    print(f"📌 Only matches with BLV (number-blv > 0)")
    print(f"📌 Live status calculated from match time in title")
    print(f"📌 Output file: {OUTPUT_FILE}")
    print(f"🔧 Proxy status: {'ON' if USE_PROXY else 'OFF'}")
    print("=" * 60)
    
    TARGET_PAGE = 0  # Bạn có thể thay đổi số lượng trang đích cần cào dữ liệu tại đây
    
    data = fetch_pages_until(TARGET_PAGE)
    
    if data and data['success']:
        matches = data['data']['matches']
        total_matches = len(matches)
        
        print(f"\n📊 Kết quả thành công: {data['success']}")
        print(f"📊 Tổng số trang có trên hệ thống: {data['data']['pagination'].get('total_pages', 0)}")
        print(f"📊 Số trận đấu có Bình Luận Viên lọc được: {total_matches}")
        
        print("\n📋 Top 5 trận đấu tìm thấy đầu tiên:")
        for i, m in enumerate(matches[:5], 1):
            print(f"  {i}. {m['title']}")
            print(f"     FID: {m['fid']}, Hot: {m['hot']}, Live: {m['live']}")
            if any(k.startswith('link') for k in m.keys()):
                link_count = len([k for k in m.keys() if k.startswith('link')])
                print(f"     Streams tìm được: {link_count}")
        
        print("\n📊 Đang tiến hành tạo tệp tin playlist M3U...")
        create_m3u_file(matches, OUTPUT_FILE)
        
        hot_count = sum(1 for m in matches if m['hot'])
        living_count = sum(1 for m in matches if m['live'] == 'living')
        end_count = sum(1 for m in matches if m['live'] == 'end')
        comming_count = sum(1 for m in matches if m['live'] == 'comming')
        total_streams = sum(1 for m in matches for k in m.keys() if k.startswith('link') and m[k])
        
        print(f"\n📊 Báo cáo Thống kê dữ liệu:")
        print(f"   🔥 Trận Hot: {hot_count}")
        print(f"   🔴 Đang Live: {living_count}")
        print(f"   ✅ Đã kết thúc: {end_count}")
        print(f"   ⏳ Sắp diễn ra: {comming_count}")
        print(f"   🔗 Tổng số liên kết phát trực tiếp thu được: {total_streams}")
        
        print(f"\n✅ HOÀN THÀNH QUY TRÌNH! File lưu tại: {OUTPUT_FILE}")
    else:
        print("❌ Thất bại, không thu thập được dữ liệu trận đấu.")

if __name__ == "__main__":
    main()
