import requests
import json
import re
from bs4 import BeautifulSoup
import time
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import urllib3

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# CẤU HÌNH GỐC (Bị chặn DNS tại VN)
# ============================================
BLOCKED_BASE_URL = "https://xoilac365ll.cc"
OUTPUT_FILE = "xoilactv.m3u"
VIETNAM_TZ = timezone(timedelta(hours=7))

session = requests.Session()
session.verify = False

def get_vietnam_time():
    return datetime.now(VIETNAM_TZ)

# ============================================
# ⚡ BYPASS DNS: GỌI ĐẾN GOOGLE DNS OVER HTTPS
# ============================================
def resolve_blocked_domain(domain_url):
    """
    Hỏi thẳng Google DNS qua HTTPS xem IP thực của domain bị chặn là gì
    để kết nối trực tiếp không qua DNS nhà mạng.
    """
    parsed_url = urlparse(domain_url)
    hostname = parsed_url.hostname
    
    print(f"🔍 Đang phân giải DNS Over HTTPS cho domain bị chặn: {hostname}...")
    try:
        # Gọi API DNS của Google
        dns_url = f"https://dns.google/resolve?name={hostname}&type=A"
        res = requests.get(dns_url, timeout=10)
        if res.status_code == 200:
            dns_data = res.json()
            answers = dns_data.get("Answer", [])
            if answers:
                # Lấy IP đầu tiên tìm được
                ip = answers[0].get("data")
                print(f"🎯 Tìm thấy IP thực của Xôi Lạc: {ip}")
                return ip
    except Exception as e:
        print(f"⚠️ Không thể phân giải DoH qua Google: {e}")
    
    # Fallback dự phòng nếu Google DNS lỗi (Thử qua Cloudflare)
    try:
        dns_url = f"https://cloudflare-dns.com/dns-query?name={hostname}&type=A"
        res = requests.get(dns_url, headers={"accept": "application/dns-json"}, timeout=10)
        if res.status_code == 200:
            dns_data = res.json()
            answers = dns_data.get("Answer", [])
            if answers:
                ip = answers[0].get("data")
                print(f"🎯 Tìm thấy IP thực (Cloudflare DoH): {ip}")
                return ip
    except Exception as e:
        print(f"⚠️ Không thể phân giải DoH qua Cloudflare: {e}")
        
    return None

# ============================================
# TỰ ĐỘNG LẤY DOMAIN MỚI NHẤT QUA IP ĐÃ BYPASS
# ============================================
def get_actual_base_url():
    ip = resolve_blocked_domain(BLOCKED_BASE_URL)
    parsed_origin = urlparse(BLOCKED_BASE_URL)
    
    if ip:
        try:
            # Gửi request thẳng bằng IP nhưng giữ Header Host để Cloudflare của Xôi Lạc nhận diện đúng
            headers = {"Host": parsed_origin.hostname, "User-Agent": "Mozilla/5.0"}
            target_url = f"{parsed_origin.scheme}://{ip}/"
            
            print(f"🔗 Đang kết nối trực tiếp qua IP: {target_url}")
            response = session.get(target_url, headers=headers, allow_redirects=True, timeout=15)
            
            # Nếu hệ thống chuyển hướng (Redirect) sang domain mới (như majinbuofficial.com)
            actual_url = response.url
            if ip in actual_url:
                # Nếu không tự redirect thì thử đọc thẻ meta refresh hoặc thẻ a trong HTML công bố domain mới
                soup = BeautifulSoup(response.text, 'html.parser')
                # Tìm các link ngoài dạng .com/.net xem có domain mới không
                for a in soup.find_all('a', href=True):
                    if 'http' in a['href'] and parsed_origin.hostname not in a['href']:
                        parsed_new = urlparse(a['href'])
                        return f"{parsed_new.scheme}://{parsed_new.netloc}"
            else:
                parsed_new = urlparse(actual_url)
                return f"{parsed_new.scheme}://{parsed_new.netloc}"
        except Exception as e:
            print(f"⚠️ Lỗi kết nối qua IP: {e}")
            
    # BƯỚC DỰ PHÒNG CUỐI CÙNG: Nếu lấy tự động thất bại hoàn toàn, điền thẳng domain bạn biết đang sống
    print("⚠️ Không lấy tự động được domain mới qua DNS Bypass. Sử dụng domain dự phòng cứng...")
    return "https://majinbuofficial.com"

