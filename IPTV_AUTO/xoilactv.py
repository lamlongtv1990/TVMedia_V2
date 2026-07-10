import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import random
import urllib3

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# CẤU HÌNH
# ============================================
BASE_URL = "https://xoilac365ll.cc"
OUTPUT_FILE = "xoilactv.m3u"
USE_PROXY = False  # Khuyên bạn nên OFF vì các proxy free trong list hầu hết đã chết hoặc bị Cloudflare block (log báo Proxy error)
VIETNAM_TZ = timezone(timedelta(hours=7))

# Khởi tạo session với HTTPAdapter tùy biến để ép SNI khi gọi IP (Sửa lỗi SSLV3_ALERT_HANDSHAKE_FAILURE)
class ForcedIPAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, host_header, **kwargs):
        self.host_header = host_header
        super().__init__(kwargs)
    def init_poolmanager(self, *args, **kwargs):
        kwargs['assert_hostname'] = self.host_header
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.verify = False

def get_vietnam_time():
    return datetime.now(VIETNAM_TZ)

# ============================================
# ⚡ BYPASS DNS & SSL HANDSHAKE (FIX CHÍ MẠNG)
# ============================================
def resolve_doh_and_setup_session():
    """Phân giải IP và cấu hình mã hóa TLS với SNI chuẩn để không bị lỗi Handshake"""
    hostname = urlparse(BASE_URL).hostname
    print(f"🔍 [DoH] Đang phân giải tên miền bị chặn: {hostname}...")
    
    ip = None
    try:
        res = requests.get(f"https://dns.google/resolve?name={hostname}&type=A", timeout=5)
        if res.status_code == 200:
            ans = res.json().get("Answer", [])
            if ans: ip = ans[0].get("data")
    except:
        pass

    if not ip:
        try:
            res = requests.get(f"https://cloudflare-dns.com/dns-query?name={hostname}&type=A", 
                               headers={"accept": "application/dns-json"}, timeout=5)
            if res.status_code == 200:
                ans = res.json().get("Answer", [])
                if ans: ip = ans[0].get("data")
        except:
            pass

    if ip:
        print(f"🎯 [DoH] Tìm thấy IP: {ip}. Ép cấu hình SNI chống lỗi SSL...")
        # Ép Requests khi kết nối vào IP này phải gửi SNI là hostname gốc
        session.mount(f"https://{ip}/", ForcedIPAdapter(host_header=hostname))
        return ip
    return None

