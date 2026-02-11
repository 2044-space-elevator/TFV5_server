# TouchFishServer V5 Api 文档，主页面

欢迎参阅 TouchFish V5 Api 文档（对于 TouchFishServer V5，下简称 TFV5），对于查阅你需要使用的 Api 前，请仔细阅读该文档，以免造成不必要的误解和麻烦。

本文章主要介绍 TFV5 api 中的约定俗成以及加密规定，作为所有 API 的基础。

因为 TFV5 API 体系较为庞大，如有问题可在 Github 上或 TF 群里资讯。

**错误访问和访问失败可能会返回 API 规定的结果，也可能返回空 JSON 或字符串 `Wrong Requests!`。**

**请不要频繁访问 API，遵循服主要求。**

## 文档约定

约定 1：secret 类型的 API 条目前面**不加**星号，public 类型的 API 条目前面**加**星号。

> 例如：
> `* /get_rsa_pub` 获取该服务器的 RSA 公钥。

至于何为 secret 类型 API，何为 public 类型 API，详见[API类型和对应请求方法](#api-类型和对应请求方法)。

约定 2：要带用户 uid 和密码的 API 条目前面**加** ^ 号，不带用户 uid 和密码的 API 条目前面**不加** ^ 号。

**用户密码是明文传输**，但保证带有 ^ 号的一定不加 * 号。以确保明文传输密码时的安全

对于约定 2 中如何上传请求体，详见[API类型和对应请求方法](#api-类型和对应请求方法)。

约定 3：API 中 `<uid>` 表示填入用户编码的占位符，`<fid>` 表示填入论坛编码的占位符，`<gid>` 表示填入群聊编码的占位符，`<aid>` 表示填入公告编码的占位符。

## 获取服务器的 RSA 公钥

持有 RSA 公钥是访问 TFV5 api 的必要前提，否则你将无法访问大部分的 TFV5 api（因为它们都需要加密）。

以下是获取 RSA 公钥的 API：

- `* GET /get_rsa_pub` 获取该服务器的 RSA 公钥。

请求体：无。

返回值：PEM 格式的 RSA 公钥文件，文件名为 `<servername>.pem`，其中 servername 是以服务器的端口。

服务器在部署成功后会自动生成公钥哈希值，TFV5 要求部署者将哈希值通过可靠的方式公布于用户中。**为防止中间人攻击，务必对公钥文件进行 SHA256 哈希并校对部署者提供的公钥哈希值**。

## Api 类型和对应请求方法

TFV5 api 分为两类：secret 和 public。

约定4：TFV5 Api 文档中，secret 请求类型一般为 POST，public 请求类型一般为 GET。

对于 secret 请求，请使用 RSA + AES 混合加密，服务器将返回使用你的 AES 密钥加密后的值。对于 public 请求，请明文上传请求体。

### 对于 secret 类型

**务必先获取服务器的 RSA 密钥并校对**。

标准请求体如下：

```json
{
    "iv": <iv>,
    "key": <key>,
    "content" : <content>
}
```

AES 加密需要有初始向量（IV），在 Python 中，它的生成代码是（意味着 iv 的 bytes 形式长度为 16）：

```python
os.urandom(16)
```

**IV 是不需要保密的**，请直接将 IV Base64 编码后再用 UTF-8 解码成字符串并传入 `<iv>`。但请保证每次使用不同的 IV。

再随机生成一个 AES 密钥，AES 鉴于其快速的特点**强烈建议每一次使用不同的 AES 密钥**，在 Python 中，它的生成代码是（意味着 AES 密钥的 bytes 形式长度为 32）：

```python
os.urandom(32)
```

**将你生成的 AES 密钥使用服务器的 RSA 公钥进行 AES 加密，得到 bytes 串，将该 bytes 串使用 Base64 编码后再用 UTF-8 解码成字符串并传入 `<key>`**。

接着 `Content` 是 secret API 真正要求的请求体，格式为以字符串形式表示的 JSON。

**请将真正的请求体的字符串形式使用你的 AES key 进行 AES 加密，加密后将加密后的 bytes 串使用 Base64 编码后再用 UTF-8 解码成字符串并传入 <content>**。

### 对于 public 类型

依照 api 要求，直接明文传输请求体即可。

### 对于用户令牌类型（要求请求体包含用户的密码）

请按照[对于 secret 类型](#对于-secret-类型)的方法中，将你的请求体做混合加密。

请求体中，除了 API 文档要求的那些，再包含两个键值对，内容为：

```json
{
    "uid" : <uid>
    "password" : <password>
    # Request body
    # ......
}
```

### 对于 secret 类型 API 的返回值

其返回值为：

```
{
    "iv" : <iv>,
    "content": <content>
}
```

服务器会生成一个长度 16 位的 Bytes iv，**并将其 Base64 编码后用 UTF-8 解码成字符串，传入 `<iv>`**。

服务器还会用这个 iv 和请求体中的 AES key 加密 API 文档中规定的返回体的字符串格式，生成的 Bytes **用 Base64 编码后再用 UTF-8 解码成字符串，传入 `<content>`**。

## 对于 secret 类型 API 的测试用例

加密流程有一点复杂，因此举个例子，请将 TFV5 代码包下载，解压，使用终端切换到 contact 目录。

确保你的 Python 环境中有 `cryptography` 库、`Flask` 库与 `requests` 库。

请在终端中打开 `python`，输入：

```python
import crypto
pri, pub, pripem, pubpem, has = crypto.generate_rsa_keys()
with open("pub.pem", "wb") as file:
    file.write(pubpem)

with open("pri.pem", "wb") as file:
    file.write(pripem)
```

**测试完成后，建议删除目录下的 pub.pem 和 pri.pem。**

获取公钥、私钥的绝对路径。

运行 test1.py，与此同时运行 test2.py，输入所求。

如果在 test1.py 的输出看到了请求体，test2.py 的输出看到了 `Hello World`，证明加密 API 通信成功。

开发者可以通过阅读 `test2.py` 的代码来理解 secret API 请求的原理。