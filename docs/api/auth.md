# TouchFish V5 Api 文档（账号相关部分）

**请确保在阅读本文档前阅读了[主文档](main.md)。**

- `^ POST /auth/login` 校验用户密码与账号是否对应 

请求体：

```
{

}
```

返回：若身份核验成功，则返回值为时间戳加上 `True`。若身份核验失败，则返回值为时间戳加上 `False`。

- `^ POST  /auth/change_sign` 改变个性签名

请求体：

```
{
    "new_sign" : <sign>
}
```

其中 `<sign>` 是新的个性签名。

返回：若密码更改成功，返回时间戳加 `True`，否则返回时间戳加 `False`。

- `^ POST  /auth/change_introduction` 改变个人简介

请求体：

```
{
    "new_introduction" : <new_intro>
}

其中 `<new_intro>` 是新的个人简介

返回：若密码更改成功，返回时间戳加 `True`，否则返回时间戳加 `False`。

- `^ POST  /auth/change_pwd`  改变用户密码

请求体：

```
{
    "new_pwd" : <new_pwd>
}
```

其中 `<new_pwd>` 是新密码。

返回：若密码更改成功，返回时间戳加 `True`，否则返回时间戳加 `False`。

- `^ POST /auth/change_auth`

请求体：

```
{
    "change_uid" : <uid>,
    "new_auth": <user_stat>
}
```

其中 `<uid>` 是被操作者的用户编号，`<new_auth>` 是用户的新状态（身份），有：`admin, banned, user`，其中只有 `root` 权限用户才可将用户状态更为 `admin`，只有 `root` 权限才可改变非 `root` 权限用户的权限到 `admin` ，`admin` 和 `root` 权限可改变 `user` 权限用户到 `banned`。

返回体：若更改成功，返回时间戳加 `True`。若无权限或更改失败，返回时间戳加 `False`。

- `^ POST /auth/chagne_captcha` 改变是否要开启图片验证码注册

请求体：

```
{
    "change_to" : <new_stat>
}
```

`<new_stat>` 为布尔对象，如果为 `true` 表示启用图片验证码注册，如果为 `false` 表示不启用图片验证码注册。

需注意只有 `root` 用户有修改这个的权限。

返回体：修改成功为时间戳加 `True`，修改失败为时间戳加 `False`。

- `^ POST /auth/change_email_verify` 改变是否要开启邮箱验证

请求体：

```
{
    "change_to" : <new_stat>,
    "verify_email" : <verify_email>,
    "email_password: <email_pwd>
}
```

`<new_stat>` 含义同上，只不过修改的是是否启用邮箱验证。如果它的值为 `true`，请附上后面两项。

`verify_email` 是发送验证邮件的邮箱，`email_password` 是发送验证邮件的的邮箱的 SMTP 授权码（**不是密码！**）。

返回体：修改成功为时间戳加 `True`，否则为时间戳加 `False`。

- `^ POST /auth/change_email` 改变用户的邮箱地址

请求体：

```
{
    "new_email" : <email>
}
```

其中 `<email>` 是新邮箱地址，必须满足邮箱地址格式。

返回体：操作成功返回时间戳加 `True`，否则返回时间戳加 `False`。

- `* GET /auth/captcha/` 获取证码图片

请求体：无

该请求用处是为注册做准备。

需要注意的是：这只有部分服务器会要求，具体是否要求请询问服主或者查询服务器信息。

返回体：若未启用验证码，返回体为空，若启用了验证码，返回体为：

```
{
    "pic" : <pic>,
    "stamp" : <stamp>
}
```

`<pic>` 是 `png` 格式图片的 Base64 编码用 `utf-8` 解码后的格式，`<stamp>` 是验证码标识码（时间戳，为整数）。


- `* GET /auth/uid/<uid>` 查询用户（以 `uid` 为键）相关信息

`<uid>` 是用户编号。

返回体：

```
{
    "uid" : <uid>,
    "username" : <username>,
    "email" : <email>,
    "stat" : <stat>,
    "create_time" : <create_time>,
    "personal_sign" : <personal_sign>,
    "introduction" : <introduction>
}
```

`<create_time>` 是用户创建时间，**为字符串形式的时间戳**。`<personal_sign>` 是个性签名，`<introduction>` 是自我介绍（约束中使用 Markdown 格式）。`<stat>` 是用户权限。

- `* GET /auth/username/<username>` 查询用户，以 `username` 查询。

返回体和返回体含义同上。


- `POST /auth/activate` 激活账号（只有要求邮箱验证的服务器会要求）

请求体：
```
{
    "uid" : <uid>,
    "activate_code" : <code>
}
```

`<code>` 是整数类型。

返回体：如果激活成功返回时间戳加 `True`，否则返回时间戳加 `False`。

- `POST /auth/register`

请求体：

```
{
    "username" : <username>,
    "password" : <password>,
    "captcha_stamp" : <captcha_stamp>,
    "captcha_code" : <captcha_code>,
    "email" : <email>
}
```

如果服务器不启用图形验证码， `<captcha_stamp>` 和 `<captcha_code>` 是可以省略的。

**`captcha_stamp` 是字符串**。

如果服务器不启用邮箱激活，`<email>` 是可以省略的。

注册成功返回时间戳加 True，否则返回时间戳加 False。需注意如果要邮箱验证，用户初始状态为 `banned`。