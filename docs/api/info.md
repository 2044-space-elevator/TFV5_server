# TouchFish V5 Api 文档（信息相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

- `* GET /info` 查询服务器信息

请求体：无

返回体；

```
{
    "captcha" : <is_captcha>,
    "email_activate" : <is_email_activate>,
    "file_last_time" : <file_last_time>,
    "groups_limit" : <groups_limit>,
    "port_api" : <port_api>,
    "port_tcp" : <port_tcp>,
    "server_name" : <servername>,
    "single_group_max_people" : <single_group_max_people>
}
```

Example:

```
{"captcha":false,"email_activate":false,"file_last_time":72,"groups_limit":30,"port_api":7001,"port_tcp":1145,"server_name":"TouchFish","single_group_max_people":200}
```