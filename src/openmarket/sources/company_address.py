"""Head-office county (縣市) per listed company, from the official basic-information OpenAPIs.

- TWSE https://openapi.twse.com.tw/v1/opendata/t187ap03_L — 公司代號, 住址 (Chinese, e.g.
  "(104)台北市中山區…", "新竹科學園區新竹縣寶山鄉…", sometimes only "新竹科學園區創新一路…").
- TPEx https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O — SecuritiesCompanyCode, Address
  (English only, e.g. "…,Nangang Dist.,Taipei City 115605,Taiwan").
Only the county is derived (no geocoding): county names first, then science-park names, then the
postal code. Foreign head offices (Cayman, China, Vietnam…) go to OVERSEAS.
"""

from __future__ import annotations

import re

import httpx

from .http import get_with_retry

TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
OVERSEAS = "海外"
MIN_COMPANIES = 1500  # ~1,100 listed + ~900 OTC; far fewer means an API change

COUNTIES = [
    "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", "基隆市", "新竹市", "嘉義市",
    "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣",
    "臺東縣", "澎湖縣", "金門縣", "連江縣",
]

# science / industrial parks written without a county
PARKS = [
    ("新竹科學", "新竹市"), ("竹科", "新竹市"), ("南部科學", "臺南市"), ("台南科學", "臺南市"),
    ("臺南科學", "臺南市"), ("南科", "臺南市"), ("中部科學", "臺中市"), ("中科", "臺中市"),
]

# Cities / districts written without their county (county seats, New Taipei districts, "北市")
LOCAL = [
    ("彰化市", "彰化縣"), ("員林市", "彰化縣"), ("南投市", "南投縣"), ("苗栗市", "苗栗縣"), ("頭份市", "苗栗縣"),
    ("竹北市", "新竹縣"), ("屏東市", "屏東縣"), ("宜蘭市", "宜蘭縣"), ("花蓮市", "花蓮縣"), ("臺東市", "臺東縣"),
    ("斗六市", "雲林縣"), ("太保市", "嘉義縣"), ("朴子市", "嘉義縣"), ("馬公市", "澎湖縣"),
    *((d + "區", "新北市") for d in ["板橋", "三重", "中和", "永和", "新莊", "新店", "土城", "蘆洲", "汐止", "樹林",
                                     "五股", "林口", "淡水", "鶯歌", "三峽", "泰山", "深坑", "八里", "瑞芳"]),
    ("北市", "臺北市"),
]

# English names, matched on the address lowercased with every non-letter removed (so "Hsin-Chu",
# "Tao Yuan" and "DistrictTaoyuan" all match). Order matters: New Taipei districts and "newtaipei"
# before "taipei", Hsinchu County towns before "hsinchu".
ENGLISH = [
    *((k, "新北市") for k in ["newtaipei", "newtaipi", "banqiao", "panchiao", "sanchong", "sanchung", "zhonghe",
                              "chungho", "yonghe", "yungho", "xinzhuang", "hsinchuang", "tucheng", "shulin",
                              "xizhi", "sijhih", "hsichih", "xindian", "hsintien", "wugu", "linkou", "luzhou",
                              "tamsui", "danshui", "yingge", "sanxia", "taishan", "shenkeng"]),
    ("taipei", "臺北市"), ("taoyuan", "桃園市"), ("zhongli", "桃園市"), ("chungli", "桃園市"), ("jhongli", "桃園市"), ("taichung", "臺中市"), ("tainan", "臺南市"), ("liouying", "臺南市"), ("liuying", "臺南市"),
    ("kaohsiung", "高雄市"), ("koahsiung", "高雄市"), ("kaoshsiung", "高雄市"), ("keelung", "基隆市"),
    ("chiayicounty", "嘉義縣"), ("chiayihsien", "嘉義縣"), ("minxiong", "嘉義縣"), ("chiayi", "嘉義市"),
    *((k, "新竹縣") for k in ["hsinchucounty", "hsinchuhsien", "hsinchiuhsien", "zhubei", "jhubei", "chupei",
                              "hukou", "baoshan", "paoshan", "zhudong", "jhudong", "chutung", "xinpu", "hsinpu",
                              "chiunglin", "qionglin"]),
    ("hsinchu", "新竹市"), ("miaoli", "苗栗縣"), ("zhunan", "苗栗縣"), ("jhunan", "苗栗縣"), ("chunan", "苗栗縣"),
    ("changhua", "彰化縣"), ("lugang", "彰化縣"), ("nantou", "南投縣"), ("yunlin", "雲林縣"), ("douliu", "雲林縣"),
    ("douleu", "雲林縣"), ("pingtung", "屏東縣"), ("yilan", "宜蘭縣"), ("ilan", "宜蘭縣"), ("hualien", "花蓮縣"),
    ("taitung", "臺東縣"), ("penghu", "澎湖縣"), ("kinmen", "金門縣"), ("lienchiang", "連江縣"), ("matsu", "連江縣"),
]

