# TouchFish V5 Api 文档（论坛相关部分）

> 因为我懒得写了，所以我不说明就默认成功时返回时间戳加 True，否则返回时间戳加 False。

- `^ POST /forum/create_forum` 创建论坛。

请求体：

```
{
    "forum_name" : <forum_name>,
    "introduction" : <introduction>
}
```

需注意，创建论坛后不是马上出现在论坛页面，是进入审核页面，等待管理员审核。

- `^ POST /forum/get_approving_forum_list` 获取所有在审核队列

**只有 ADMIN 和 ROOT 用户有权限访问。**

请求体：

```
{

}
```

返回体：

一个字符串化的 json，返回体例为：

```
{
    "queue_num" : <queue_num>,
    <qid> : {
        "creater" : <creater>,
        "forumname" : <forumname>,
        "introduction" : <introduction>
    }
    ...
}
```

其中 `<queue_num>` 是在队列的待审批论坛数量。

- `^ POST /forum/approve_forum` 批准论坛。

请求体：

```
{
    "qid" : <qid>
}
```

`<qid>` 是队列中的请求 id，获取方法见上。

- `* GET /forum/get_forum_list` 获取所有论坛

返回体：

```
[
    [
        <forum_id>,
        <forumname>,
        <creater_id>,
        <creater_time>,
        <introduction>
    ],
    ...
]
```

- `^ POST /forum/send_post` 发布帖子

请求体：

```
{
    "fid" : <fid>,
    "title" : <title>,
    "content" : <content>
}
```

- `* GET /get_post_list/<fid>` 获取某一论坛的所有帖子

返回体：

```
[
    [
        <post_id>,
        <title>,
        <creater>,
        <content>,
        <create_time>
    ]
]
```

- `^ POST /forum/remove_post` 删除帖子

**只有论坛创始人、帖子发布者、管理员有权限操作**

请求体：

```
{
    "fid" : <fid>,
    "pid" : <pid>
}
```


- `^ POST /forum/remove_post` 删除论坛

**只有论坛创始人、管理员有权限操作**

请求体：

```
{
    "fid" : <fid>,
}
```