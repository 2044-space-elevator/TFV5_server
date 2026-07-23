# TouchFish V5 Api 文档（消息与聊天相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

TFV5 的消息系统由两部分组成：

1. **REST API**：发送消息、查询聊天列表、拉取历史消息。
2. **WebSocket 实时推送**：发送和接收即时消息、输入状态提示。

消息在服务端持久化存储，通过 `mid`（消息ID）唯一标识。客户端可通过 `client_mid` 实现去重和发送确认。

---

## 数据结构

### 消息对象

```json
{
    "mid" : <mid>,
    "client_mid" : <client_mid>,
    "sender_uid" : <sender_uid>,
    "receiver_uid" : <receiver_uid>,
    "group_id" : <group_id>,
    "content" : <content>,
    "content_type" : "plain" | "file",
    "file_hash" : <file_hash>,
    "send_time" : <send_time>,
    "quote" : <quote_mid>,
    "deleted" : 0 | 1,
    "mentioned_uids" : [<uid>, ...]
}
```

- `<mid>`：服务端分配的消息唯一ID，自增。
- `<client_mid>`：客户端生成的去重标识（可选）。同一 `client_mid` 的消息不会重复存储。
- `<content_type>`：`"plain"` 表示文本消息，`"file"` 表示文件消息。
- `<file_hash>`：文件消息的取件码（参见[文件文档](file.md)）。
- `<quote>`：引用的消息 `mid`，`-1` 表示不引用。
- `<mentioned_uids>`：消息正文中通过 `@用户名` 提及的用户 uid 列表。仅在 `content_type` 为 `"plain"` 时有值。
- `<room_id>`：聊天室标识，格式为 `"U<uid>"` 或 `"G<gid>"`。

### 聊天室对象

```json
{
    "room_id" : <room_id>,
    "room_type" : "direct" | "group",
    "partner_uid" : <partner_uid>,
    "username" : <username>,
    "avatar" : <avatar_url>,
    "last_content" : <last_content>,
    "last_content_type" : <content_type>,
    "last_time" : <last_time>,
    "last_sender_uid" : <last_sender_uid>,
    "last_mid" : <last_mid>,
    "is_friend" : <true_or_false>,
    "is_pinned" : <true_or_false>,
    "notify_level" : <0_or_1_or_2>
}
```

- `is_friend`：`room_type = "direct"` 时表示当前是否仍为好友关系。
- `is_pinned`：当前用户是否将此聊天室置顶。
- `notify_level`：当前用户对此聊天室的通知级别。`0` = 全部通知，`1` = 仅 @提及，`2` = 静音。首次访问或未设置时返回 `null`。

---

### @提及候选用户

- `^ POST /auth/mention_candidates` 获取当前服务器上可以被 @提及的用户列表。

请求体：

```json
{

}
```

返回体：

```json
[
    {
        "uid" : <uid>,
        "username" : <username>
    }
]
```

过滤掉当前用户及被封禁用户。结果按 `username` 升序排列。

---

### 聊天室偏好设置

- `^ POST /chat/preferences/update` 更新当前用户对指定聊天室的偏好（置顶、通知级别）。

请求体：

```json
{
    "room_id" : <room_id>,
    "is_pinned" : <true_or_false>,
    "notify_level" : <0_or_1_or_2>
}
```

其中：
- `<room_id>`（必填）聊天室标识，格式为 `"U<uid>"`（私聊）或 `"G<gid>"`（群聊）。
- `<is_pinned>`（可选，布尔类型）是否置顶该聊天室。
- `<notify_level>`（可选，整数类型）通知级别：`0` = 全部通知，`1` = 仅 @提及，`2` = 静音。

以上字段至少传入一个，只更新传入的字段。

权限约束：操作者必须与目标私聊用户为好友关系，或为目标群的成员。

返回：成功返回时间戳加 `True`，否则返回时间戳加 `False`。

---

## Secret API（REST）

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

### 发送消息（统一接口）

- `^ POST /message/send` 发送文本或文件消息。

*提示：在有 WebSocket 连接时，推荐优先使用 WebSocket 发送消息。*

请求体：

```json
{
    "recipient" : <recipient>,
    "content" : <content>,
    "content_type" : <content_type>,
    "client_mid" : <client_mid>,
    "quote" : <quote_mid>,
    "file_hash" : <file_hash>
}
```

其中：
- `<recipient>`（必填）是接收方，格式为 `"U<uid>"`（私聊）或 `"G<gid>"`（群聊）。
- `<content>`（必填）是消息正文。文本消息传文本内容，文件消息传文件哈希。
- `<content_type>`（可选，默认 `"plain"`）消息类型：`"plain"` 或 `"file"`。
- `<client_mid>`（可选）客户端去重标识。重复提交相同 `client_mid` 不会创建新消息，直接返回已有 `mid`。
- `<quote>`（可选，默认 `-1`）引用的消息 `mid`。
- `<file_hash>`（可选，`content_type = "file"` 时必填）文件的取件码。

