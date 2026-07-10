import requests
import json
import re
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import urllib3

# Tắt cảnh báo SSL do ta sẽ gọi bằng IP thay vì Domain ở bước dò tìm
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# CẤU HÌNH BỎ CHẶN DNS
# ============================================
# Domain gốc bị chặn DNS
TARGET_HOST = "xoilac365ll.cc" 
# IP Anycast công cộng của Cloudflare (Nhà mạng VN không chặn dải IP này)
CLOUDFLARE_IP = "104.21.74.212"  

OUTPUT_FILE = "xoilactv.m3u"
VIETNAM_TZ = timezone(timedelta(hours=7))

session = requests.Session()
session.verify = False

def get_vietnam_time():
    return datetime.now(VIETNAM_TZ)

# ============================================
# HÀM ĐỘT PHÁ: ĐI XUYÊN QUA CHẶN DNS ĐỂ LẤY DOMAIN MỚI
# ============================================
def get_actual_base_url():
    # Gửi request thẳng tới IP Cloudflare nhưng gắn Host của Xôi Lạc
    url_via_ip = f"https://{CLOUDFLARE_IP}/"
    headers = {
        "Host": TARGET_HOST,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    }
    
    try:
        print(f"📡 Đang kết nối trực tiếp tới IP Cloudflare ({CLOUDFLARE_IP}) để dò domain mới...")
        # Sử dụng allow_redirects=True để hứng domain cuối cùng sau khi hệ thống tự chuyển hướng
        response = session.get(url_via_ip, headers=headers, timeout=15, allow_redirects=True)
        
        # Nếu thành công, lấy domain thực tế từ response.url
        actual_url = response.url
        parsed = urlparse(actual_url)
        
        # Nếu kết quả trả về vẫn dính IP Cloudflare, kiểm tra xem có domain mới trong lịch sử chuyển hướng không
        if parsed.netloc == CLOUDFLARE_IP and response.history:
            for resp in response.history:
                if 'location' in resp.headers:
                    loc = resp.headers['location']
                    if "http" in loc:
                        p = urlparse(loc)
                        return f"{p.scheme}://{p.netloc}"
        
        # Trường hợp trả về đúng domain sạch không bị chặn (VD: majinbuofficial.com)
        if parsed.netloc and parsed.netloc != CLOUDFLARE_IP:
            return f"{parsed.scheme}://{parsed.netloc}"
            
    except Exception as e:
        print(f"⚠️ Không thể dò tự động qua IP Cloudflare do: {e}")
    
    # [HẠNH CHÓT]: Nếu cách trên thất bại, điền thẳng domain bạn đang xem được bằng trình duyệt vào đây
    fallback_domain = "https://majinbuofficial.com"
    print(f"🔄 Sử dụng domain cấu hình sẵn (Cố định): {fallback_domain}")
    return fallback_domain

# ============================================
# HEADERS CHO DOMAIN MỚI
# ============================================
def build_headers(domain):
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "referer": f"{domain}/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    }

# ============================================
# TRÍCH XUẤT CÁC LINK M3U8 CON
# ============================================
def extract_stream_links(match_url, domain):
    try:
        headers = build_headers(domain)
        res = session.get(match_url, headers=headers, timeout=12)
        if res.status_code != 200:
            return []
            
        # Tìm mộc chuỗi JSON chứa danh sách luồng stream
        match = re.search(r'list_stream\s*=\s*(\[.*?\]);', res.text, re.DOTALL)
        if match:
            list_stream = json.loads(match.group(1))
            urls = []
            for item in list_stream:
                if isinstance(item, list) and len(item) > 0:
                    url = str(item[0]).replace('\\/', '/')
                    if url.startswith('http'):
                        urls.append(url)
            if urls:
                return list(dict.fromkeys(urls))
                
        # Phương án dự phòng bằng quét chuỗi Regex m3u8 trực tiếp
        m3u8_links = re.findall(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', res.text)
        if m3u8_links:
            return list(set(m3u8_links))
    except Exception:
        pass
    return []

# ============================================
# PARSE DỮ LIỆU TRẬN ĐẤU TỪ HTML
# ============================================
def parse_html_robust(html_content, domain):
    soup = BeautifulSoup(html_content, 'html.parser')
    matches = []
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link['href']
        if not href or href == '#' or 'sport/football' in href or href.startswith('javascript'):
            continue
            
        title = link.get('title', link.get_text()).strip()
        if not title or len(title) < 6:
            continue

        full_url = href if href.startswith('http') else f"{domain.rstrip('/')}/{href.lstrip('/')}"
        
        # Tránh trùng lặp trận
        if any(m['url'] == full_url for m in matches):
            continue
            
        print(f"   ⚽ Phát hiện trận: {title}")
        streams = extract_stream_links(full_url, domain)
        
        if streams:
            matches.append({'title': title, 'url': full_url, 'streams': streams})
            print(f"      ✅ Đã lấy được {len(streams)} link stream.")
        else:
            print(f"      ❌ Trận này chưa có link hoặc lỗi nguồn phát.")
            
    return matches

# ============================================
# CHƯƠNG TRÌNH CHÍNH
# ============================================
def main():
    # Bước 1: Vượt chặn DNS để lấy domain sạch đang hoạt động
    domain = get_actual_base_url()
    print("=" * 60)
    print(f"🚀 Khởi chạy thu thập dữ liệu từ Domain sạch: {domain}")
    print("=" * 60)
    
    # Bước 2: Truy cập thẳng vào domain mới thông qua DNS sạch của GitHub/Môi trường chạy
    print("📥 Đang cào dữ liệu danh sách trận đấu...")
    headers = build_headers(domain)
    all_matches = []
    
    try:
        response = session.get(domain, headers=headers, timeout=20)
        if response.status_code == 200:
            all_matches = parse_html_robust(response.text, domain)
    except Exception as e:
        print(f"❌ Lỗi khi tải dữ liệu từ domain mới: {e}")

    # Bước 3: Xuất danh sách ra file .m3u
    if all_matches:
        m3u_content = "#EXTM3U\n"
        m3u_content += f"# Generated: {get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)\n\n"
        
        for m in all_matches:
            for idx, stream in enumerate(m['streams'], 1):
                m3u_content += f'#EXTINF:-1 group-title="Xôi Lạc TV",{m["title"]} - Link {idx}\n'
                m3u_content += '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n'
                m3u_content += f'{stream}\n\n'
                
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print(f"\n🎉 Thành công! Đã lưu thành công vào file: {OUTPUT_FILE}")
    else:
        print("\n❌ Thất bại: Không thu thập được dữ liệu. Vui lòng kiểm tra lại cấu hình fallback_domain.")

if __name__ == "__main__":
    main()