FOREIGN = ["grand pavilion", "rayong", "cayman", "british virgin", "bermuda", "samoa", "hong kong", "china", "singapore", "malaysia",
           "vietnam", "thailand", "japan", "korea", "u.s.a", "usa", "united states", "philippines", "indonesia",
           "中國", "香港", "越南", "泰國", "日本", "馬來西亞", "新加坡", "開曼", "美國", "菲律賓", "印尼", "省", "P.O. Box"]

# 3-digit postal prefixes → county (Chunghwa Post ranges)
_ZIP = [
    (100, 116, "臺北市"), (200, 206, "基隆市"), (207, 208, "新北市"), (209, 212, "連江縣"),
    (220, 253, "新北市"), (260, 272, "宜蘭縣"), (300, 300, "新竹市"), (302, 315, "新竹縣"),
    (320, 338, "桃園市"), (350, 369, "苗栗縣"), (400, 439, "臺中市"), (500, 530, "彰化縣"),
    (540, 558, "南投縣"), (600, 600, "嘉義市"), (602, 625, "嘉義縣"), (630, 655, "雲林縣"),
    (700, 745, "臺南市"), (800, 852, "高雄市"), (880, 885, "澎湖縣"), (890, 896, "金門縣"),
    (900, 947, "屏東縣"), (950, 966, "臺東縣"), (970, 983, "花蓮縣"),
]


def county_from_zip(prefix: int) -> str | None:
    for lo, hi, county in _ZIP:
        if lo <= prefix <= hi:
            return county
    return None


def county_of(address: str) -> str | None:
    """County for a Chinese or English address; OVERSEAS for foreign ones; None if unknown."""
    if not address or not address.strip():
        return None
    text = address.replace("台", "臺").replace("巿", "市").strip()
    best = None
    for county in COUNTIES:
        i = text.find(county)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, county)
    if best:
        return best[1]
    for key, county in PARKS + LOCAL:
        if key in text:
            return county
    lower = address.lower()
    letters = re.sub(r"[^a-z]", "", lower)
    if letters and not any(k.lower() in lower for k in FOREIGN):
        for key, county in ENGLISH:
            if key in letters:
                return county
    if any(k.lower() in lower for k in FOREIGN):
        return OVERSEAS
    m = re.match(r"^\s*\(?\s*(\d{3})\d{0,3}\s*\)?", address) or re.search(r"\b(\d{3})\d{2,3}\b", address)
    if m:
        return county_from_zip(int(m.group(1)))
    return None


def group_by_county(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    """[(code, address)] → {county: [codes]} (unknown addresses are left out)."""
    out: dict[str, list[str]] = {}
    for code, address in rows:
        county = county_of(address)
        if county:
            out.setdefault(county, []).append(code)
    return out


async def fetch_county_groups(client: httpx.AsyncClient, progress=lambda done, total: None) -> dict[str, list[str]]:
    progress(0, 2)
    twse = (await get_with_retry(client, TWSE_URL)).json()
    progress(1, 2)
    tpex = (await get_with_retry(client, TPEX_URL)).json()
    progress(2, 2)
    rows = [(str(r.get("公司代號", "")).strip(), str(r.get("住址", ""))) for r in twse]
    rows += [(str(r.get("SecuritiesCompanyCode", "")).strip(), str(r.get("Address", ""))) for r in tpex]
    rows = [(c, a) for c, a in rows if c]
    if len(rows) < MIN_COMPANIES:
        raise ValueError(f"company basic-information APIs returned only {len(rows)} companies")
    return group_by_county(rows)


async def fetch_company_names(client: httpx.AsyncClient) -> dict[str, str]:
    """{code: 公司全名} from the same two basic-information APIs (for matching 轉投資 names)."""
    twse = (await get_with_retry(client, TWSE_URL)).json()
    tpex = (await get_with_retry(client, TPEX_URL)).json()
    out = {str(r.get("公司代號", "")).strip(): str(r.get("公司名稱", "")).strip() for r in twse}
    out.update({str(r.get("SecuritiesCompanyCode", "")).strip(): str(r.get("CompanyName", "")).strip() for r in tpex})
    return {k: v for k, v in out.items() if k and v}
