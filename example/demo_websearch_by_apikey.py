import json
import requests

APIKEY = ""


def websearch_by_apikey(body: dict):
    # 请求URL
    url = 'https://open.feedcoopapi.com/search_api/web_search'

    # 请求头
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {APIKEY}'
    }

    try:
        # 发送 POST 请求
        response = requests.post(url, headers=headers, json=body)

        # 打印响应状态码
        print(f"Response Status Code: {response.status_code}")

        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf - 8')
                    if "invalid_request" in line_str:
                        return json.loads(response.text)
                    print(line_str)

    except Exception as e:
        print(f"Error occurred: {str(e)}")


if __name__ == "__main__":
    body = {
        "Query": "深圳今天天气",
        # "SearchType": "web",
        "SearchType": "web_summary",
        "Count": 1,
        "Filter": {
            "NeedContent": False,
            "NeedUrl": True
        },
        "NeedSummary": True
    }

    websearch_by_apikey(body=body)
