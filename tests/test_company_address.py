import asyncio

import httpx
import pytest

from openmarket.sources.company_address import OVERSEAS, county_from_zip, county_of, fetch_county_groups, group_by_county


@pytest.mark.parametrize(
    ("address", "county"),
    [
        ("(104)台北市中山區松江路111號12樓", "臺北市"),
        ("台北巿大安區忠孝東路四段219號12樓", "臺北市"),
        ("(221)新北市汐止區新台五路一段98號19樓", "新北市"),
        ("新竹科學園區新竹縣寶山鄉創新一路十一號", "新竹縣"),
        ("新竹科學園區苗栗縣竹南鎮科中路15號", "苗栗縣"),
        ("新竹科學園區力行六路8號", "新竹市"),
        ("南部科學園區台南市善化區南科八路一號", "臺南市"),
        ("中部科學園區臺中市大雅區科雅路11號", "臺中市"),
        ("彰化市中山路3段359號", "彰化縣"),
        ("板橋區民生路一段一號", "新北市"),
        ("北市後港街六十六號", "臺北市"),
        ("2F.,No.30,Sec. 1,Heping W.Rd.,Zhongzheng Dist.,Taipei City 100028TAIPEI,TAIWAN(R.O.C)", "臺北市"),
        ("No.31,Wuquan 5th Rd.,Wugu Dist.,New Taipei City,Taiwan,R.O.C.", "新北市"),
        ("3rd Floor, No. 610, Dayuan DistrictTaoyuan City, Taiwan, R.O.C.", "桃園市"),
        ("9F.NO.186 Jian Yi  Road Chung Ho CityTaipei,Taiwan", "新北市"),
        ("5F, No.5, Innovation Road I, Science-Based Industrial ParkHsin-Chu, Taiwan, R.O.C.", "新竹市"),
        ("NO 176-5, LU LIAO KEN, CHIUNG LIN, HSIN-CHIU HSIEN,  TAIWAN,", "新竹縣"),
        ("21 Chenggong 2nd St. Minxiong Township,Chia Yi County, Taiwan", "嘉義縣"),
        ("17 PEI-YUAN ROADCHUNG-LI INDUSTRIAL PARK, TAIWAN, R.O.C.", "桃園市"),
        ("Windward 3,Regatta Office Park,PO Box 1350,Grand Cayman KY1", OVERSEAS),
        ("廣東省東莞市厚街鎮橋頭第三工業區", OVERSEAS),
        ("(52861)芳苑鄉後寮村工區路28號", "彰化縣"),
        ("No. 12345 Some Road", None),
        ("\u3000\u3000", None),
    ],
)
def test_county_of(address, county):
    assert county_of(address) == county


def test_zip_ranges():
    assert county_from_zip(300) == "新竹市" and county_from_zip(302) == "新竹縣" and county_from_zip(299) is None


def test_fetch_groups_both_markets():
    twse = [{"公司代號": "2330", "住址": "新竹科學園區力行六路8號"}] * 1 + [{"公司代號": str(1000 + i), "住址": "台北市"} for i in range(800)]
    tpex = [{"SecuritiesCompanyCode": str(5000 + i), "Address": "Kaohsiung City"} for i in range(800)]

    def handler(request):
        return httpx.Response(200, json=twse if "twse" in request.url.host else tpex)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_county_groups(client)

    groups = asyncio.run(run())
    assert groups["新竹市"] == ["2330"] and len(groups["臺北市"]) == 800 and len(groups["高雄市"]) == 800
    assert group_by_county([("1", "??")]) == {}


def test_fetch_groups_rejects_truncated_api():
    def handler(request):
        return httpx.Response(200, json=[{"公司代號": "1101", "住址": "台北市"}])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_county_groups(client)

    with pytest.raises(ValueError):
        asyncio.run(run())


def test_map_file_has_exactly_the_22_counties():
    import json
    from pathlib import Path

    from openmarket.sources.company_address import COUNTIES

    geo = json.loads((Path(__file__).parent.parent / "static" / "geo" / "tw-counties.geo.json").read_text(encoding="utf-8"))
    names = sorted(f["properties"]["name"] for f in geo["features"])
    assert len(names) == 22 and sorted(COUNTIES) == names
