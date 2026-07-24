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

- `friend.request`
- `friend.accepted`
- `auth.stat.changed`
- `forum.approved`
- `forum.rejected`
- `forum.review.submitted`
- `forum.review.pending`
- `forum.comment.created`
- `forum.comment.mentioned`
- `forum.post.mentioned`
- `forum.post.deleted`
- `forum.comment.deleted`
- `announcement.created`
- `announcement.edited`
- `group.admin.added`
- `group.member.removed`
- `group.admin.removed`
- `group.deleted`
- `group.owner.transferred`
- `group.join.request`
- `group.invited`
- `group.invited.pending`
- `group.join.approved`
- `message.plain`
- `message.file`
- `message.recalled`

## Secret API

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

- `^ POST /notification/query_all` 查询当前用户的全部通知。

*注意：不应频繁调用通知接口实现通知收取，在有 WebSocket 连接时，推荐优先使用实时推送。*

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

*注意：不应频繁调用通知接口实现通知收取，在有 WebSocket 连接时，推荐优先使用实时推送。*

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

#### 接收文本消息

**在 `info` 中**，有：
```json
{
    "event" : "message.plain",
    "title" : "<send_time>",
    "content" : <content>,
    "sender" : "<sender_id>",
    "meta" : <quote_mid>,
    "mid" : <mid>,
    "client_mid" : <client_mid>,
    "room_id" : "<room_id>",
    "group_id" : <group_id>,
    "quote_preview" : <quote_preview_or_null>,
    "forwarded" : <forwarded_mid>,
    "forward_preview" : <forward_preview_or_null>,
    "mentioned_uids" : [<uid>, ...],
    "mentions_me" : <true_or_false>,
    "should_alert" : <true_or_false>
}
```

新增字段说明：
- `<mid>`：服务端分配的消息唯一 ID。
- `<client_mid>`：客户端发送时携带的去重标识（若发送时未携带则为 `null`）。
- `<room_id>`：聊天室标识。私聊时，接收方看到的 `room_id` 为发送者 uid（`"U<sender_uid>"`），发送方（自己也会收到推送）看到的为 `"U<target_uid>"`。群聊时为 `"G<gid>"`。
- `<group_id>`：仅群聊消息存在，为群 gid；私聊消息不包含该字段。
- `<forwarded>`：转发来源消息的 `mid`；非转发消息为 `-1`。
- `<forward_preview>`：转发来源消息摘要，结构与 `quote_preview` 相同；非转发消息为 `null`。
- `<mentioned_uids>`：消息中完整的、经服务端解析出的 @提及用户 uid 列表；发送方收到的副本也保留此列表。
- `<mentions_me>`：当前接收用户是否在被提及列表中。发送方收到的推送中固定为 `false`。
- `<should_alert>`：客户端是否应触发通知提醒。由用户的聊天室偏好（`notify_level`）和被提及状态共同决定。发送方收到的推送中固定为 `false`。

`<sender_id>` 的格式：
- 私聊：`"U<uid>"`，如 `"U0"`。
- 群聊：`"G<gid>U<uid>"`，如 `"G0U0"`。

其余字段含义见[消息文档](message.md)。

#### 接收文件消息

**在 `info` 中**，有：
```json
{
    "event" : "message.file",
    "title" : "<send_time>",
    "content" : <hashes>,
    "sender" : "<sender_id>",
    "meta" : <quote_mid>,
    "mid" : <mid>,
    "file_hash" : <hashes>,
    "client_mid" : <client_mid>,
    "room_id" : "<room_id>",
    "group_id" : <group_id>,
    "quote_preview" : <quote_preview_or_null>,
    "forwarded" : <forwarded_mid>,
    "forward_preview" : <forward_preview_or_null>,
    "file" : <file_metadata>,
    "mentioned_uids" : [],
    "mentions_me" : false,
    "should_alert" : <true_or_false>
}
```