校验：
- 操作者必须与接收方为好友关系（私聊），或为该群成员（群聊）。
- `content_type` 仅允许为 `"plain"` 或 `"file"`，否则请求将被拒绝。
- 文本消息长度不得超过 `max_message_length` 配置（默认 10000 字符）。
- 当 `content_type = "file"` 时，`file_hash` 必须为 64 位十六进制字符串（SHA-256 格式），否则请求将被拒绝。

返回：成功返回 `{"mid": <mid>, "client_mid": <client_mid>, "status": "sent"}`。重复提交也返回此格式（`mid` 为已有消息ID）。失败返回时间戳加 `False`。


### 聊天列表

- `^ POST /chat/list` 获取当前用户的全部聊天室列表（含最后一条消息）。

请求体：

```json
{

}
```

返回体：

```json
[
    {
        "room_id" : "U<uid>" | "G<gid>",
        "room_type" : "direct" | "group",
        "partner_uid" : <uid>,
        "username" : <username>,
        "avatar" : <avatar_url>,
        "last_content" : <last_content>,
        "last_content_type" : "plain" | "file",
        "last_time" : <last_time>,
        "last_sender_uid" : <last_sender_uid>,
        "last_mid" : <last_mid>,
        "is_friend" : <true_or_false>
    }
]
```

说明：
- 包含所有私聊和群聊会话，按最后消息时间降序排列。
- 尚无消息的好友也会出现在列表中（`last_mid` 为 `null`）。
- `room_type = "direct"` 时 `is_friend` 表示当前是否仍为好友关系。

---

### 历史消息

- `^ POST /message/history` 拉取历史消息（分页）。

*注意：不应频繁调用历史消息接口获取消息，在有 WebSocket 连接时，推荐优先使用实时推送。*

请求体：

```json
{
    "target_uid" : <target_uid>,
    "group_id" : <group_id>,
    "before_mid" : <before_mid>,
    "limit" : <limit>
}
```

其中：
- `<target_uid>`（私聊时必填）对方用户 uid。
- `<group_id>`（群聊时必填）群 gid。
- `target_uid` 和 `group_id` 二选一，不可同时使用。
- `<before_mid>`（可选，默认 `0` 即从最新开始）翻页游标，传上次返回结果中最小的 `mid`。
- `<limit>`（可选，默认 `50`，上限 `200`）每次拉取条数。

返回体：

```json
[
    {
        "mid" : <mid>,
        "client_mid" : <client_mid>,
        "sender_uid" : <sender_uid>,
        "receiver_uid" : <receiver_uid>,
        "group_id" : <group_id>,
        "content" : <content>,
        "content_type" : "plain" | "file",
        "file_hash" : <file_hash>,
        "send_time" : <send_time>,
        "quote" : <quote_mid>,
        "deleted" : 0 | 1,
        "mentioned_uids" : [<uid>, ...]
    }
]
```

消息按 `mid` 降序排列（最新在前）。

---

## WebSocket 实时通讯

消息实时通讯使用服务器的 `port_tcp` 端口（参见[主文档](main.md)和[通知文档](notification.md)的"TCP WebSocket 实时推送"部分）。

连接建立和 AES 密钥协商流程与通知推送一致，此处不再赘述。以下仅说明消息相关的 WebSocket 协议。

### 通用约定

