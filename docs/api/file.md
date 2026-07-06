# TouchFish V5 Api 文档（文件存储相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

TFV5 的文件存储系统基于哈希去重和用户配额管理。同一文件可被多个用户上传，但分别计入各自的存储额度。

## 概念说明

- 哈希：上传时对文件内容计算 SHA256，相同内容的文件共享同一物理存储。
- 引用计数 (`ref_count`)：文件被引用次数（论坛帖子、聊天消息等场景中的引用）。
- 上传用户计数 (`upload_user_count`)：拥有该文件的用户数。降为 0 时文件立即从服务器移除。
- 存储配额 (`user_storage_quota`)：每个用户的存储空间上限，单位为字节。`-1` 表示不限。

## 公开 API

- `GET /file/get_file/<hashes>` 下载文件。

无需加密，直接访问。文件不存在或已被清理时返回 404。

- `GET /file/get_file_info/<hashes>` 获取文件基本信息。

无需加密。返回体：

```json
{
    "sender" : <sender_uid>,
    "file_name" : <file_name>,
    "send_time" : <send_time>,
    "hash" : <hash>,
    "ref_count" : <ref_count>,
    "last_ref_time" : <last_ref_time>,
    "size" : <size>,
    "upload_user_count" : <upload_user_count>
}
```

## Secret API

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

### 上传文件

- `^ POST /file/upload_file` 上传文件。

请求体：

```json
{
    "filename" : <filename>,
    "file_b64" : <file_b64>
}
```

其中 `<filename>` 是文件名，`<file_b64>` 是文件内容的 Base64 编码。

返回：若成功，返回文件哈希及下载地址：

```json
{
    "success" : true,
    "result" : "<timestamp>True",
    "hash" : <hash>,
    "download_url" : "/file/get_file/<hash>",
    "info_url" : "/file/get_file_info/<hash>"
}
```

上传前会检查：
- 用户是否被 ban
- 文件大小是否超过 `max_file_size` 限制
- 文件名和扩展名是否合法
- 用户存储配额是否足够（若文件内容已存在且用户已有该文件则不重复计费）

### 查看用户文件

- `^ POST /file/get_user_files` 查看当前用户的所有已上传文件（仍存在的）。

请求体：无（仅需 `uid` 和 `password`）。

返回体：

```json
[
    {
        "hash" : <hash>,
        "file_name" : <file_name>,
        "upload_time" : <upload_time>,
        "size" : <size>,
        "ref_count" : <ref_count>,
        "upload_user_count" : <upload_user_count>
    }
]
```

### 查看存储信息

- `^ POST /file/get_storage_info` 查看当前用户的存储使用情况。

请求体：无（仅需 `uid` 和 `password`）。

返回体：

```json
{
    "quota" : <quota>,
    "used" : <used>,
    "remaining" : <remaining>
}
```

其中 `<quota>` 为配置的用户存储配额（-1 表示不限），`<used>` 为已用字节数，`<remaining>` 为剩余可用字节数。

### 删除用户文件

- `^ POST /file/delete_file` 从当前用户的存储中删除文件。

请求体：

```json
{
    "hash" : <hash>
}
```

返回：成功返回时间戳加 `True`。

删除行为：
- 将用户与该文件的关联标记为无效（不再计入存储额度）
- 减少该文件的 `upload_user_count`
- 若 `upload_user_count` 降为 0，文件立即从服务器磁盘移除

### 减少引用

- `^ POST /file/dereference_file` 减少文件引用计数。

请求体：

```json
{
    "hash" : <hash>
}
```

返回：成功返回时间戳加 `True`。

## 管理员 API

> 以下接口仅 admin 或 root 用户可访问。

### 查看所有用户文件

- `^ POST /file/admin_get_all_files` 查看所有用户的已上传文件（或指定用户的文件）。

请求体：

```json
{
    "uid" : <operator_uid>,
    "password" : <operator_password>,
    "target_uid" : <optional, 不填则查询所有用户>
}
```

返回体：

```json
[
    {
        "uid" : <file_owner_uid>,
        "username" : <file_owner_username>,
        "hash" : <hash>,
        "file_name" : <file_name>,
        "upload_time" : <upload_time>,
        "size" : <size>,
        "ref_count" : <ref_count>,
        "upload_user_count" : <upload_user_count>,
        "sender" : <original_sender_uid>
    }
]
```

### 强行删除文件

- `^ POST /file/admin_force_delete_file` 强行删除文件，忽略引用计数和上传用户计数。

请求体：

```json
{
    "uid" : <operator_uid>,
    "password" : <operator_password>,
    "hash" : <hash>
}
```

返回：成功返回时间戳加 `True`。

删除行为：
- 立即从服务器磁盘删除文件
- 删除数据库中的文件记录
- 删除所有用户与该文件的关联记录（`user_file` 表）
- **不检查引用计数**，即使文件仍被帖子或消息引用也会被删除

## 管理员配置

管理员可通过 `^ POST /auth/server_settings/update` 配置存储相关参数：

- `max_file_size`：单个文件最大上传大小（字节），`-1` 不限。
- `user_storage_quota`：每个用户的存储配额（字节），`-1` 不限。新增于 TFV5。

此外 `file_last_time` 控制引用计数为 0 且超时的文件自动清理（单位：小时）。

## 自动清理机制

两种情况下文件会被清理：

1. **上传用户数为 0**：当文件不再被任何用户拥有时，立即从服务器删除（即使引用计数仍大于 0）。
2. **引用计数为 0 且超时**：当文件无引用且超过 `file_last_time` 小时，从服务器删除，并将其关联的用户文件标记为无效。
