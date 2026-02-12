import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

START_URL = "https://quechoa5.live/"
OUT_M3U = r"D:\kaytee1012.github.io\quechoa.txt"

TIMEOUT = 12
MAX_MATCHES = 80  # đủ dùng, mày tăng/giảm tùy

# Bắt m3u8 (absolute URL) trong HTML/inline JS
M3U8_RE = re.compile(r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]+)?', re.IGNORECASE)

# Dấu hiệu HLS trong nội dung playlist
HLS_HINT_RE = re.compile(r"#EXTM3U|#EXT-X-|#EXTINF:", re.IGNORECASE)
MAX_BYTES = 200_000

def is_live_m3u8(url: str, session: requests.Session) -> bool:
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        if r.status_code != 200:
            return False
        chunk = r.raw.read(MAX_BYTES).decode("utf-8", errors="ignore")
        low = chunk.lower()
        if "<html" in low or "<!doctype html" in low:
            return False
        return bool(HLS_HINT_RE.search(chunk))
    except Exception:
        return False

def pick_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def extract_match_links(home_html: str) -> list[str]:
    soup = BeautifulSoup(home_html, "lxml")
    links = []
    for a in soup.select('a[href]'):
        href = a.get("href", "").strip()
        if not href:
            continue
        # bắt các link trận
        if "/truc-tiep/" in href:
            links.append(urljoin(START_URL, href))
    # unique giữ thứ tự
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def parse_match_info(match_html: str) -> dict:
    """
    Parse metadata từ text hiển thị trên trang trận.
    Trên trang trận của quechoa5.live có: giải (LCP), giờ (06:00), ngày (12.02),
    team A, team B, BLV (GẤU NÂU), trạng thái Live/Sắp diễn ra.
    """
    soup = BeautifulSoup(match_html, "lxml")

    # Lấy text toàn trang để fallback regex
    text = soup.get_text("\n", strip=True)

    # Giờ + ngày: dạng 06:00 và 12.02
    time_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    date_m = re.search(r"\b(\d{1,2}\.\d{2})\b", text)
    hhmm = time_m.group(1) if time_m else ""
    ddmm = date_m.group(1) if date_m else ""

    # Trạng thái: Live hoặc Sắp diễn ra (trên trang trận có chữ Live) :contentReference[oaicite:2]{index=2}
    status = "Live" if re.search(r"\bLive\b", text) else ""

    # Team: thường là 2 heading gần nhau (### GAM..., ### Fukuoka...) :contentReference[oaicite:3]{index=3}
    # Lấy h3/h2/h1 theo thứ tự xuất hiện
    headings = [pick_text(h) for h in soup.select("h1,h2,h3") if pick_text(h)]
    team_a = headings[0] if len(headings) >= 1 else ""
    team_b = headings[1] if len(headings) >= 2 else ""

    # Giải: thường là token ngắn (LCP/LCK/AFC Cup...) nằm gần khu scoreboard
    # Trên trang trận GAM vs Fukuoka có "LCP" :contentReference[oaicite:4]{index=4}
    # Fallback: lấy token in hoa độ dài 2-5 trước giờ, hoặc lấy dòng đơn lẻ ngắn
    league = ""
    # thử tìm dòng đơn lẻ ngắn có chữ cái (ít ký tự)
    for line in text.split("\n"):
        t = line.strip()
        if 2 <= len(t) <= 20 and any(c.isalpha() for c in t):
            # né các chữ chung chung
            if t.lower() in {"chia sẻ", "mở rộng", "fhd hd sd"}:
                continue
            # ưu tiên token in hoa
            if re.fullmatch(r"[A-Z0-9]{2,6}", t):
                league = t
                break
    if not league:
        # fallback: tìm cụm kiểu "AFC Cup", "Champions League", "Pro League" từ trang chủ cũng có :contentReference[oaicite:5]{index=5}
        m = re.search(r"\b(AFC Cup|Champions League|Pro League|Premier League|LCK|LCP|Futsal World|Cup)\b", text, re.IGNORECASE)
        league = m.group(1) if m else ""

    # BLV: trên trang trận có tên “GẤU NÂU” hiển thị rõ :contentReference[oaicite:6]{index=6}
    blv = ""
    # tìm 1 đoạn toàn chữ cái/space, độ dài vừa phải, nằm sau khu team
    # (đơn giản: ưu tiên các tên in hoa có dấu)
    for line in text.split("\n"):
        t = line.strip()
        if 2 <= len(t) <= 30 and any(ch.isalpha() for ch in t):
            # né tên menu / chung chung
            if t.upper() in {"TRANG CHỦ", "LỊCH THI ĐẤU", "KẾT QUẢ", "XEM LẠI", "TUYỂN DỤNG"}:
                continue
            if t in {league, team_a, team_b, status, hhmm, ddmm}:
                continue
            # thường BLV là 1-3 từ, viết hoa
            if t == t.upper() and " " in t:
                blv = t
                break

    return {
        "league": league.strip(),
        "time": hhmm.strip(),
        "date": ddmm.strip(),
        "team_a": team_a.strip(),
        "team_b": team_b.strip(),
        "status": status.strip(),
        "blv": blv.strip(),
    }

def build_channel_name(info: dict) -> str:
    parts = []
    if info["status"]:
        parts.append(info["status"])
    if info["time"] or info["date"]:
        parts.append(f'[{info["time"]} {info["date"]}]'.strip())
    if info["team_a"] and info["team_b"]:
        parts.append(f'{info["team_a"]} vs {info["team_b"]}')
    elif info["team_a"]:
        parts.append(info["team_a"])
    if info["blv"]:
        parts.append(f'({info["blv"]})')
    return " ".join([p for p in parts if p]).strip() or "Live"

def main():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "IPTV-Match-Crawler/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    home = s.get(START_URL, timeout=TIMEOUT)
    home.raise_for_status()

    match_links = extract_match_links(home.text)[:MAX_MATCHES]
    print("Found match pages:", len(match_links))

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

        # m3u8 nằm trong HTML/inline JS của trang trận (mày nói có)
        m3u8s = list(dict.fromkeys(M3U8_RE.findall(html)))

        picked = ""
        for u in m3u8s:
            if u in seen_m3u8:
                continue
            if is_live_m3u8(u, s):
                picked = u
                break

        if picked:
            seen_m3u8.add(picked)
            items.append({
                "name": name,
                "url": picked,
                "group": info["league"],
            })

        print(f"[{idx}/{len(match_links)}] {match_url} | m3u8={len(m3u8s)} | added={'YES' if picked else 'NO'}")

    # Xuất M3U
    lines = ["#EXTM3U"]
    for it in items:
        attrs = []
        if it["group"]:
            attrs.append(f'group-title="{it["group"]}"')
        attr_str = (" " + " ".join(attrs)) if attrs else ""
        lines.append(f'#EXTINF:-1{attr_str},{it["name"]}')
        lines.append(it["url"])

    with open(OUT_M3U, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print("DONE ->", OUT_M3U, "| channels:", len(items))

if __name__ == "__main__":
    main()
