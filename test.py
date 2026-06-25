import requests

proxy_host = "lite.flashproxy.io"
proxy_port = "6969"
proxy_user = "BHF6UsNS-country-US"
proxy_pass = "X8ABIdpI"

proxies = {
    "http": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
    "https": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
}

# 请求 ipinfo.io 获取地理位置和 IP 信息
url = "https://httpbin.org/get"

try:
    response = requests.get(url, proxies=proxies, timeout=12)
    if response.status_code == 200:
        print("[成功] 代理正常工作，出口 IP 信息如下：")
        print(response.text)
    else:
        print(f"[失败] 请求成功但状态码异常: {response.status_code}")
except requests.exceptions.RequestException as e:
    print(f"[错误] 代理连接失败: {e}")