def get_actual_base_url():
    """Lấy domain live cuối cùng"""
    parsed_origin = urlparse(BASE_URL)
    ip = resolve_doh_and_setup_session()
    
    try:
        if ip:
            url_target = f"https://{ip}/"
            headers = {"Host": parsed_origin.hostname, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = session.get(url_target, headers=headers, allow_redirects=True, timeout=10)
            actual = res.url
            if ip in actual:
                # Nếu không tự chuyển hướng, quét thẻ a tìm domain dạng .com/.net mới
                soup = BeautifulSoup(res.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    if 'http' in a['href'] and parsed_origin.hostname not in a['href']:
                        return f"{urlparse(a['href']).scheme}://{urlparse(a['href']).netloc}"
            else:
                return f"{urlparse(actual).scheme}://{urlparse(actual).netloc}"
    except Exception as e:
        print(f"⚠️ Lỗi DoH/SSL: {e}. Chuyển sang dùng domain sống dự phòng.")
        
    return "https://majinbuofficial.com"

# ============================================
# ⚙️ PARSE ENGINE THEO API MỚI (CHẮC CHẮN CÓ TRẬN)
# ============================================
def fetch_api_matches(base_url):
    """Gọi thẳng vào Endpoint API JSON mới của hệ thống Xôi Lạc"""
    print(f"📡 Đang kết nối API nguồn: {base_url}")
    
    # Endpoint API lấy danh sách trận hiện tại của hệ thống Xôi lạc
    api_url = f"{base_url}/api/match/list?page=1&limit=50&type=all"
    headers = {
        "Referer": f"{base_url}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    try:
        res = session.get(api_url, headers=headers, timeout=15)
        if res.status_code != 200:
            return []
            
        json_data = res.json()
        raw_matches = json_data.get('data', {}).get('items', json_data.get('data', []))
        
        parsed_matches = []
        for item in raw_matches:
            # LỌC BLV: Logic gốc của bạn (chỉ lấy trận có bình luận viên)
            # API mới trả về hẳn mảng blv hoặc thuộc tính số lượng blv_count
            blv_list = item.get('commentators', [])
            if not blv_list and item.get('blv_count', 0) == 0:
                continue # Bỏ qua trận không có BLV đúng chuẩn logic gốc
                
            # Đọc dữ liệu
            home_team = item.get('home_team', {}).get('name', 'Home')
            away_team = item.get('away_team', {}).get('name', 'Away')
            match_time_raw = item.get('match_time', int(time.time())) # Timestamp
            
            # Chuyển đổi timestamp sang string format tiêu đề gốc của bạn để không lỗi Regex phía sau
            dt_object = datetime.fromtimestamp(match_time_raw, tz=VIETNAM_TZ)
            time_str = dt_object.strftime('%H:%M')
            date_str = dt_object.strftime('%d/%m/%Y')
            title = f"{home_team} vs {away_team} lúc {time_str} ngày {date_str}"
            
            # Xác định trạng thái live
            is_live = item.get('is_live', False)
            live_status = 'living' if is_live else 'comming'
            
            # Lấy danh sách link stream (API mới trả về trực tiếp mảng link m3u8/embed, không cần cào trang con!)
            streams = []
            for stream_obj in item.get('links', []):
                url = stream_obj.get('m3u8') or stream_obj.get('url')
                if url and url.startswith('http'):
                    streams.append(url)
                    
            if not streams:
                continue
                
            match_dict = {
                'fid': str(item.get('id', '')),
                'hot': item.get('is_hot', False) or item.get('hot', 0) == 1,
                'live': live_status,
                'title': title,
            }
            
            # Map vào link1, link2 theo đúng cấu trúc biến của bạn
            for idx, stream_url in enumerate(streams, 1):
                match_dict[f'link{idx}'] = stream_url
                
            parsed_matches.append(match_dict)
            
        return parsed_matches
    except Exception as e:
        print(f"❌ Lỗi xử lý API JSON: {e}")
        return []

# ============================================
# TẠO FILE M3U (GIỮ NGUYÊN 100% LOGIC GỐC CỦA BẠN)
# ============================================
def create_m3u_file(matches, filename):
    try:
        all_streams = []
        for match in matches:
            link_keys = [k for k in match.keys() if k.startswith('link')]
            for key in link_keys:
                stream_url = match[key]
                if stream_url and stream_url.startswith('http'):
                    # Trích xuất thời gian dựa trên Title bằng Regex cũ của bạn
                    time_match = re.search(r'lúc\s+(\d{2}):(\d{2})', match['title'])
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else "00:00"
                    
                    date_match = re.search(r'ngày\s+(\d{2})/(\d{2})/(\d{4})', match['title'])
                    date_str = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}" if date_match else ""
                    
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
            
        m3u_content = "#EXTM3U\n"
        m3u_content += "# Xôi Lạc TV Playlist\n"
        m3u_content += f"# Total streams: {len(all_streams)}\n"
        m3u_content += f"# Generated: {get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)\n\n"
        
        for stream in all_streams:
            m3u_content += f'#EXTINF:-1 group-title="Xôi Lạc Z TV",{stream["title"]}\n'
            m3u_content += '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36\n'
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
# MAIN MAIN MAIN
# ============================================
def main():
    print("=" * 60)
    print("         🚀 FETCH MATCHES VIA API SYSTEM")
    print("=" * 60)
    
    # Bước 1: Lấy URL thật sự đang sống
    base_url = get_actual_base_url().rstrip('/')
    
    # Bước 2: Gọi API mới thu thập dữ liệu trận đấu
    matches = fetch_api_matches(base_url)
    total_matches = len(matches)
    
    print(f"\n📊 Total matches with BLV: {total_matches}")
    
    if total_matches > 0:
        print("\n📋 Sample matches:")
        for i, m in enumerate(matches[:5], 1):
            print(f"  {i}. {m['title']} | Live: {m['live']}")
            
        print("\n📊 Creating M3U file...")
        if create_m3u_file(matches, OUTPUT_FILE):
            hot_count = sum(1 for m in matches if m['hot'])
            living_count = sum(1 for m in matches if m['live'] == 'living')
            total_streams = sum(1 for m in matches for k in m.keys() if k.startswith('link') and m[k])
            
            print(f"\n📊 Statistics:")
            print(f"   🔥 Hot: {hot_count}")
            print(f"   🔴 Living: {living_count}")
            print(f"   🔗 Total streams: {total_streams}")
            print(f"\n✅ DONE! File saved: {OUTPUT_FILE}")
    else:
        print("⚠️ No matches with BLV found!")

if __name__ == "__main__":
    main()