格式说明同文本消息。`<hashes>` 是文件的取件码。`quote_preview` 是回复目标摘要，`forward_preview` 是转发来源摘要，`file` 是文件名、大小、MIME 类型、扩展名和下载地址等元数据。文件消息不支持 @提及，`mentioned_uids` 固定为空数组，`mentions_me` 固定为 `false`。

#### 消息撤回通知

撤回成功后，相关在线用户会收到：

```json
{
    "type" : "NOTIFICATION.NEW",
    "notification" : {
        "time_stamp" : <time_stamp>,
        "info" : {
            "event" : "message.recalled",
            "title" : "<deleted_at>",
            "content" : null,
            "sender" : <operator_uid>,
            "mid" : <mid>,
            "deleted" : true,
            "deleted_at" : <deleted_at>,
            "deleted_by" : <operator_uid>,
            "room_id" : <room_id>,
            "group_id" : <group_id_or_null>
        }
    }
}
```

通知不会包含被撤回的原始内容。撤回接口和权限规则见[消息文档](message.md#撤回消息)。

### 客户端发送消息

TFV5 在 WebSocket 中支持发送文本和文件消息，可带引用。

每条消息可携带 `client_mid`（客户端生成的唯一标识），该字段可选。仅当 `client_mid` 非 `null` 时，服务端才会返回 `message.ack` 确认包（成功时含服务端 `mid`），并利用 `client_mid` 对重传做去重；省略或传入 `null` 时仍可发送消息，但不会收到成功或失败 ACK。

服务端对每个用户实施每秒 10 条消息的限流。详情参见[消息文档](message.md)。

**文本消息**格式如下（封装格式参考 secret 类型）：

```json
{
    "type" : "message.plain",
    "client_mid" : "<client_mid>",
    "content" : {
        "send_to" : "<id>",
        "plain" : "<content>",
        "quote" : <mid>
    }
}
```

其中 `<id>` 是**字符串**：
- 发给用户：`"U<Uid>"`，例如 `"U0"`
- 发到群聊：`"G<Gid>"`

不引用时 `<mid>` 为 `-1`。

**文件消息**格式如下：

```json
{
    "type" : "message.file",
    "client_mid" : "<client_mid>",
    "content" : {
        "send_to" : "<id>",
        "file_hashes" : "<hashes>",
        "quote" : <mid>
    }
}
```

`<hashes>` 是文件取件码，由上传文件 API 返回。

### 发送确认（message.ack）

仅当发送请求中的 `client_mid` 非 `null` 时，服务端处理消息后返回 ACK：

```json
{
    "type" : "message.ack",
    "client_mid" : "<client_mid>",
    "mid" : <mid>,
    "status" : "sent"
}
```

若消息被拒绝：

```json
{
    "type" : "message.ack",
    "client_mid" : "<client_mid>",
    "status" : "failed",
    "error" : "<error_code>"
}
```

错误码包括：`not_friends`、`not_group_member`、`rate_limited`、`message_too_long`、`invalid_quote`、`invalid_target`、`invalid_file_hash`、`file_not_owned`、`client_mid_conflict`、`group_not_found`、`banned`。详见[消息文档](message.md)。

客户端必须保证 `send_to` 是非空的 `"U<uid>"` 或 `"G<gid>"`。缺少字段、空字符串或不可转换的编号属于畸形协议包，当前实现可能关闭连接而不返回 ACK。

### 输入状态（typing.start / typing.stop）

客户端发送输入状态，服务端广播给聊天室内其他在线成员（群聊时不广播给自己）：

请求：
```json
{
    "type" : "typing.start",
    "room_id" : "<room_id>"
}
```

```json
{
    "type" : "typing.stop",
    "room_id" : "<room_id>"
}
```

广播：
```json
{
    "type" : "typing.start",
    "room_id" : "<room_id>",
    "uid" : <typer_uid>
}
```

### 心跳（PING / PONG）

保持连接活跃：

请求：
```json
{
    "type" : "PING"
}
```

响应：
```json
{
    "type" : "PONG"
}
```

心跳不计入消息频率限制，但心跳仍然有频率限制。
