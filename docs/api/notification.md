# TouchFish V5 Api 文档（通知相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

TFV5 的通知系统由两部分组成：

1. Secret API：查询和清理持久化通知。
2. TCP WebSocket：推送实时通知。

需要注意的是，WebSocket 只负责推送新通知，不会在登录后自动补发历史通知。客户端应先通过查询 API 拉取历史通知，再保持 TCP 连接接收后续推送。

## 通知数据结构

无论是查询 API 还是实时推送，单条通知都使用下面的结构：

```json
{
    "time_stamp" : <time_stamp>,
    "info" : {
        "event" : <event>,
        "title" : <title>,
        "content" : <content>,
        "sender" : <sender_uid>,
        "meta" : <meta>
    }
}
```

其中：

- `<time_stamp>` 是通知生成时间，为时间戳。
- `<event>` 是事件类型。
- `<title>` 是通知标题。
- `<content>` 是通知正文。
- `<sender_uid>` 是通知触发者 uid，没有触发者时也可能为空。
- `<meta>` 是附加信息，通常包含论坛、群聊、公告等上下文编号。

当前内置事件类型有：

- `auth.stat.changed`
- `forum.approved`
- `forum.rejected`
- `forum.comment.created`
- `forum.comment.mentioned`
- `announcement.created`
- `announcement.edited`
- `group.admin.added`
- `group.member.removed`
- `group.admin.removed`
- `group.deleted`
- `message.plain`
- `message.file`

## Secret API

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

- `^ POST /notification/query_all` 查询当前用户的全部通知。

请求体：

```json
{

}
```

返回体：

```json
[
    {
        "time_stamp" : <time_stamp>,
        "info" : {
            "event" : <event>,
            "title" : <title>,
            "content" : <content>,
            "sender" : <sender_uid>,
            "meta" : <meta>
        }
    }
]
```

- `^ POST /notification/query_after` 查询指定时间戳之后的通知。

请求体：

```json
{
    "time_stamp" : <time_stamp>
}
```

返回体同上，只不过只返回比 `<time_stamp>` 更新的通知。

- `^ POST /notification/delete_before` 删除某个时间戳及之前的所有通知。

请求体：

```json
{
    "time_stamp" : <time_stamp>
}
```

返回体：删除成功返回时间戳加 `True`，否则返回时间戳加 `False`。

- `^ POST /notification/delete_all` 删除当前用户的全部通知。

请求体：

```json
{

}
```

返回体：删除成功返回时间戳加 `True`，否则返回时间戳加 `False`。

## TCP WebSocket 实时推送

通知实时推送使用服务器的 `port_tcp` 端口，端口值可通过 `GET /info` 获取。

连接地址格式如下：

```text
ws://<server_host>:<port_tcp>
```

### 建立连接

建立连接后，请按如下顺序发送数据：

1. 明文发送 AES 密钥更新包：

```json
{
    "type" : "REQ.UPDATE_AES_KEY",
    "aes_key" : <rsa_encrypted_aes_key_base64>
}
```

2. 再发送一个 secret 类型的加密请求，请求体解密后应为：

```json
{
    "type" : "AUTH.LOGIN",
    "uid" : <uid>,
    "password" : <password>
}
```

如果登录成功，服务器会返回一个 secret 类型的加密响应，解密后内容如下：

```json
{
    "type" : "AUTH.LOGIN_SUCCEEDED"
}
```

### 接收实时通知

登录成功后，服务器会主动推送新的通知。推送包也是 secret 类型的加密响应，解密后格式如下：

```json
{
    "type" : "NOTIFICATION.NEW",
    "notification" : {
        "time_stamp" : <time_stamp>,
        "info" : {
            "event" : <event>,
            "title" : <title>,
            "content" : <content>,
            "sender" : <sender_uid>,
            "meta" : <meta>
        }
    }
}
```

客户端收到 `NOTIFICATION.NEW` 后，可以直接展示，也可以用其中的 `time_stamp` 配合 `query_after` 或 `delete_before` 做本地同步与清理。

#### 接受文本信息


**在 <info> 中**，有：
```json
{
    "event" : "message.plain",
    "title" : <this_mid>,
    "content" : <content>,
    "sender" : <uid>,
    "meta" : <quote_mid>
}
```

各参数含义请见“客户端发送的”。

**且，如果聊天对象是群聊，那么 `<uid>` 是：`G<Gid>U<Uid>`，比如群编号 0 以及用户编号也是 0，那么 `<uid> 即为 `G0U0`。如果聊天对象是用户，那么 `<uid> 是用户编号。**

#### 接受文件信息

**在 <info> 中**，有：
```json
{
    "event" : "message.file",
    "title" : <this_mid>,
    "content" : <hashes>,
    "sender" : <uid>,
    "meta" : <quote_mid>
}
```

各参数含义请见“客户端发送的”。

**且，如果聊天对象是群聊，那么 `<uid>` 是：`G<Gid>U<Uid>`，比如群编号 0 以及用户编号也是 0，那么 `<uid> 即为 `G0U0`。如果聊天对象是用户，那么 `<uid> 是用户编号。**

### 客户端发送的

需注意，发送信息时，如果发送成功那么服务器会再

鉴于大部分功能已经被 API 统一处理，为了加快线上沟通效率，TFV5 在 WebSocket 接口中允许客户端发送一对一通讯信息（即好友快速通讯和群聊快速通讯）。

允许发送文件和纯文本，可以带一个引用，引用的为 message id（message id 将在 notification 中被提供）。对于文本类型格式如下（封装格式参考 secret 类型）：

```json
{
    "type" : "message.plain",
    "content" : {
        "send_to" : <id>,
        "plain" : <content>,
        "quote" : <mid>
    }
}
```

其中 `<id>` 是**字符串**，对于该字符串：
- 如果是发给用户的，请注明 "U<Uid>"，<Uid> 是用户编码。（例如 "U0"）
- 如果是发到群聊的，请注明 "G<Gid>"，<Gid> 是群聊编码。

如果不引用，`<mid>` 为 -1。

文件格式如下：

```json
{
    "type" : "message.file",
    "content" : {
        "send_to" : <id>,
        "file_hashes" : <hashes>,
        "quote" : <mid>
    }
}
```

`<hashes>` 是文件的“取件码”，在上传文件的时候由 API 返回。

`<mid>`、`<id>` 的说明如上。