# ============================================
# HEADERS GIẢ LẬP TRÌNH DUYỆT
# ============================================
def build_headers(domain):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "referer": f"{domain}/",
        "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    }

# ============================================
# TRÍCH XUẤT CÁC LINK M3U8 TỪ TRANG CHI TIẾT
# ============================================
def extract_stream_links(match_url, domain):
    try:
        headers = build_headers(domain)
        res = session.get(match_url, headers=headers, timeout=15)
        if res.status_code != 200:
            return []
            
        # Dùng Regex quét trực tiếp toàn bộ chuỗi có định dạng .m3u8 trong mã nguồn (Nhanh và chính xác nhất)
        m3u8_links = re.findall(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', res.text)
        
        # Lọc sạch các ký tự escape dấu gạch chéo ngược \/ thường có trong json chuỗi
        cleaned_links = [link.replace('\\/', '/') for link in m3u8_links]
        
        # Loại bỏ bớt link trùng
        return list(set(cleaned_links))
    except Exception:
        return []

# ============================================
# QUÉT TOÀN BỘ TRẬN ĐẤU (CHẤP MỌI ĐỔI THAY CLASS HTML)
# ============================================
def parse_html_robust(html_content, domain):
    soup = BeautifulSoup(html_content, 'html.parser')
    matches = []
    
    # Quét tất cả thẻ <a> có thuộc tính href chứa thông tin trận đấu
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link['href']
        if not href or href == '#' or 'sport/football' in href or 'javascript' in href:
            continue
            
        title = link.get('title', link.get_text()).strip()
        if not title or len(title) < 5:
            continue

        full_url = href if href.startswith('http') else f"{domain.rstrip('/')}/{href.lstrip('/')}"
        
        # Né trùng lặp trận
        if any(m['url'] == full_url for m in matches):
            continue
            
        print(f"   ⚽ Phát hiện: {title}")
        streams = extract_stream_links(full_url, domain)
        
        if streams:
            matches.append({'title': title, 'url': full_url, 'streams': streams})
            print(f"      ✅ Đã lấy thành công {len(streams)} link luồng m3u8.")
        else:
            print(f"      ❌ Không tìm thấy link m3u8 nào hoạt động.")
            
    return matches

# ============================================
# ENGINE KHỞI CHẠY
# ============================================
def main():
    # Bước 1: Vượt chặn DNS để lấy domain thực tế đang chạy
    domain = get_actual_base_url()
    print("=" * 60)
    print(f"🌐 Domain đích đang xử lý: {domain}")
    print("=" * 60)
    
    print("📥 Tiến hành cào dữ liệu trang chủ...")
    headers = build_headers(domain)
    
    all_matches = []
    try:
        response = session.get(domain, headers=headers, timeout=25)
        if response.status_code == 200:
            all_matches = parse_html_robust(response.text, domain)
    except Exception as e:
        print(f"❌ Không thể tải nội dung từ {domain}: {e}")
        
    # Tạo file xuất danh sách kênh IPTV
    if all_matches:
        print(f"\n🎉 Hoàn thành! Quét được {len(all_matches)} trận đấu có luồng.")
        m3u_content = "#EXTM3U\n"
        m3u_content += f"# Generated: {get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)\n\n"
        
        for m in all_matches:
            for idx, stream in enumerate(m['streams'], 1):
                m3u_content += f'#EXTINF:-1 group-title="Xôi Lạc TV",{m["title"]} - Luồng {idx}\n'
                m3u_content += '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n'
                m3u_content += f'{stream}\n\n'
                
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print(f"💾 File danh sách đã được cập nhật thành công: {OUTPUT_FILE}")
    else:
        print("\n❌ Thất bại: Không lấy được luồng phát sóng nào công khai.")

if __name__ == "__main__":
    main()