- 所有 WebSocket 消息（除心跳外）均经过 AES 加密，封装格式同 [secret 类型 API](main.md#对于-secret-类型)。
- 每条消息可携带 `client_mid`（客户端生成的唯一标识），用于去重和发送确认。
- 服务端对每个用户默认实施 **每秒 10 条**消息的限流。超出限制时返回 `message.ack` 带 `"rate_limited"` 错误。

---

### 心跳

客户端可发送 PING 以保持连接活跃：

请求（secret 加密后）：

```json
{
    "type" : "PING"
}
```

响应（secret 加密后）：

```json
{
    "type" : "PONG"
}
```

心跳消息不计入频率限制。

---

### 发送文本消息（WebSocket）

请求（secret 加密后）：

```json
{
    "type" : "message.plain",
    "client_mid" : <client_mid>,
    "content" : {
        "send_to" : <send_to>,
        "plain" : <plain>,
        "quote" : <quote_mid>
    }
}
```

其中：
- `<send_to>`（必填）是字符串。私聊为 `"U<uid>"`，群聊为 `"G<gid>"`。
- `<plain>`（必填）是消息文本。
- `<quote>`（必填，不引用时传 `-1`）引用的消息 `mid`。
- `<client_mid>`（可选）客户端去重标识。

---

### 发送文件消息（WebSocket）

请求（secret 加密后）：

```json
{
    "type" : "message.file",
    "client_mid" : <client_mid>,
    "content" : {
        "send_to" : <send_to>,
        "file_hashes" : <file_hashes>,
        "quote" : <quote_mid>
    }
}
```

其中 `<file_hashes>` 是文件取件码（参见[文件文档](file.md)）。

---

### 发送确认（ACK）

服务端收到消息后，会立即返回 ACK 确认包：

```json
{
    "type" : "message.ack",
    "client_mid" : <client_mid>,
    "mid" : <mid>,
    "status" : "sent"
}
```

若消息被拒绝，`status` 为 `"failed"`，同时包含 `error` 字段说明原因：

```json
{
    "type" : "message.ack",
    "client_mid" : <client_mid>,
    "status" : "failed",
    "error" : "not_friends" | "not_group_member" | "rate_limited" | "message_too_long" | "invalid_quote" | "invalid_target" | "group_not_found" | "banned"
}
```

错误类型：
- `not_friends` — 对方不是好友
- `not_group_member` — 发送者不在该群中
- `rate_limited` — 超过频率限制（10 条/秒）
- `message_too_long` — 文本超过 `max_message_length`
- `invalid_quote` — 引用消息 ID 非法
- `invalid_target` — 接收方格式非法
- `group_not_found` — 群不存在
- `banned` — 账号已被封禁

---

### 接收消息推送

消息发送成功后，服务端会向接收方（及发送方本人，私聊时）推送消息通知。推送格式封装在 `NOTIFICATION.NEW` 中（参见[通知文档](notification.md)），`info` 中携带额外字段：

**文本消息**：

```json
{
    "event" : "message.plain",
    "title" : "<send_time>",
    "content" : <plain>,
    "sender" : "<sender_id>",
    "meta" : <quote_mid>,
    "mid" : <mid>,
    "client_mid" : <client_mid>,
    "room_id" : "<room_id>",
    "group_id" : <group_id>,
    "mentioned_uids" : [<uid>, ...],
    "mentions_me" : <true_or_false>,
    "should_alert" : <true_or_false>
}
```

**文件消息**：

```json
{
    "event" : "message.file",
    "title" : "<send_time>",
    "content" : <file_hashes>,
    "sender" : "<sender_id>",
    "meta" : <quote_mid>,
    "mid" : <mid>,
    "file_hash" : <file_hashes>,
    "client_mid" : <client_mid>,
    "room_id" : "<room_id>",
    "group_id" : <group_id>,
    "mentioned_uids" : [],
    "mentions_me" : false,
    "should_alert" : <true_or_false>
}
```

字段说明：
- `<mid>`：服务端消息ID。
- `<client_mid>`：客户端去重标识（与发送时一致）。
- `<room_id>`：聊天室标识。私聊时，接收方看到的 `room_id` 为发送者 uid（`"U<sender_uid>"`），发送方看到的为接收者 uid（`"U<target_uid>"`）。群聊时为 `"G<gid>"`。
- `<group_id>`：群聊时存在，为群 gid。私聊时无此字段。
- `<sender_id>`：私聊为 `"U<uid>"`，群聊为 `"G<gid>U<uid>"`。
- `<meta>`：引用的消息 `mid`。
- `<mentioned_uids>`：消息中被 @提及的用户 uid 列表。文件消息固定为空数组。
- `<mentions_me>`：当前接收用户是否在被提及列表中。发送方收到的推送中固定为 `false`。
- `<should_alert>`：客户端是否应触发通知提醒。由用户的聊天室偏好（`notify_level`）和被提及状态共同决定。发送方收到的推送中固定为 `false`。

### 输入状态

客户端可发送输入状态（"正在输入..."），服务端会广播给聊天室内其他在线成员：

请求（secret 加密后）：

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

广播（secret 加密后）：

```json
{
    "type" : "typing.start" | "typing.stop",
    "room_id" : "<room_id>",
    "uid" : <typer_uid>
}
```

群聊时不会广播给发送者本人。

---

## 服务端配置

消息相关配置项可通过 `^ POST /auth/server_settings/update` 设置：

- `max_message_length`：单条消息最大字符数，默认 `10000`，最小为 `1`。
- `min_group_name_length`：群名称最小字符数，默认 `1`，最小为 `1`。
- `max_group_name_length`：群名称最大字符数，默认 `50`，最小为 `1`。

## 注意事项

- 私聊消息仅好友之间可发送。非好友关系会收到 `not_friends` 错误。
- 群聊消息仅群成员可发送。非成员会收到 `not_group_member` 错误。
- 推荐客户端始终携带 `client_mid`，以便在网络重传时做到幂等去重。
