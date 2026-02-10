# TouchFish V5 Api 文档（信息相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

- `* GET /info/` 查询服务器信息

请求体：无

返回体；

```
{
    "captcha" : <is_captcha>,
    "email_activate" : <is_email_activate>,
    "port_api" : <port_api>,
    "port_tcp" : <port_tcp>,
    "server_name" : <servername>
}
```

Example:

```
{"captcha":false,"email_activate":false,"port_api":7001,"port_tcp":1145,"server_name":"TouchFish"}
```