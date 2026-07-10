import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import urllib3
import socket

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# CẤU HÌNH
# ============================================
BASE_URL = "https://xoilac365ll.cc"
PER_PAGE = 20
OUTPUT_FILE = "xoilactv.m3u"
VIETNAM_TZ = timezone(timedelta(hours=7))

# ============================================
# DNS 1.1.1.1 - RESOLVE THỦ CÔNG
# ============================================
def resolve_dns_1_1_1_1(hostname):
    """Resolve DNS bằng 1.1.1.1"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['1.1.1.1']
        answers = resolver.resolve(hostname, 'A')
        return [str(r) for r in answers]
    except:
        # Fallback: dùng socket.getaddrinfo với DNS mặc định
        try:
            return [socket.gethostbyname(hostname)]
        except:
            return None

def get_ip_for_host(hostname):
    """Lấy IP từ DNS 1.1.1.1"""
    ips = resolve_dns_1_1_1_1(hostname)
    if ips:
        return ips[0]
    return None

# ============================================
# HÀM LẤY URL THỰC TẾ SAU CHUYỂN HƯỚNG
# ============================================
def get_actual_base_url():
    try:
        # Dùng requests với IP đã resolve
        parsed = urlparse(BASE_URL)
        hostname = parsed.netloc
        ip = get_ip_for_host(hostname)
        
        if ip:
            # Tạo URL với IP
            url_with_ip = f"{parsed.scheme}://{ip}"
            if parsed.path:
                url_with_ip += parsed.path
            
            # Headers với Host đúng
            headers = {
                'Host': hostname,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url_with_ip, headers=headers, allow_redirects=True, timeout=15, verify=False)
            actual_url = response.url
            if not actual_url.endswith('/'):
                actual_url += '/'
            return actual_url
    except:
        pass
    
    # Fallback: dùng requests bình thường
    try:
        response = requests.get(BASE_URL, allow_redirects=True, timeout=15, verify=False)
        actual_url = response.url
        if not actual_url.endswith('/'):
            actual_url += '/'
        return actual_url
    except:
        if not BASE_URL.endswith('/'):
            return BASE_URL + '/'
        return BASE_URL

# ============================================
# HÀM TẠO HEADERS ĐỘNG
# ============================================
def build_dynamic_headers(no_encoding=False):
    actual_url = get_actual_base_url()
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
        headers["accept-encoding"] = "gzip, deflate, br"
    return headers

# ============================================
# HÀM LẤY DỮ LIỆU - DÙNG IP RESOLVE
# ============================================
def fetch_with_dns(url, headers):
    """Fetch dùng DNS 1.1.1.1"""
    parsed = urlparse(url)
    hostname = parsed.netloc
    ip = get_ip_for_host(hostname)
    
    if ip:
        # Tạo URL với IP
        url_with_ip = f"{parsed.scheme}://{ip}{parsed.path}"
        if parsed.query:
            url_with_ip += f"?{parsed.query}"
        
        # Headers với Host đúng
        headers['Host'] = hostname
        
        response = requests.get(url_with_ip, headers=headers, timeout=30, verify=False)
        return response
    
    # Fallback: dùng URL gốc
    return requests.get(url, headers=headers, timeout=30, verify=False)

# ============================================
# HÀM XỬ LÝ RESPONSE
# ============================================
def parse_response(response):
    if response.status_code != 200:
        return None
    try:
        return response.text
    except:
        try:
            return response.content.decode('utf-8', errors='ignore')
        except:
            return None

# ============================================
# HÀM LẤY URL STREAM TỪ LINK CON
# ============================================
def extract_url_stream_from_link(link_url):
    try:
        headers = build_dynamic_headers(True)
        response = fetch_with_dns(link_url, headers)
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
# HÀM LẤY STREAM LINKS TỪ TRANG CHI TIẾT
# ============================================
def extract_stream_links(url):
    try:
        headers = build_dynamic_headers(True)
        response = fetch_with_dns(url, headers)
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
# HÀM TÍNH TRẠNG THÁI LIVE
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
# HÀM TRÍCH XUẤT
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

def get_vietnam_time():
    return datetime.now(VIETNAM_TZ)

# ============================================
# HÀM PARSE 1 MATCH
# ============================================
def parse_match_from_element(item):
    link = item.select_one('a.redirectPopup')
    if not link:
        return None
    
    href = link.get('href', '')
    title = link.get('title', '').strip()
    
    footer_streamer = item.select_one('.grid-match__footer-center')
    blv_count = 0
    if footer_streamer:
        # Đếm số lượng commentator
        commentators = footer_streamer.select('a.commentator')
        blv_count = len(commentators)
    
    if blv_count == 0:
        return None
    
    if not title:
        href_parts = [p for p in href.split('/') if p]
        if href_parts:
            slug = href_parts[-1]
            time_find = re.search(r'-luc-(\d{2})(\d{2})', slug)
            date_find = re.search(r'-ngay-(\d{2})-(\d{2})-(\d{4})', slug)
            
            clean_name = slug
            if time_find: clean_name = clean_name.split('-luc-')[0]
            elif date_find: clean_name = clean_name.split('-ngay-')[0]
            clean_name = clean_name.replace('-', ' ').title()
            
            t_str = f"{time_find.group(1)}:{time_find.group(2)}" if time_find else "00:00"
            d_str = f"{date_find.group(1)}/{date_find.group(2)}/{date_find.group(3)}" if date_find else datetime.now().strftime("%d/%m/%Y")
            title = f"{clean_name} lúc {t_str} ngày {d_str}"
        else:
            title = f"{item.get('data-league', 'Match')} lúc 00:00 ngày {datetime.now().strftime('%d/%m/%Y')}"

    live_status = get_live_status_from_title(title)
    actual_base = get_actual_base_url().rstrip('/')
    
    is_hot = 'grid-match--is-hot' in item.get('class', []) or item.get('data-hot', '') == ' on '
    
    match = {
        'fid': item.get('data-fid', ''),
        'hot': is_hot,
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

# ============================================
# HÀM PARSE ALL MATCHES
# ============================================
def parse_all_matches(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    items = soup.select('.main-grid-match')
    
    matches = []
    for item in items:
        match = parse_match_from_element(item)
        if match:
            matches.append(match)
    return matches

# ============================================
# LẤY DỮ LIỆU 1 TRANG
# ============================================
def fetch_page(page):
    actual_base = get_actual_base_url().rstrip('/')
    url = f"{actual_base}/sport/football/load-more/home/page/{page}/per/{PER_PAGE}?t={int(time.time())}"
    
    try:
        print(f"📤 GET page {page}: {url}")
        headers = build_dynamic_headers(True)
        
        response = fetch_with_dns(url, headers)
        
        if response.status_code == 200:
            decoded_text = parse_response(response)
            if not decoded_text:
                print("❌ Không thể decode response")
                return None
            
            if not decoded_text.strip().startswith('{'):
                print(f"❌ Response không phải JSON: {decoded_text[:200]}")
                return None
            
            data = json.loads(decoded_text)
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
            print(f"❌ Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

# ============================================
# LẤY NHIỀU TRANG
# ============================================
def fetch_pages_until(page_target):
    all_matches = []
    total_pages = 0
    success = True
    
    print("=" * 60)
    print("        🚀 FETCH MATCHES WITH BLV ONLY")
    print("=" * 60)
    print(f"📊 Per page: {PER_PAGE} matches")
    print(f"📌 Only matches with BLV (number-blv > 0)")
    print(f"📌 Live status calculated from match time in title")
    print(f"📌 Output file: {OUTPUT_FILE}")
    print(f"🔧 DNS: 1.1.1.1 (Cloudflare)")
    print("=" * 60)
    
    for page in range(0, page_target + 1):
        result = fetch_page(page)
        if not result or not result.get('success'):
            print(f"❌ Failed to fetch page {page}")
            success = False
            break
        if page == 0:
            total_pages = result['data']['pagination'].get('total_pages', 0)
            print(f"📊 Total pages available: {total_pages}")
        
        matches = result['data'].get('matches', [])
        all_matches.extend(matches)
        print(f"   ✅ Page {page}: got {len(matches)} matches (total: {len(all_matches)})")
        
        time.sleep(0.5)
    
    print("=" * 60)
    return {'success': success, 'data': {'pagination': {'total_pages': total_pages}, 'matches': all_matches}}

# ============================================
# TẠO FILE M3U
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
                    
                    display_title = match['title']
                    clean_title = re.sub(r'lúc\s+\d{2}:\d{2}\s+', '', display_title)
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
            print("❌ No stream links found!")
            return False
        
        vn_time = get_vietnam_time()
        time_str = vn_time.strftime('%Y-%m-%d %H:%M:%S')
        
        m3u_content = "#EXTM3U\n"
        m3u_content += "# Xôi Lạc TV Playlist\n"
        m3u_content += f"# Total streams: {len(all_streams)}\n"
        m3u_content += f"# Generated: {time_str} (GMT+7)\n\n"
        
        for stream in all_streams:
            m3u_content += f'#EXTINF:-1 group-title="Xôi Lạc Z TV",{stream["title"]}\n'
            m3u_content += '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36\n'
            m3u_content += '#EXTVLCOPT:http-referrer=https://xlz.buzzscorelinez.com/\n'
            m3u_content += f'{stream["url"]}\n\n'
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        
        print(f"✅ M3U file created: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error creating M3U: {e}")
        return False

# ============================================
# MAIN
# ============================================
def main():
    TARGET_PAGE = 0
    data = fetch_pages_until(TARGET_PAGE)
    
    if data and data['success']:
        matches = data['data']['matches']
        total_matches = len(matches)
        
        print(f"\n📊 Total matches with BLV: {total_matches}")
        
        if total_matches > 0:
            print("\n📋 Sample matches:")
            for i, m in enumerate(matches[:5], 1):
                print(f"  {i}. {m['title']}")
                print(f"     FID: {m['fid']}, Hot: {m['hot']}, Live: {m['live']}")
                link_count = len([k for k in m.keys() if k.startswith('link')])
                if link_count > 0:
                    print(f"     Streams: {link_count}")
            
            print("\n📊 Creating M3U file...")
            if create_m3u_file(matches, OUTPUT_FILE):
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
            print("⚠️ No matches with BLV found!")
    else:
        print("❌ Failed to fetch data")

if __name__ == "__main__":
    main()
