import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

START_URL = "https://bunchatv.net/truc-tiep"
OUT_M3U = "buncha.txt"

TIMEOUT = 12
MAX_MATCHES = 80  # Đủ dùng, mày tăng/giảm tùy ý

# Bắt m3u8 (absolute URL) trong HTML/inline JS
M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]+)?', re.IGNORECASE)

def pick_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def extract_match_links(home_html: str) -> list[str]:
    # Dùng Regex bắt trực tiếp các href có chứa /truc-tiep/
    hrefs = re.findall(r'href=["\']([^"\']*?/truc-tiep/[^"\']*?)["\']', home_html)
    
    seen = set()
    out = []
    for href in hrefs:
        u = urljoin(START_URL, href)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def parse_match_info(match_html: str) -> dict:
    """
    Chỉ lấy đúng Giờ và Tên 2 đội để cho tên kênh thật ngắn gọn.
    """
    soup = BeautifulSoup(match_html, "lxml")
    text = soup.get_text("\n", strip=True)

    # Lấy giờ
    time_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    hhmm = time_m.group(1) if time_m else ""

    # Lấy tên đội từ thẻ tiêu đề
    headings = [pick_text(h) for h in soup.select("h1,h2,h3") if pick_text(h)]
    team_a = headings[0] if len(headings) >= 1 else ""
    team_b = headings[1] if len(headings) >= 2 else ""

    return {
        "time": hhmm.strip(),
        "team_a": team_a.strip(),
        "team_b": team_b.strip()
    }

def build_channel_name(info: dict) -> str:
    # Format chuẩn: [08:00] Matagalpa FC vs Real Esteli
    name = ""
    if info["time"]:
        name += f'[{info["time"]}] '
        
    if info["team_a"] and info["team_b"]:
        name += f'{info["team_a"]} vs {info["team_b"]}'
    elif info["team_a"]:
        name += info["team_a"]
    else:
        name += "Live" # Fallback nếu không tìm thấy tên đội
        
    return name.strip()

def main():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "IPTV-Match-Crawler/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    try:
        home = s.get(START_URL, timeout=TIMEOUT)
        home.raise_for_status()
    except Exception as e:
        print(f"Lỗi khi truy cập trang chủ: {e}")
        return

    match_links = extract_match_links(home.text)[:MAX_MATCHES]
    print(f"Tìm thấy số trang trận đấu: {len(match_links)}")

    items = []
    seen_m3u8 = set()

    for idx, match_url in enumerate(match_links, 1):
        try:
            r = s.get(match_url, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            html = r.text
        except Exception:
            continue

        info = parse_match_info(html)
        name = build_channel_name(info)

        m3u8s = list(dict.fromkeys(M3U8_RE.findall(html)))

        added_count = 0
        for u in m3u8s:
            if u not in seen_m3u8:
                seen_m3u8.add(u)
                items.append({
                    # Nếu có nhiều link trong 1 trận, từ link thứ 2 thêm (Link 2), (Link 3)...
                    "name": name if added_count == 0 else f"{name} (Link {added_count + 1})",
                    "url": u,
                    "group": "KayTee"
                })
                added_count += 1

        print(f"[{idx}/{len(match_links)}] {match_url} | Tìm thấy {len(m3u8s)} m3u8 | Đã thêm {added_count} link")

    # Xuất M3U
    lines = ["#EXTM3U"]
    for it in items:
        lines.append(f'#EXTINF:-1 group-title="{it["group"]}",{it["name"]}')
        lines.append(it["url"])

    with open(OUT_M3U, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nXONG -> {OUT_M3U} | Tổng số kênh thu được: {len(items)}")

if __name__ == "__main__":
    main()
