import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# ============================================
# CẤU HÌNH
# ============================================
BASE_URL_SOURCE = "https://raw.githubusercontent.com/lamlongtv1990/TVMedia_V2/main/IPTV_AUTO/domain_xoilactv"
PER_PAGE = 20
OUTPUT_FILE = "xoilactv.m3u"
VIETNAM_TZ = timezone(timedelta(hours=7))
def get_vietnam_time():
    """Lấy thời gian hiện tại theo múi giờ Việt Nam (UTC+7)"""
    return datetime.now(VIETNAM_TZ)
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
# CẬP NHẬT BASE_URL
# ============================================
#BASE_URL = get_base_url_from_github()
BASE_URL = "https://yellow-bar-d6d1.lockerzlong.workers.dev"
# ============================================
# HÀM LẤY URL THỰC TẾ SAU CHUYỂN HƯỚNG
# ============================================
def get_actual_base_url():
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

# ============================================
# HÀM TẠO HEADERS ĐỘNG
# ============================================
def build_dynamic_headers():
    actual_url = get_actual_base_url()
    parsed = urlparse(actual_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    
    return {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "cache-control": "no-cache",
        "origin": domain,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": actual_url,
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }


# ============================================
# HÀM LẤY URL STREAM TỪ 1 LINK
# ============================================
def extract_url_stream_from_link(link_url):
    try:
        headers = build_dynamic_headers()
        response = requests.get(link_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
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
        headers = build_dynamic_headers()
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
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
# HÀM LẤY THỜI GIAN TỪ TITLE (HH:MM)
# ============================================
def extract_time_from_title(title):
    try:
        time_match = re.search(r'lúc\s+(\d{2}):(\d{2})', title)
        if time_match:
            return f"{time_match.group(1)}:{time_match.group(2)}"
        return "00:00"
    except Exception:
        return "00:00"


# ============================================
# HÀM LẤY NGÀY TỪ TITLE (DD/MM/YYYY)
# ============================================
def extract_date_from_title(title):
    try:
        date_match = re.search(r'ngày\s+(\d{2})/(\d{2})/(\d{4})', title)
        if date_match:
            return f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
        return ""
    except Exception:
        return ""


# ============================================
# HÀM PARSE 1 MATCH
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
    
    actual_base = get_actual_base_url()
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
# LẤY 1 TRANG
# ============================================
def fetch_page(page):
    actual_base = get_actual_base_url().rstrip('/')
    url = f"{actual_base}/sport/football/load-more/home/page/{page}/per/{PER_PAGE}?t={int(time.time())}"
    
    try:
        print(f"📤 GET page {page}: {url}")
        headers = build_dynamic_headers()
        # ⚠️ THÊM DÒNG NÀY
        headers["accept-encoding"] = "gzip, deflate, br"
        
        # ⚠️ SỬA: dùng stream=True để xử lý nén tự động
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        
        if response.status_code == 200:
            # ⚠️ SỬA: dùng response.content (đã được giải nén tự động)
            content = response.content.decode('utf-8')
            
            if not content.strip():
                print(f"⚠️ Response rỗng")
                return None
                
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"📄 Response preview: {content[:200]}...")
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
            print(f"❌ Error: {response.status_code}")
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
    
    for page in range(0, page_target + 1):
        result = fetch_page(page)
        
        if not result or not result.get('success'):
            print(f"❌ Failed to fetch page {page}")
            success = False
            break
        
        if page == 0:
            total_pages = result['data']['pagination'].get('total_pages', 0)
        
        matches = result['data'].get('matches', [])
        all_matches.extend(matches)
        print(f"   ✅ Page {page}: got {len(matches)} matches (total: {len(all_matches)})")
        
        time.sleep(0.5)
    
    return {
        'success': success,
        'data': {
            'pagination': {'total_pages': total_pages},
            'matches': all_matches
        }
    }


# ============================================
# TẠO FILE M3U
# ============================================
def create_m3u_file(matches, filename="tv.m3u"):
    try:
        all_streams = []
        
        for match in matches:
            link_keys = [k for k in match.keys() if k.startswith('link')]
            for key in link_keys:
                stream_url = match[key]
                if stream_url and stream_url.startswith('http'):
                    # Lấy thời gian và ngày từ title
                    time_str = extract_time_from_title(match['title'])
                    date_str = extract_date_from_title(match['title'])
                    
                    # Tạo tiêu đề mới: 🔥⏳03:00 Brazil vs Na Uy ngày 06/07/2026
                    display_title = match['title']
                    
                    # Thay thế "lúc HH:MM" và "ngày DD/MM/YYYY" bằng format mới
                    # Xóa phần "lúc HH:MM" và "ngày DD/MM/YYYY" khỏi title
                    clean_title = re.sub(r'lúc\s+\d{2}:\d{2}\s+', '', display_title)
                    clean_title = re.sub(r'ngày\s+\d{2}/\d{2}/\d{4}', '', clean_title).strip()
                    
                    # Xây dựng tiêu đề mới
                    new_title = ""
                    
                    # Thêm icon live
                    #if match['live'] == 'living':
                    #    new_title = "🔴"
                    #elif match['live'] == 'end':
                    #    new_title = "✅"
                    #elif match['live'] == 'comming':
                    #    new_title = "⏳"
                    
                    # Thêm hot
                    if match['hot']:
                        new_title += "🔥"
                    
                    # Thêm thời gian
                    if time_str:
                        new_title += time_str + " "
                    
                    # Thêm tên trận và ngày
                    new_title += clean_title
                    
                    # Nếu chưa có ngày trong title, thêm vào
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
        # Lấy thời gian Việt Nam
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
        print(f"   Total streams: {len(all_streams)}")
        return True
    except Exception as e:
        print(f"❌ Error creating M3U: {e}")
        return False


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
        #purge_jsdelivr_cache()
        
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

#def purge_jsdelivr_cache():
#    print("⚡ Đang gửi yêu cầu xóa cache đến jsDelivr CDN...")
    # Thêm tiền tố /purge/ vào trước URL của jsDelivr để xóa cache ngay lập tức
#    purge_url = "https://purge.jsdelivr.net/gh/lamlongtv1990/TVMedia_V2@main/IPTV_AUTO/xoilactv.m3u"
#    
#    try:
#        res = requests.get(purge_url, timeout=10)
#        if res.status_code == 200:
#            data = res.json()
#            if data.get('id'):
#                print("✅ Ép jsDelivr xóa bản lưu cũ thành công!")
#            else:
#                print(f"⚠️ jsDelivr phản hồi lạ: {data}")
#        else:
#            print(f"⚠️ API Purge phản hồi mã lỗi: {res.status_code}")
#    except Exception as e:
#        print(f"❌ Không thể dọn dẹp cache: {e}")
        
if __name__ == "__main__":
    main()
