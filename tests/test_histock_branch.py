from openmarket.sources.histock_branch import parse_branches

# made-up page in HiStock's shape (the real page is not kept in the repo)
PAGE = """<html><body><table><tr><th>券商名稱</th><th>買張</th><th>賣張</th><th>賣超</th><th>均價</th>
<th>券商名稱</th><th>買張</th><th>賣張</th><th>買超</th><th>均價</th></tr>
<tr><td>永豐金-信義</td><td>6</td><td>218</td><td>-211</td><td>1155.09</td><td>凱基</td><td>506</td><td>40</td><td>466</td><td>1164.19</td></tr>
<tr><td>元大</td><td>788</td><td>956</td><td>-168</td><td>1,162.58</td><td>國泰</td><td>287</td><td>22</td><td>265</td><td>1168.78</td></tr>
</table></body></html>"""


def test_parse_branches():
    r = parse_branches(PAGE)
    assert [(x.name, x.net) for x in r["buy"]] == [("凱基", 466), ("國泰", 265)]
    assert [(x.name, x.net, x.avg) for x in r["sell"]] == [("永豐金-信義", -211, 1155.09), ("元大", -168, 1162.58)]
