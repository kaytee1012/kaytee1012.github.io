import re
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

START_URL = "https://bunchatv.net/truc-tiep"

OUT_M3U = "buncha.txt"
OUT_JSON = "buncha.json"

TIMEOUT = 12
MAX_MATCHES = 80  # đủ dùng, mày tăng/giảm tùy

# Bắt m3u8 (absolute URL) trong HTML/inline JS
M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]+)?', re.IGNORECASE)

# Bắt giờ kiểu 09:30, 11:00
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")

def pick_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def stable_id(prefix: str, text: str, n: int = 10) -> str:
    h = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:n]
    return f"{prefix}-{h}"

def extract_match_links(home_html: str) -> list[str]:
    # Bắt trực tiếp các href chứa /truc-tiep/
    hrefs = re.findall(r'href=["\']([^"\']*?/truc-tiep/[^"\']*?)["\']', home_html)

    seen = set()
    out = []
    for href in hrefs:
        u = urljoin(START_URL, href)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_title_like(soup: BeautifulSoup) -> str:
    """
    Ưu tiên og:title -> title -> h1/h2/h3 đầu tiên
    """
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()

    t = soup.title.get_text(" ", strip=True) if soup.title else ""
    if t:
        return t.strip()

    for sel in ["h1", "h2", "h3"]:
        h = soup.select_one(sel)
        if h:
            tx = pick_text(h)
            if tx:
                return tx
    return ""

def split_teams_from_title(title: str) -> tuple[str, str]:
    """
    Cố gắng tách team A / team B từ title kiểu:
    - "A vs B"
    - "A - B"
    - "A v B"
    - "A VS B"
    """
    if not title:
        return "", ""

    t = re.sub(r"\s+", " ", title).strip()

    # Loại bớt phần thừa hay gặp
    t = re.sub(r"\s*\|\s*.*$", "", t)   # cắt sau dấu |
    t = re.sub(r"\s*-\s*(Trực tiếp|Live).*?$", "", t, flags=re.I)

    # Các dấu phân cách hay dùng
    seps = [r"\s+vs\s+", r"\s+VS\s+", r"\s+v\s+", r"\s+V\s+", r"\s+-\s+", r"\s+–\s+"]
    for sep in seps:
        parts = re.split(sep, t, maxsplit=1)
        if len(parts) == 2:
            a = parts[0].strip(" -–|")
            b = parts[1].strip(" -–|")
            # chặn trường hợp tách bậy quá ngắn
            if len(a) >= 2 and len(b) >= 2:
                return a, b

    return "", ""

def parse_match_info(match_html: str) -> dict:
    """
    Lấy giờ + team A/B từ title/og:title hoặc heading.
    """
    soup = BeautifulSoup(match_html, "lxml")
    full_text = soup.get_text("\n", strip=True)

    # giờ
    time_m = TIME_RE.search(full_text)
    hhmm = time_m.group(1) if time_m else ""

    title_like = extract_title_like(soup)
    team_a, team_b = split_teams_from_title(title_like)

    # fallback: thử tìm trong các heading nếu title_like không tách được
    if not team_a and not team_b:
        headings = [pick_text(h) for h in soup.select("h1,h2,h3") if pick_text(h)]
        for h in headings[:5]:
            a, b = split_teams_from_title(h)
            if a and b:
                team_a, team_b = a, b
                break

    return {
        "time": hhmm.strip(),
        "team_a": team_a.strip(),
        "team_b": team_b.strip(),
        "title_like": title_like.strip()
    }

def build_channel_name(info: dict) -> str:
    # Mày muốn ngắn gọn để UI hiện đẹp
    if info["team_a"] and info["team_b"]:
        return f'{info["team_a"]} vs {info["team_b"]}'.strip()
    if info["title_like"]:
        return info["title_like"]
    return "Live"

def build_labels(info: dict, group: str) -> list[dict]:
    labels = [
        {
            "position": "top-left",
            "text": "● Live",
            "color": "#FF0000",
            "text_color": "#FFFFFF"
        },
        {
            "position": "bottom-left",
            "text": group,
            "color": "#0066CC",
            "text_color": "#FFFFFF"
        }
    ]
    if info.get("time"):
        labels.append(
            {
                "position": "center",
                "text": info["time"],
                "color": "#4CAF50",
                "text_color": "#FFFFFF"
            }
        )
    return labels

def guess_request_headers(m3u8_url: str, match_url: str) -> list[dict]:
    """
    Một số CDN cần Referer. Nếu mày biết chắc referer nào thì set cứng ở đây.
    Default: dùng chính match_url làm Referer (an toàn hơn để chống 403).
    """
    return [{"key": "Referer", "value": match_url}]

