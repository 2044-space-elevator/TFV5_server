# TouchFish V5 Api 文档（群聊相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

TFV5 群聊系统支持创建群组、成员管理、管理员管理、入群审核、群主转让等功能。

## 角色层级

群聊中有三个角色层级（对应 `is_admin` 返回值）：

- 2（群主/owner）：群创建者或被转让的新群主。拥有全部权限。
- 1（管理员/admin）：由群主任命。可添加/移除成员、审核入群申请。
- 0（普通成员/member）：可发送消息、查看群信息。

权限规则：高角色可操作低角色。群主不可被移除或降级。管理员不可操作同级管理员。

## 入群机制

群聊支持两种入群方式（由创建者配置）：

1. **直接加入**（`allow_direct_join = true`，`require_review = false`）：用户可直接加入，无需审核。
2. **申请后审核**（`allow_direct_join = true`，`require_review = true`）：用户提交入群申请，管理员/群主审批后加入。
3. **仅邀请**（`allow_direct_join = false`）：用户无法主动加入，只能通过群成员邀请加入。

无论如何，群内成员也可以直接邀请好友；管理员/群主邀请时可绕过审核直接拉人。

## Secret API

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

### 创建群聊

- `^ POST /group/create_group` 创建群聊。

请求体：

```json
{
    "groupname" : <groupname>,
    "introduction" : <introduction>,
    "enter_hint" : <enter_hint>,
    "allow_direct_join" : <allow_direct_join>,
    "require_review" : <require_review>
}
```

其中：
- `<groupname>`（必填）是群名称。
- `<introduction>`（可选，默认 `""`）是群简介。
- `<enter_hint>`（可选，默认 `""`）是入群欢迎语，显示在聊天界面。
- `<allow_direct_join>`（可选，默认 `false`）是否允许用户直接申请入群。
- `<require_review>`（可选，默认 `true`）是否需要对入群申请进行审核。仅在 `allow_direct_join` 为 `true` 时有效。

返回：创建成功返回 `{"gid": <gid>}`，失败返回时间戳加 `False`。

创建者自动成为群主（owner）和第一个成员。群组数量受 `groups_limit` 服务器配置限制。

---

### 查询群信息

- `* GET /group/group_info/<gid>` 查看群基本信息。

请求体：无（public 接口）。

返回：一个数组，分别为 `[gid, creater, groupname, members, admins, enter_hint, introduction, allow_direct_join, require_review]`。若群不存在返回 `{}`。

---

### 搜索群聊

- `* GET /group/groupname_search/<groupname>` 按群名模糊搜索。

请求体：无（public 接口）。

返回：匹配的群聊列表，每项格式同上。

---

### 群设置（查看）

- `^ POST /group/settings` 查看群完整设置。

请求体：

```json
{
    "gid" : <gid>
}
```

需要操作者为该群管理员或群主（`is_admin >= 1`）。

返回体：

```json
{
    "gid" : <gid>,
    "creater" : <creater_uid>,
    "groupname" : <groupname>,
    "enter_hint" : <enter_hint>,
    "introduction" : <introduction>,
    "allow_direct_join" : <true_or_false>,
    "require_review" : <true_or_false>
}
```

---

### 群设置（更新）

- `^ POST /group/update_settings` 更新群设置。

请求体：

```json
{
    "gid" : <gid>,
    "groupname" : <new_groupname>,
    "enter_hint" : <new_enter_hint>,
    "introduction" : <new_introduction>,
    "allow_direct_join" : <true_or_false>,
    "require_review" : <true_or_false>
}
```

以上字段均为可选，只更新传入的字段。仅群主（`is_admin == 2`）可操作。

返回：更新成功返回时间戳加 `True`，失败返回时间戳加 `False`。

---

### 查看群成员

- `^ POST /group/members` 查看群成员列表及角色。

请求体：

```json
{
    "gid" : <gid>
}
```

需要操作者为该群成员。

返回体：

```json
{
    "members" : [
        {
            "uid" : <uid>,
            "username" : <username>,
            "role" : "owner" | "admin" | "member"
        }
    ],
    "settings" : {
        "gid" : <gid>,
        "creater" : <creater_uid>,
        "groupname" : <groupname>,
        "enter_hint" : <enter_hint>,
        "introduction" : <introduction>,
        "allow_direct_join" : <true_or_false>,
        "require_review" : <true_or_false>
    }
}
```

---

### 入群申请

- `^ POST /group/join` 申请加入群聊。

请求体：

```json
{
    "gid" : <gid>
}
```

需要群设置为 `allow_direct_join = true`。

返回：
- 若无需审核（`require_review = false`），直接加入成功返回 `{"pending": false}`。
- 若需审核，创建入群申请，返回 `{"rid": <rid>, "pending": true}`。群主和所有管理员会收到 `group.join.request` 通知。
- 失败返回时间戳加 `False`。

---

### 邀请入群

- `^ POST /group/invite` 邀请好友加入群聊。

请求体：

```json
{
    "gid" : <gid>,
    "invited_uid" : <invited_uid>
}
```

