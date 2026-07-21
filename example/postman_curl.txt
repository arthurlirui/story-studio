curl --location 'https://open.feedcoopapi.com/search_api/web_search' \
--header 'Content-Type: application/json' \
--header 'Authorization: Bearer {此处填写APIKEY}' \
--data '{
    "Query": "深圳明天天气",
    "SearchType": "web",
    "Count": 10,
    "Filter": {
        "NeedContent": true,
        "NeedUrl": false,
        "Sites": "",
        "BlockHosts": "",
        "AuthInfoLevel": 0
    },
    "NeedSummary": true,
    "TimeRange": "",
    "QueryControl": {
        "QueryRewrite": false
    }
}'