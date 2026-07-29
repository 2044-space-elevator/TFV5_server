# 表情包 API

> 这么点内容真的要单开文档吗？

表情资源只以内容 SHA-256 标识。

现在表情包不再依赖 MIME 判断类型。

通常的表情字符串为 `:pack+sticker`，其中 `pack` 是表情包的前缀，`sticker` 是表情标识符（下记作 `slug`）。

`file_type` 由服务端通过内容特征识别，目前服务器支持识别 `png`、`jpg`、`gif`、`bmp`、`svg`、`tgs`。

- `GET /sticker/market?offset=0&limit=20&order=usage|date&query=`：市场（分页）。

- `GET /sticker/pack/<id>`：获取表情包及内容。

- `GET /sticker/lookup/<prefix+slug>`：表情代码查询。

- `^ POST /sticker/mine`：已收藏包。

- `^ POST /sticker/created`：当前用户创建的包。

- `^ POST /sticker/pack/create`：`name`、`prefix`、可选 `description`。

- `^ POST /sticker/item/create`：`pack_id`、`slug`、`file_hash`、可选 `name/size/mode`。

- `^ POST /sticker/ownership`：`pack_id`、`owned` 添加或移除收藏。

- `^ POST /sticker/ownership/reorder`：完整 `pack_ids` 数组，按收藏顺序重排。

新建贴图包会自动加入创建者的收藏列表。创建贴图项时，`file_hash` 必须是当前用户有效拥有的上传文件。

服务器默认限制：

普通用户最多 24 个贴图包、每包 24 张、每日创建不限。
管理员和 root 不受限制。
服务器 JSON 配置项 `max_sticker_packs_per_user`、`max_stickers_per_pack`、`daily_sticker_pack_creation_limit` 可通过 JSON 或 root 设置 API 更新。
