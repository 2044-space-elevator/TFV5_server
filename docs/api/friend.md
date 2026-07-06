# TouchFish V5 Api 文档（好友相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

TFV5 的好友系统基于申请-审核机制：一方发起好友申请后，关系进入 `pending` 状态，另一方处理（通过或拒绝）后结束流程。

## Secret API

> 因为这些接口属于 secret 类型，所以请求体仍然需要按照[主文档](main.md)中的 RSA + AES 方式加密。

- `^ POST /friend/add_friend` 向其他用户发起好友申请。

请求体：

```json
{
    "added" : <added_uid>,
    "req_word" : <req_word>
}
```

其中 `<added_uid>` 是被添加用户的 uid，`<req_word>` 是验证信息（预留字段，目前未使用）。

返回：若操作成功，返回时间戳加 `True`，否则返回时间戳加 `False`。

成功时会向对方推送 `friend.request` 事件（参见[通知文档](notification.md)）。

---

- `^ POST /friend/deal_ship` 处理好友申请（通过或拒绝）。

请求体：

```json
{
    "dealt" : <dealt_uid>,
    "stat" : <stat>
}
```

其中 `<dealt_uid>` 是发起好友申请的用户的 uid，`<stat>` 为 `"allow"` 或 `"reject"`。

- `"allow"`：通过申请，关系变为 `friend`。
- `"reject"`：拒绝申请，关系记录被删除。

返回：若操作成功，返回时间戳加 `True`，否则返回时间戳加 `False`。

成功通过时会向对方推送 `friend.accepted` 事件（参见[通知文档](notification.md)）。

## 注意事项

- 无法对自己发起好友申请。
- 已有关系记录（pending / friend / blocked）的双方无法重复发起申请。
- 只有收到申请的一方才能处理该申请（发起者不能自行通过自己的申请）。