需要操作者为群成员，且被邀请者为操作者的好友。

返回：
- 若群无需审核（`require_review = false`）或邀请者是管理员/群主，被邀请者直接加入，返回 `{"pending": false}`。被邀请者收到 `group.invited` 通知。
- 否则创建入群申请，返回 `{"rid": <rid>, "pending": true}`。群主和所有管理员会收到 `group.join.request` 通知，被邀请者也会收到 `group.invited.pending` 通知。

---

### 查看入群申请

- `^ POST /group/join_requests` 查看待处理的入群申请。

请求体：

```json
{
    "gid" : <gid>
}
```

需要操作者为管理员或群主（`is_admin >= 1`）。

返回体：

```json
[
    {
        "rid" : <rid>,
        "gid" : <gid>,
        "uid" : <applicant_uid>,
        "username" : <applicant_username>,
        "inviter_uid" : <inviter_uid>,
        "inviter_name" : <inviter_name>,
        "status" : "pending",
        "request_time" : <timestamp>
    }
]
```

其中 `inviter_uid` 为 0 表示申请人自行申请；非 0 表示由某群成员邀请。

---

### 处理入群申请

- `^ POST /group/handle_join_request` 通过或拒绝入群申请。

请求体：

```json
{
    "rid" : <rid>,
    "approved" : <true_or_false>
}
```

需要操作者为管理员或群主（`is_admin >= 1`）。

`approved = true` 通过申请，申请人加入群聊并收到 `group.join.approved` 通知。`approved = false` 拒绝申请。

返回：操作成功返回时间戳加 `True`，失败返回时间戳加 `False`。

---

### 添加管理员

- `^ POST /group/add_admin` 将群成员提升为管理员。

请求体：

```json
{
    "gid" : <gid>,
    "added" : <target_uid>
}
```

仅群主（`is_admin == 2`）可操作。

返回：成功返回时间戳加 `True`，失败返回时间戳加 `False`。成功时被提升者收到 `group.admin.added` 通知。

---

### 移除管理员

- `^ POST /group/remove_admin` 取消某成员的管理员身份。

请求体：

```json
{
    "gid" : <gid>,
    "removed" : <target_uid>
}
```

仅群主（`is_admin == 2`）可操作。

返回：成功返回时间戳加 `True`，失败返回时间戳加 `False`。成功时被移除者收到 `group.admin.removed` 通知。

---

### 移除成员

- `^ POST /group/remove_member` 将成员移出群聊。

请求体：

```json
{
    "gid" : <gid>,
    "removed" : <target_uid>
}
```

仅高角色可移除低角色（`is_admin(operator) > is_admin(target)`）。群主不可被移除。

返回：成功返回时间戳加 `True`，失败返回时间戳加 `False`。成功时被移除者收到 `group.member.removed` 通知。

---

### 转让群主

- `^ POST /group/transfer_owner` 将群主转让给另一群成员。

请求体：

```json
{
    "gid" : <gid>,
    "new_owner" : <new_owner_uid>
}
```

仅当前群主（`is_admin == 2`）可操作。`<new_owner_uid>` 必须为群成员。

返回：成功返回时间戳加 `True`，失败返回时间戳加 `False`。成功时新群主收到 `group.owner.transferred` 通知。

---

### 解散群聊

- `^ POST /group/delete_group` 解散群聊。

请求体：

```json
{
    "gid" : <gid>
}
```

仅群主（`is_admin == 2`）可操作。解散后清除群头像、入群申请记录、群记录，并向所有成员推送 `group.deleted` 通知。

返回：成功返回时间戳加 `True`，失败返回时间戳加 `False`。

---

## 通知事件类型

群聊相关的事件通知（参见[通知文档](notification.md)）：

- `group.admin.added` — 被提升为管理员
- `group.admin.removed` — 管理员权限被移除
- `group.member.removed` — 被移出群聊
- `group.deleted` — 群聊被解散
- `group.owner.transferred` — 被转让为群主
- `group.join.request` — 收到新的入群申请（发送给群主）
- `group.join.approved` — 入群申请被通过（发送给申请人）
- `group.invited` — 被邀请加入群聊（无需审核直接加入时）
- `group.invited.pending` — 被邀请加入群聊，等待审核

---

### 群头像

群头像的上传和获取与其他头像系统一致，参见[主文档](main.md)中头像相关说明。

群头像上传接口：`^ POST /avatar/upload_group_avatar`，请求体 `{"gid": <gid>, "pic": <pic_base64>}`。需要操作者为管理员或群主。

群头像获取：`GET /avatar/get_avatar/group/<gid>`。

---

## 服务端配置

群聊相关配置项可通过 `^ POST /auth/server_settings/update` 设置：

- `groups_limit`：每人最多创建的群数。`-1` 不限。
- `single_group_max_people`：单个群最大人数。`-1` 不限。
- `min_group_name_length`：群名称最小字符数，默认 `1`，最小为 `1`。
- `max_group_name_length`：群名称最大字符数，默认 `50`，最小为 `1`。