def main():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "IPTV-Match-Crawler/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    # 1) Load home
    try:
        home = s.get(START_URL, timeout=TIMEOUT)
        home.raise_for_status()
    except Exception as e:
        print(f"Lỗi khi truy cập trang chủ: {e}")
        return

    match_links = extract_match_links(home.text)[:MAX_MATCHES]
    print(f"Tìm thấy số trang trận đấu: {len(match_links)}")

    # 2) Thu items (cho M3U) + channels (cho JSON)
    m3u_items = []
    channels = []
    seen_m3u8 = set()

    GROUP_NAME = "KayTee"

    for idx, match_url in enumerate(match_links, 1):
        try:
            r = s.get(match_url, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            html = r.text
        except Exception:
            continue

        info = parse_match_info(html)
        base_name = build_channel_name(info)

        # lấy tất cả m3u8 duy nhất theo thứ tự
        m3u8s = list(dict.fromkeys(M3U8_RE.findall(html)))

        added_count = 0
        for u in m3u8s:
            if u in seen_m3u8:
                continue
            seen_m3u8.add(u)

            # tên kênh: nếu nhiều link trong 1 trận, thêm (Link 2), (Link 3)...
            display_name = base_name if added_count == 0 else f"{base_name} (Link {added_count + 1})"

            # --- M3U item ---
            m3u_items.append({
                "name": (f'[{info["time"]}] {display_name}'.strip() if info.get("time") else display_name),
                "url": u,
                "group": GROUP_NAME
            })

            # --- JSON channel ---
            ch_id = stable_id("kaytee", match_url + "|" + u, 12)
            source_id = stable_id("src", ch_id, 10)
            content_id = stable_id("ct", ch_id, 10)
            stream_id = stable_id("st", ch_id, 10)
            link_id = stable_id("lnk", ch_id, 10)

            channels.append({
                "id": ch_id,
                "name": display_name,
                "labels": build_labels(info, GROUP_NAME),
                "description": info["time"] if info.get("time") else "",
                "image": {
                    # Không có poster trận => dùng logo buncha (đỡ trống)
                    "url": "https://kaytee1012.github.io/buncha_logo.png",
                    "height": 480,
                    "width": 640,
                    "display": "cover",
                    "shape": "square"
                },
                "type": "single",
                # QUAN TRỌNG: để hiện tên trận như mày muốn
                "display": "text-below",
                "sources": [
                    {
                        "id": source_id,
                        "name": "Bún chả TV",
                        "contents": [
                            {
                                "id": content_id,
                                "name": display_name,
                                "streams": [
                                    {
                                        "id": stream_id,
                                        "name": GROUP_NAME,
                                        "stream_links": [
                                            {
                                                "id": link_id,
                                                "name": "HLS",
                                                "type": "hls",
                                                "default": True,
                                                "url": u,
                                                "request_headers": guess_request_headers(u, match_url)
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            })

            added_count += 1

        print(f"[{idx}/{len(match_links)}] {match_url} | Tìm thấy {len(m3u8s)} m3u8 | Đã thêm {added_count} link")

    # 3) Xuất M3U
    m3u_lines = ["#EXTM3U"]
    for it in m3u_items:
        m3u_lines.append(f'#EXTINF:-1 group-title="{it["group"]}",{it["name"]}')
        m3u_lines.append(it["url"])

    with open(OUT_M3U, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(m3u_lines) + "\n")

    # 4) Build JSON đúng format buncha (bản tối giản: chỉ Live)
    buncha_json = {
        "id": "buncha",
        "url": "https://tt.8share.pro/buncha",
        "name": "Bún Chả TV",
        "color": "#1cb57a",
        "description": "Bún Chả TV - Trang web phát sóng bóng đá trực tuyến miễn phí hàng đầu tại Việt Nam, mang đến trải nghiệm chất lượng cao với bình luận tiếng Việt sống động.",
        "image": {
            "url": "https://kaytee1012.github.io/buncha_logo.png"
        },
        "groups": [
            {
                "id": "live",
                "name": "🔴 Live",
                "display": "horizontal",
                "grid_number": 2,
                "channels": channels
            }
        ],
        "option": {
            "save_history": False,
            "save_search_history": False,
            "save_wishlist": False
        }
    }

    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(buncha_json, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nXONG -> {OUT_M3U} | Tổng số kênh M3U: {len(m3u_items)}")
    print(f"XONG -> {OUT_JSON} | Tổng số channels JSON: {len(channels)}")

if __name__ == "__main__":
    main()
